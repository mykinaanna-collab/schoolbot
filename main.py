import asyncio
import os
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote

import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")

CHANNEL_URL = "https://t.me/ozonbluerise"
CONSULT_FORM_URL = os.getenv(
    "CONSULTATION_FORM_URL",
    "https://forms.yandex.ru/u/697a05d3d046884d940bc2af/",
)

# Профиль поддержки (НЕ бот)
SUPPORT_CONTACT = "BlueRise_support"
LEGACY_SUPPORT_HANDLES = ("yashiann", "ilya_bolsheglazov")

DEFAULT_ROOT_TEXT = (
    "Приветствую, {name}!\n\n"
    "Это «Синий рассвет» — здесь мы систематизируем бизнес на маркетплейсах: "
    "от основ до продвинутых стратегий."
)

# Единое имя кнопки для ссылки оплаты по карте/СБП
PAYLINK_BUTTON_LABEL = "Запросить ссылку на оплату по карте или СБП"

# Единое имя кнопки для счета
BILL_BUTTON_LABEL = "Выставить счет для оплаты с р/с"


def bill_prefill(course_title: str) -> str:
    # Диалог открывается с предзаполненным текстом (НЕ отправляется автоматически)
    return (
        "Добрый день. Хочу оплатить через р/с. "
        f"Выставьте пожалуйста счет за курс «{course_title}». "
        "ИНН организации — (укажите свой ИНН)."
    )


def paylink_prefill(course_title: str) -> str:
    return f"Здравствуйте! Нужна ссылка на оплату по карте или СБП за курс «{course_title}»."


dp = Dispatcher()
POOL: Optional[asyncpg.Pool] = None


class EditTextFlow(StatesGroup):
    slug = State()
    text = State()


class AddButtonFlow(StatesGroup):
    slug = State()
    label = State()
    action = State()
    target = State()
    position = State()


class EditButtonFlow(StatesGroup):
    button_id = State()
    label = State()
    action = State()
    target = State()
    position = State()


class DeleteButtonFlow(StatesGroup):
    button_id = State()


@dataclass(frozen=True)
class Node:
    slug: str
    text: str


@dataclass(frozen=True)
class Button:
    id: int
    label: str
    action_type: str
    target: str
    position: int


def is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and user_id == OWNER_ID


def tg_link(username: str, text: str) -> str:
    return f"https://t.me/{username}?text={quote(text)}"


async def init_db() -> None:
    """
    ВАЖНО:
    - Сначала создаём таблицы
    - Потом удаляем дубли (если были)
    - Потом создаём UNIQUE индекс (node_id, label)
    - И только после этого начинаем использовать ON CONFLICT
    """
    assert POOL is not None
    async with POOL.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id SERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buttons (
                id SERIAL PRIMARY KEY,
                node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        # 1) чистим дубли (если уже были)
        await dedupe_buttons(conn)

        # 2) создаём уникальность по (node_id, label) — чтобы не могло быть 2 одинаковых кнопок по названию
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_buttons_node_label
            ON buttons (node_id, label);
            """
        )

        # 3) гарантируем root + структуру
        root_id = await ensure_node(conn, "root", DEFAULT_ROOT_TEXT.format(name="друг"))
        await seed_default_nodes(conn, root_id)

        # 4) миграции текстов/ссылок (и в nodes, и в buttons)
        await migrate_support_contacts(conn)
        await migrate_text_typos(conn)
        await normalize_buttons(conn)

        # 5) финальный дедуп на всякий
        await dedupe_buttons(conn)


async def ensure_node(conn: asyncpg.Connection, slug: str, text: str) -> int:
    node_id = await conn.fetchval(
        "INSERT INTO nodes (slug, text) VALUES ($1, $2) "
        "ON CONFLICT (slug) DO NOTHING RETURNING id",
        slug,
        text,
    )
    if node_id:
        return node_id
    existing = await conn.fetchval("SELECT id FROM nodes WHERE slug=$1", slug)
    if not existing:
        raise RuntimeError(f"Failed to create or fetch node: {slug}")
    return existing


async def ensure_button(
    conn: asyncpg.Connection,
    node_id: int,
    label: str,
    action_type: str,
    target: str,
    position: int,
) -> None:
    """
    UPSERT по (node_id, label):
    - если кнопка уже есть — обновляем action/target/position
    - это убирает дубли и гарантирует актуальные ссылки/тексты
    """
    await conn.execute(
        """
        INSERT INTO buttons (node_id, label, action_type, target, position)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (node_id, label) DO UPDATE
        SET action_type = EXCLUDED.action_type,
            target = EXCLUDED.target,
            position = EXCLUDED.position
        """,
        node_id,
        label,
        action_type,
        target,
        position,
    )


async def seed_default_nodes(
    conn: asyncpg.Connection,
    root_id: int,
    *,
    replace_existing: bool = False,
) -> None:
    nodes = [
        ("courses", "Выберите раздел 👇"),
        (
            "pre_courses",
            "Все курсы в нашей линейке предзаписанные и с постоянными апдейтами под изменения в Озон.\n\n"
            "Не надо ждать потоков, курс идет по принципу «Купи и смотри». Доступ к нему и ко всем его "
            "изменениям остается навсегда.\n\n"
            "Вся линейка курсов задумана, как постоянно обновляемая База Знаний, с помощью которых вы "
            "сможете обучать новых сотрудников и постоянно актуализировать свои знания. Доступ ко всем "
            "обновлениям купленного курса БЕСПЛАТНЫЙ.",
        ),
        (
            "beginner_course",
            "«Грамотный старт на Озон» — для селлеров и менеджеров, которые делают первые шаги в Озон "
            "и хотят начать уверенно разбираться во всех основных вещах, необходимых для ведения прибыльного бизнеса.",
        ),
        ("advanced_courses", "Продвинутый уровень: выберите курс 👇"),
        (
            "pro_logistics",
            "Курс PRO логистику для тех, кто хочет снизить СВД в своем кабинете, понимать сколько товара "
            "грузить в каждый кластер и понять, как не переплачивать за логистику.",
        ),
        (
            "pro_ads",
            "Курс PRO рекламу — для тех, кто хочет оптимизировать свои рекламные расходы, научиться выстраивать "
            "рекламные стратегии и понимать, какими инструментами продвижения пользоваться для разных типов товаров "
            "и в различных ситуациях.",
        ),
        (
            "pro_analytics",
            "Курс PRO Аналитику — для тех, кто хочет изучить все значимые нюансы и все инструменты, которые необходимы для анализа.",
        ),
        (
            "pro_finance",
            "Курс «PRO Финансы» — для тех, кто хочет научиться считать юнит-план и юнит-факт, ROI и маржинальность. "
            "Разбираться в финансовых отчетах Озона, иметь представление о кредитных инструментах.",
        ),
        ("all_about_ozon", "Все 4 блока курсов PRO логистику, PRO рекламу, PRO аналитику, PRO финансы в одном со скидкой 20%."),
        ("special_courses", "Спецкурсы и инструменты: выберите курс 👇"),
        (
            "pro_design",
            "Курс «PRO Дизайн» — для тех, кто хочет понять принципы продающей инфографики, уберечь себя от ошибок "
            "в дизайне карточек товара, которые ведут к снижению CTR, научиться выстраивать взаимоотношения с дизайнерами "
            "и «считывать» их квалификацию.",
        ),
        (
            "sxr_ai",
            "Курс по нейросетям от SXR Studio для тех, кто смотрит в будущее и хочет научиться генерировать нейро-контент "
            "для своих карточек товара.",
        ),
        (
            "new_courses",
            "Здесь будут появляться анонсы новых курсов и специальных форматов обучения.\n\n"
            "Мы регулярно работаем над тем, чтобы обучение было еще полезнее и эффективнее. Возможно, это будут обновленные "
            "программы или новые проекты.\n\n"
            "Хотите быть в курсе всех новинок первыми?\n"
            f"👉 Подпишитесь на наш канал: {CHANNEL_URL}\n\n"
            "А пока все наши основные курсы для старта и уверенного роста уже ждут вас в 📚 Предзаписанные курсы.",
        ),
        (
            "webinars",
            "Поздравляю! Вам открыт доступ к вебинарам по Яндекс маркету.\n\n"
            "Что вы получите внутри:\n"
            "1. Запись 3-х дней вебинаров по ЯМ, в которых разобраны все аспекты работы с площадкой.\n"
            "2. Ссылка на чат единомышленников.\n\n"
            "Кстати, подписывайтесь на мой канал «Синий рассвет» — там куча полезной информации по Озон и про бизнес на маркетплейсах в целом.",
        ),
        (
            "help",
            "Чтобы подобрать курс, который решит именно вашу задачу, напишите напрямую @BlueRise_support. "
            "Опишите ваш опыт и цель — и вы получите персональную рекомендацию.",
        ),
        (
            "support",
            "По любым техническим вопросам (доступ к курсам, проблемы с оплатой) напишите напрямую @BlueRise_support. "
            "Опишите проблему как можно подробнее — это поможет решить её быстрее.",
        ),
        (
            "calculator",
            "Поздравляю! Вам открыт доступ к обновленному калькулятору.\n\n"
            "Что вы получите внутри:\n"
            "1. Калькулятор с FBS и новой логистикой.\n"
            "2. Подробное видеообъяснение к калькулятору: как пользоваться, что ввести, на что смотреть.\n\n"
            "Кстати, подписывайтесь на мой канал «Синий рассвет». Там куча полезной информации по Озон и про бизнес на маркетплейсах в целом.",
        ),
        (
            "partnership",
            "Привет! 👋\n\n"
            "Этот раздел — для обсуждения профессионального партнёрства.\n\n"
            "Чтобы предложить свою идею, напишите напрямую @BlueRise_support в Telegram. "
            "В первом сообщении кратко опишите суть предложения — это поможет начать диалог максимально предметно.\n\n"
            "Жду вашего сообщения! 🤝",
        ),
        (
            "consult",
            "Индивидуальный разбор вашего кейса.\n\n"
            "Для записи заполните, пожалуйста, форму. Это поможет подготовиться к нашей встрече.",
        ),
    ]

    node_ids = {"root": root_id}
    for slug, text in nodes:
        node_id = await ensure_node(conn, slug, text)
        node_ids[slug] = node_id
        if replace_existing:
            await conn.execute("UPDATE nodes SET text=$1 WHERE slug=$2", text, slug)

    if replace_existing:
        await conn.execute("DELETE FROM buttons WHERE node_id = ANY($1::int[])", list(node_ids.values()))
        await conn.execute("UPDATE nodes SET text=$1 WHERE slug='root'", DEFAULT_ROOT_TEXT.format(name="друг"))

    # ROOT
    await ensure_button(conn, root_id, "Наши курсы", "node", "courses", 1)
    await ensure_button(conn, root_id, "Калькулятор OZON/ЯМ", "node", "calculator", 2)
    await ensure_button(conn, root_id, "Сотрудничество", "node", "partnership", 3)
    await ensure_button(conn, root_id, "Личная консультация", "node", "consult", 4)

    # COURSES
    await ensure_button(conn, node_ids["courses"], "📚 Предзаписанные курсы", "node", "pre_courses", 1)
    await ensure_button(conn, node_ids["courses"], "🆕 Новинки и потоки", "node", "new_courses", 2)
    await ensure_button(conn, node_ids["courses"], "🔶 Бесплатные вебинары по ЯМ", "node", "webinars", 3)
    await ensure_button(conn, node_ids["courses"], "❓ Помощь с выбором курса", "node", "help", 4)
    await ensure_button(conn, node_ids["courses"], "🛠️ Техническая поддержка", "node", "support", 5)
    await ensure_button(conn, node_ids["courses"], "⬅️ Назад", "node", "root", 6)

    # PRE COURSES
    await ensure_button(conn, node_ids["pre_courses"], "🚀 Ozon: Начальный уровень", "node", "beginner_course", 1)
    await ensure_button(conn, node_ids["pre_courses"], "⚡ Ozon: Продвинутый уровень", "node", "advanced_courses", 2)
    await ensure_button(conn, node_ids["pre_courses"], "🛠️ Спецкурсы и инструменты", "node", "special_courses", 3)
    await ensure_button(conn, node_ids["pre_courses"], "⬅️ Назад", "node", "courses", 4)

    # BEGINNER
    course_title = "Грамотный старт на Озон"
    await ensure_button(conn, node_ids["beginner_course"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/GSO_VC", 1)
    await ensure_button(conn, node_ids["beginner_course"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["beginner_course"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["beginner_course"], "⬅️ Назад", "node", "pre_courses", 4)

    # ADVANCED COURSES
    await ensure_button(conn, node_ids["advanced_courses"], "PRO логистику", "node", "pro_logistics", 1)
    await ensure_button(conn, node_ids["advanced_courses"], "PRO рекламу", "node", "pro_ads", 2)
    await ensure_button(conn, node_ids["advanced_courses"], "PRO Аналитику", "node", "pro_analytics", 3)
    await ensure_button(conn, node_ids["advanced_courses"], "PRO Финансы", "node", "pro_finance", 4)
    await ensure_button(conn, node_ids["advanced_courses"], "Всё про Озон", "node", "all_about_ozon", 5)
    await ensure_button(conn, node_ids["advanced_courses"], "⬅️ Назад", "node", "pre_courses", 6)

    # PRO LOGISTICS
    course_title = "PRO логистику"
    await ensure_button(conn, node_ids["pro_logistics"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/PRO_logistics", 1)
    await ensure_button(conn, node_ids["pro_logistics"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["pro_logistics"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["pro_logistics"], "⬅️ Назад", "node", "advanced_courses", 4)

    # PRO ADS
    course_title = "PRO рекламу"
    await ensure_button(conn, node_ids["pro_ads"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/PRO_Reklamu", 1)
    await ensure_button(conn, node_ids["pro_ads"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["pro_ads"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["pro_ads"], "⬅️ Назад", "node", "advanced_courses", 4)

    # PRO ANALYTICS
    course_title = "PRO Аналитику"
    await ensure_button(conn, node_ids["pro_analytics"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/PRO_Analytics", 1)
    await ensure_button(conn, node_ids["pro_analytics"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["pro_analytics"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["pro_analytics"], "⬅️ Назад", "node", "advanced_courses", 4)

    # PRO FINANCE
    course_title = "PRO Финансы"
    await ensure_button(conn, node_ids["pro_finance"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/PRO_Finance", 1)
    await ensure_button(conn, node_ids["pro_finance"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["pro_finance"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["pro_finance"], "⬅️ Назад", "node", "advanced_courses", 4)

    # ALL ABOUT OZON
    course_title = "Всё про Озон"
    await ensure_button(conn, node_ids["all_about_ozon"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/all_about_ozon", 1)
    await ensure_button(conn, node_ids["all_about_ozon"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["all_about_ozon"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["all_about_ozon"], "⬅️ Назад", "node", "advanced_courses", 4)

    # SPECIAL COURSES
    await ensure_button(conn, node_ids["special_courses"], "PRO Дизайн", "node", "pro_design", 1)
    await ensure_button(conn, node_ids["special_courses"], "Нейросети от SXR Studio", "node", "sxr_ai", 2)
    await ensure_button(conn, node_ids["special_courses"], "⬅️ Назад", "node", "pre_courses", 3)

    # PRO DESIGN
    course_title = "PRO Дизайн"
    await ensure_button(conn, node_ids["pro_design"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/PRO_design", 1)
    await ensure_button(conn, node_ids["pro_design"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["pro_design"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["pro_design"], "⬅️ Назад", "node", "special_courses", 4)

    # SXR AI
    course_title = "Нейросети от SXR Studio"
    await ensure_button(conn, node_ids["sxr_ai"], "Узнать подробности и купить курс", "url", "https://bluerise.getcourse.ru/SXR_AI", 1)
    await ensure_button(conn, node_ids["sxr_ai"], BILL_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, bill_prefill(course_title)), 2)
    await ensure_button(conn, node_ids["sxr_ai"], PAYLINK_BUTTON_LABEL, "url", tg_link(SUPPORT_CONTACT, paylink_prefill(course_title)), 3)
    await ensure_button(conn, node_ids["sxr_ai"], "⬅️ Назад", "node", "special_courses", 4)

    # NEW COURSES
    await ensure_button(conn, node_ids["new_courses"], "📚 Предзаписанные курсы", "node", "pre_courses", 1)
    await ensure_button(conn, node_ids["new_courses"], "Подписаться на канал", "url", CHANNEL_URL, 2)
    await ensure_button(conn, node_ids["new_courses"], "⬅️ Назад", "node", "courses", 3)

    # WEBINARS
    await ensure_button(conn, node_ids["webinars"], "Вебинар тут", "url", "https://bluerise.getcourse.ru/teach/control/stream/view/id/934642226", 1)
    await ensure_button(conn, node_ids["webinars"], "Подписаться на канал", "url", CHANNEL_URL, 2)
    await ensure_button(conn, node_ids["webinars"], "⬅️ Назад", "node", "courses", 3)

    # HELP / SUPPORT
    await ensure_button(conn, node_ids["help"], "Написать в поддержку", "url", tg_link(SUPPORT_CONTACT, "Добрый день. Помогите с выбором курса."), 1)
    await ensure_button(conn, node_ids["help"], "⬅️ Назад", "node", "courses", 2)

    await ensure_button(conn, node_ids["support"], "Написать в поддержку", "url", tg_link(SUPPORT_CONTACT, "Добрый день. Возникла техническая проблема: (опишите, пожалуйста)."), 1)
    await ensure_button(conn, node_ids["support"], "⬅️ Назад", "node", "courses", 2)

    # CALCULATOR
    await ensure_button(
        conn,
        node_ids["calculator"],
        "Калькулятор здесь",
        "url",
        "https://docs.google.com/spreadsheets/d/1e4AVf3dDueEoPxQHeKOVFHgSpbcLvnbGnn6_I6ApRwg/edit?gid=246238448#gid=246238448",
        1,
    )
    await ensure_button(conn, node_ids["calculator"], "Подписаться на канал", "url", CHANNEL_URL, 2)
    await ensure_button(conn, node_ids["calculator"], "⬅️ Назад", "node", "root", 3)

    # PARTNERSHIP
    await ensure_button(conn, node_ids["partnership"], "Написать в Telegram", "url", tg_link(SUPPORT_CONTACT, "Здравствуйте! Хочу обсудить сотрудничество."), 1)
    await ensure_button(conn, node_ids["partnership"], "⬅️ Назад", "node", "root", 2)

    # CONSULT
    await ensure_button(conn, node_ids["consult"], "📅 ЗАПОЛНИТЬ ЗАЯВКУ", "url", CONSULT_FORM_URL, 1)
    await ensure_button(conn, node_ids["consult"], "⬅️ Назад", "node", "root", 2)


async def migrate_support_contacts(conn: asyncpg.Connection) -> None:
    # В текстах узлов: @old -> @new
    await conn.execute(
        """
        UPDATE nodes
        SET text = replace(
            replace(text, '@' || $1, '@' || $3),
            '@' || $2,
            '@' || $3
        )
        WHERE text LIKE '%' || '@' || $1 || '%'
           OR text LIKE '%' || '@' || $2 || '%'
        """,
        LEGACY_SUPPORT_HANDLES[0],
        LEGACY_SUPPORT_HANDLES[1],
        SUPPORT_CONTACT,
    )

    # В текстах узлов: t.me/old -> t.me/new
    for legacy in LEGACY_SUPPORT_HANDLES:
        await conn.execute(
            """
            UPDATE nodes
            SET text = replace(
                replace(text, 'https://t.me/' || $1, 'https://t.me/' || $2),
                't.me/' || $1,
                't.me/' || $2
            )
            WHERE text LIKE '%' || 't.me/' || $1 || '%'
               OR text LIKE '%' || 'https://t.me/' || $1 || '%'
            """,
            legacy,
            SUPPORT_CONTACT,
        )

    # В targets кнопок: t.me/old -> t.me/new (на всякий)
    for legacy in LEGACY_SUPPORT_HANDLES:
        await conn.execute(
            """
            UPDATE buttons
            SET target = replace(
                replace(target, 'https://t.me/' || $1, 'https://t.me/' || $2),
                't.me/' || $1,
                't.me/' || $2
            )
            WHERE target LIKE '%' || $1 || '%'
            """,
            legacy,
            SUPPORT_CONTACT,
        )


async def migrate_text_typos(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        UPDATE nodes
        SET text = replace(text, 'крако', 'кратко')
        WHERE text LIKE '%' || 'крако' || '%'
        """
    )


async def normalize_buttons(conn: asyncpg.Connection) -> None:
    """
    На случай, если в базе были старые названия/вариации:
    - "Запросить ссылку на оплату" -> новое имя
    - разные варианты "Выставить счет..." -> единое имя
    """
    await conn.execute(
        """
        UPDATE buttons
        SET label = $1
        WHERE label IN ('Запросить ссылку на оплату', 'Запросить ссылку на оплату по карте или СБП')
        """,
        PAYLINK_BUTTON_LABEL,
    )

    await conn.execute(
        """
        UPDATE buttons
        SET label = $1
        WHERE label IN ('Выставить счет для оплаты с r/с', 'Выставить счет для оплаты с р/с', 'Выставить счет для оплаты с р/с ')
        """,
        BILL_BUTTON_LABEL,
    )


async def dedupe_buttons(conn: asyncpg.Connection) -> None:
    """
    Удаляем дубли по (node_id, label) — оставляем самую раннюю запись.
    Это нужно, чтобы можно было создать UNIQUE индекс.
    """
    await conn.execute(
        """
        DELETE FROM buttons
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY node_id, label
                           ORDER BY id
                       ) AS rn
                FROM buttons
            ) t
            WHERE t.rn > 1
        )
        """
    )


async def fetch_node(slug: str) -> Optional[Node]:
    assert POOL is not None
    async with POOL.acquire() as conn:
        row = await conn.fetchrow("SELECT slug, text FROM nodes WHERE slug=$1", slug)
    if not row:
        return None
    return Node(slug=row["slug"], text=row["text"])


async def fetch_buttons(slug: str) -> list[Button]:
    assert POOL is not None
    async with POOL.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.label, b.action_type, b.target, b.position
            FROM buttons b
            JOIN nodes n ON n.id = b.node_id
            WHERE n.slug = $1
            ORDER BY b.position ASC, b.id ASC
            """,
            slug,
        )
    return [
        Button(
            id=row["id"],
            label=row["label"],
            action_type=row["action_type"],
            target=row["target"],
            position=row["position"],
        )
        for row in rows
    ]


async def find_root_target_by_label(label: str) -> Optional[str]:
    assert POOL is not None
    async with POOL.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT b.target
            FROM buttons b
            JOIN nodes n ON n.id = b.node_id
            WHERE n.slug='root' AND b.label=$1
            """,
            label,
        )
    if not row:
        return None
    return row["target"]


def build_kb(buttons: Iterable[Button]) -> Optional[InlineKeyboardMarkup]:
    rows: list[list[InlineKeyboardButton]] = []
    for btn in buttons:
        if btn.action_type == "url":
            rows.append([InlineKeyboardButton(text=btn.label, url=btn.target)])
        else:
            rows.append([InlineKeyboardButton(text=btn.label, callback_data=f"node:{btn.target}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_root_reply_kb(buttons: Iterable[Button]) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    for btn in buttons:
        keyboard.append([KeyboardButton(text=btn.label)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Разделы"), KeyboardButton(text="✏️ Изменить текст")],
            [KeyboardButton(text="➕ Добавить кнопку"), KeyboardButton(text="🔧 Изменить кнопку")],
            [KeyboardButton(text="🗑 Удалить кнопку"), KeyboardButton(text="❌ Сброс")],
        ],
        resize_keyboard=True,
    )


async def render_node(target: Message, slug: str) -> None:
    node = await fetch_node(slug)
    if not node:
        await target.answer("Раздел не найден. Проверьте структуру или выполните /repair.")
        return
    buttons = await fetch_buttons(slug)
    await target.answer(node.text, reply_markup=build_kb(buttons))


@dp.message(CommandStart())
async def start(m: Message) -> None:
    name = m.from_user.first_name if m.from_user else "друг"
    node = await fetch_node("root")
    if not node:
        await m.answer("Меню ещё не настроено.")
        return
    text = node.text.replace("{name}", name)
    buttons = await fetch_buttons("root")
    await m.answer(text, reply_markup=build_root_reply_kb(buttons))


@dp.message(F.text)
async def root_menu_click(m: Message, state: FSMContext) -> None:
    text = (m.text or "").strip()
    if text.startswith("/"):
        return
    if await state.get_state():
        return
    target_slug = await find_root_target_by_label(text)
    if not target_slug:
        return
    await render_node(m, target_slug)


@dp.callback_query(F.data.startswith("node:"))
async def cb_node(c: CallbackQuery) -> None:
    slug = c.data.split(":", 1)[1]
    await render_node(c.message, slug)
    await c.answer()


@dp.message(F.text == "/admin")
async def admin_help(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    await m.answer(
        "Админ-режим.\n"
        "/nodes — список разделов\n"
        "/node <slug> — показать раздел и кнопки\n"
        "/addnode <slug> <text> — создать раздел\n"
        "/delnode <slug> — удалить раздел\n"
        "/settext <slug> <text> — обновить текст раздела\n"
        "/addbtn <slug> <label> | <node:slug|url:https://...> | [position]\n"
        "/setbtn <id> <label> | <node:slug|url:https://...> | [position]\n"
        "/delbtn <id> — удалить кнопку\n\n"
        "Выход из пошагового режима: /cancel",
        reply_markup=admin_reply_kb(),
    )


@dp.message(F.text == "/repair")
async def repair_seed(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    assert POOL is not None
    async with POOL.acquire() as conn:
        root_id = await ensure_node(conn, "root", DEFAULT_ROOT_TEXT.format(name="друг"))

        # Важно: перед /repair — опять же дедуп и индекс (на случай, если база старая)
        await dedupe_buttons(conn)
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_buttons_node_label
            ON buttons (node_id, label);
            """
        )

        await seed_default_nodes(conn, root_id, replace_existing=True)
        await migrate_support_contacts(conn)
        await migrate_text_typos(conn)
        await normalize_buttons(conn)
        await dedupe_buttons(conn)

    await m.answer("Структура восстановлена. Откройте раздел заново.")


@dp.message(F.text == "/cancel")
async def cancel_flow(m: Message, state: FSMContext) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    await state.clear()
    await m.answer("Готово, сбросила шаги.", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == "📄 Разделы")
@dp.message(F.text == "/nodes")
async def list_nodes(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    assert POOL is not None
    async with POOL.acquire() as conn:
        rows = await conn.fetch("SELECT slug FROM nodes ORDER BY slug")
    if not rows:
        await m.answer("Разделов нет.")
        return
    await m.answer("Разделы:\n" + "\n".join(row["slug"] for row in rows))


@dp.message(F.text.startswith("/node "))
async def show_node(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    slug = m.text.split(maxsplit=1)[1].strip()
    node = await fetch_node(slug)
    if not node:
        await m.answer("Раздел не найден.")
        return
    buttons = await fetch_buttons(slug)
    if buttons:
        btn_lines = [
            f"#{btn.id} | {btn.label} | {btn.action_type}:{btn.target} | pos={btn.position}"
            for btn in buttons
        ]
        btn_text = "\n".join(btn_lines)
    else:
        btn_text = "(кнопок нет)"
    await m.answer(f"{node.text}\n\nКнопки:\n{btn_text}")


@dp.message(F.text.startswith("/addnode "))
async def add_node(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer("Формат: /addnode <slug> <text>")
        return
    slug, text = parts[1].strip(), parts[2].strip()
    assert POOL is not None
    async with POOL.acquire() as conn:
        try:
            await conn.execute("INSERT INTO nodes (slug, text) VALUES ($1, $2)", slug, text)
        except asyncpg.UniqueViolationError:
            await m.answer("Раздел с таким slug уже существует.")
            return
    await m.answer(f"Раздел {slug} создан.")


@dp.message(F.text.startswith("/delnode "))
async def del_node(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    slug = m.text.split(maxsplit=1)[1].strip()
    if slug == "root":
        await m.answer("Нельзя удалить root.")
        return
    assert POOL is not None
    async with POOL.acquire() as conn:
        res = await conn.execute("DELETE FROM nodes WHERE slug=$1", slug)
    if res.endswith("0"):
        await m.answer("Раздел не найден.")
        return
    await m.answer(f"Раздел {slug} удалён.")


@dp.message(F.text.startswith("/settext "))
async def set_text(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer("Формат: /settext <slug> <text>")
        return
    slug, text = parts[1].strip(), parts[2].strip()
    assert POOL is not None
    async with POOL.acquire() as conn:
        res = await conn.execute("UPDATE nodes SET text=$1 WHERE slug=$2", text, slug)
    if res.endswith("0"):
        await m.answer("Раздел не найден.")
        return
    await m.answer("Текст обновлён.")


def parse_button_payload(raw: str) -> Optional[tuple[str, str, str, Optional[int]]]:
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 3:
        return None
    label = parts[0]
    target_raw = parts[1]
    position = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if target_raw.startswith("node:"):
        return (label, "node", target_raw[5:], position)
    if target_raw.startswith("url:"):
        return (label, "url", target_raw[4:], position)
    return None


@dp.message(F.text.startswith("/addbtn "))
async def add_btn(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    raw = m.text[len("/addbtn ") :].strip()
    slug_split = raw.split(" ", 1)
    if len(slug_split) < 2:
        await m.answer("Формат: /addbtn <slug> <label> | <node:slug|url:https://...> | [position]")
        return
    slug, rest = slug_split[0].strip(), slug_split[1].strip()
    payload = parse_button_payload(rest)
    if not payload:
        await m.answer("Неверный формат кнопки.")
        return
    label, action_type, target, position = payload
    assert POOL is not None
    async with POOL.acquire() as conn:
        node_id = await conn.fetchval("SELECT id FROM nodes WHERE slug=$1", slug)
        if not node_id:
            await m.answer("Раздел не найден.")
            return
        if action_type == "node":
            target_exists = await conn.fetchval("SELECT 1 FROM nodes WHERE slug=$1", target)
            if not target_exists:
                await m.answer("Целевой раздел не найден.")
                return

        await ensure_button(conn, node_id, label, action_type, target, position or 0)

    await m.answer("Кнопка добавлена/обновлена.")


@dp.message(F.text.startswith("/setbtn "))
async def set_btn(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    raw = m.text[len("/setbtn ") :].strip()
    parts = raw.split(" ", 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await m.answer("Формат: /setbtn <id> <label> | <node:slug|url:https://...> | [position]")
        return
    btn_id = int(parts[0])
    payload = parse_button_payload(parts[1])
    if not payload:
        await m.answer("Неверный формат кнопки.")
        return
    label, action_type, target, position = payload
    assert POOL is not None
    async with POOL.acquire() as conn:
        if action_type == "node":
            target_exists = await conn.fetchval("SELECT 1 FROM nodes WHERE slug=$1", target)
            if not target_exists:
                await m.answer("Целевой раздел не найден.")
                return
        res = await conn.execute(
            """
            UPDATE buttons
            SET label=$1, action_type=$2, target=$3, position=$4
            WHERE id=$5
            """,
            label,
            action_type,
            target,
            position or 0,
            btn_id,
        )
    if res.endswith("0"):
        await m.answer("Кнопка не найдена.")
        return
    await m.answer("Кнопка обновлена.")


@dp.message(F.text.startswith("/delbtn "))
async def del_btn(m: Message) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await m.answer("Формат: /delbtn <id>")
        return
    btn_id = int(parts[1])
    assert POOL is not None
    async with POOL.acquire() as conn:
        res = await conn.execute("DELETE FROM buttons WHERE id=$1", btn_id)
    if res.endswith("0"):
        await m.answer("Кнопка не найдена.")
        return
    await m.answer("Кнопка удалена.")


@dp.message(F.text == "❌ Сброс")
async def admin_reset_text(m: Message, state: FSMContext) -> None:
    if not m.from_user or not is_owner(m.from_user.id):
        return
    await state.clear()
    await m.answer("Готово, сбросила шаги.", reply_markup=ReplyKeyboardRemove())


async def main() -> None:
    global POOL
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Set it in environment variables.")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is empty. Set it in environment variables.")
    if OWNER_ID == 0:
        raise RuntimeError("OWNER_ID is empty. Set it in environment variables.")

    POOL = await asyncpg.create_pool(DATABASE_URL)
    await init_db()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())


