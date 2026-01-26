import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ================== ENV ==================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
OWNER_ID = int((os.getenv("OWNER_ID", "0") or "0").strip())
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

CONSULT_FORM_URL_ENV = (os.getenv("CONSULTATION_FORM_URL") or "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty.")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is empty.")
if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID is empty/0. Set OWNER_ID in env vars.")

# ================== CONSTANTS (fallback) ==================
PRO_CONTACT_FALLBACK = "ilya_bolsheglazov"
HELP_CONTACT_FALLBACK = "yashiann"
CHANNEL_URL_FALLBACK = "https://t.me/ozonbluerise"

# ================== DATA ==================
@dataclass(frozen=True)
class Course:
    title: str
    description: str
    link: str
    invoice_text: str


BEGINNER_COURSE = Course(
    title="Грамотный старт на Озон",
    description=(
        "«Грамотный старт на Озон» — для селлеров и менеджеров, которые делают первые "
        "шаги в Озон и хотят начать уверенно разбираться во всех основных вещах, "
        "необходимых для ведения прибыльного бизнеса."
    ),
    link="https://bluerise.getcourse.ru/GSO_VC",
    invoice_text="Здравствуйте, мне нужен счет для оплаты курса «Грамотный старт на Озон».",
)

ADVANCED_COURSES = {
    "pro_logistics": Course(
        title="PRO логистику",
        description=(
            "Курс PRO логистику для тех, кто хочет снизить СВД в своем кабинете, понимать "
            "сколько товара грузить в каждый кластер и понять, как не переплачивать за логистику."
        ),
        link="https://bluerise.getcourse.ru/PRO_logistics",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO логистику».",
    ),
    "pro_ads": Course(
        title="PRO рекламу",
        description=(
            "Курс PRO рекламу — для тех, кто хочет оптимизировать свои рекламные расходы, "
            "научиться выстраивать рекламные стратегии и понимать, какими инструментами "
            "продвижения пользоваться для разных типов товаров и в различных ситуациях."
        ),
        link="https://bluerise.getcourse.ru/PRO_Reklamu",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO рекламу».",
    ),
    "pro_analytics": Course(
        title="PRO Аналитику",
        description=(
            "Курс PRO Аналитику — для тех, кто хочет изучить все значимые нюансы и все "
            "инструменты, которые необходимы для анализа."
        ),
        link="https://bluerise.getcourse.ru/PRO_Analytics",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Аналитик».",
    ),
    "pro_finance": Course(
        title="PRO Финансы",
        description=(
            "Курс «PRO Финансы» — для тех, кто хочет научиться считать юнит-план и юнит-факт, "
            "ROI и маржинальность. Разбираться в финансовых отчетах Озона, иметь представление "
            "о кредитных инструментах."
        ),
        link="https://bluerise.getcourse.ru/PRO_Finance",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Финансы».",
    ),
    "all_about_ozon": Course(
        title="Всё про Озон",
        description=(
            "Все 4 блока курсов PRO логистику, PRO рекламу, PRO аналитику, PRO финансы "
            "в одном со скидкой 20%."
        ),
        link="https://bluerise.getcourse.ru/all_about_ozon",
        invoice_text="Здравствуйте, мне нужен счет для оплаты комплекта «Всё про Озон».",
    ),
}

SPECIAL_COURSES = {
    "pro_design": Course(
        title="PRO Дизайн",
        description=(
            "Курс «PRO Дизайн» — для тех, кто хочет понять принципы продающей инфографики, "
            "уберечь себя от ошибок в дизайне карточек товара, которые ведут к снижению CTR, "
            "научиться выстраивать взаимоотношения с дизайнерами и «считывать» их квалификацию."
        ),
        link="https://bluerise.getcourse.ru/PRO_design",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Дизайн».",
    ),
    "sxr_ai": Course(
        title="Нейросети от SXR Studio",
        description=(
            "Курс по нейросетям от SXR Studio для тех, кто смотрит в будущее и хочет "
            "научиться генерировать нейро-контент для своих карточек товара."
        ),
        link="https://bluerise.getcourse.ru/SXR_AI",
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «Нейросети от SXR Studio».",
    ),
}


def tg_link(username: str, text: str) -> str:
    return f"https://t.me/{username}?text={quote(text)}"


# ================== DB ==================
pool: Optional[asyncpg.Pool] = None


async def db_init() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_kv (
              key TEXT PRIMARY KEY,
              value JSONB NOT NULL
            );
            """
        )


async def kv_get(key: str) -> Optional[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_kv WHERE key=$1", key)
        if not row:
            return None
        return dict(row["value"])


async def kv_set(key: str, value: Dict[str, Any]) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_kv(key, value)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
            """,
            key,
            json.dumps(value, ensure_ascii=False),
        )


# ================== CONFIG ==================
CFG_KEY = "ui_config_v1"

def default_cfg() -> Dict[str, Any]:
    """
    reply_buttons: тексты reply-кнопок (внизу)
    meta: ссылки/контакты
    inline: inline-секции (списки кнопок)
      - callback-кнопки: type="callback", value="courses:pre" и т.п. (value НЕ редактируем в панели)
      - url-кнопки: type="url", value="https://..." (value редактируем)
    """
    channel_url = CHANNEL_URL_FALLBACK
    consult_url = CONSULT_FORM_URL_ENV  # если есть из окружения

    return {
        "reply_buttons": {
            "courses": "Наши курсы",
            "calc": "Калькулятор OZON/ЯМ",
            "partnership": "Сотрудничество",
            "consult": "Личная консультация",
            "owner": "⚙️ Панель владельца",
        },
        "meta": {
            "channel_url": channel_url,
            "consult_form_url": consult_url,
            "pro_contact": PRO_CONTACT_FALLBACK,
            "help_contact": HELP_CONTACT_FALLBACK,
            "webinar_url": "https://bluerise.getcourse.ru/teach/control/stream/view/id/934642226",
            "calc_url": "https://docs.google.com/spreadsheets/d/1e4AVf3dDueEoPxQHeKOVFHgSpbcLvnbGnn6_I6ApRwg/edit?gid=246238448#gid=246238448",
        },
        "inline": {
            "courses_menu": [
                {"id": "pre", "text": "📚 Предзаписанные курсы", "type": "callback", "value": "courses:pre"},
                {"id": "new", "text": "🆕 Новинки и потоки", "type": "callback", "value": "courses:new"},
                {"id": "webinars", "text": "🔶 Бесплатные вебинары по ЯМ", "type": "callback", "value": "courses:webinars"},
                {"id": "help", "text": "❓ Помощь с выбором курса", "type": "callback", "value": "courses:help"},
                {"id": "support", "text": "🛠️ Техническая поддержка", "type": "callback", "value": "courses:support"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "courses:back"},
            ],
            "pre_courses": [
                {"id": "beginner", "text": "🚀 Ozon: Начальный уровень", "type": "callback", "value": "pre:beginner"},
                {"id": "advanced", "text": "⚡ Ozon: Продвинутый уровень", "type": "callback", "value": "pre:advanced"},
                {"id": "special", "text": "🛠️ Спецкурсы и инструменты", "type": "callback", "value": "pre:special"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "pre:back"},
            ],
            "advanced_courses": [
                {"id": "pro_logistics", "text": "PRO логистику", "type": "callback", "value": "advanced:pro_logistics"},
                {"id": "pro_ads", "text": "PRO рекламу", "type": "callback", "value": "advanced:pro_ads"},
                {"id": "pro_analytics", "text": "PRO Аналитику", "type": "callback", "value": "advanced:pro_analytics"},
                {"id": "pro_finance", "text": "PRO Финансы", "type": "callback", "value": "advanced:pro_finance"},
                {"id": "all_about_ozon", "text": "Всё про Озон", "type": "callback", "value": "advanced:all_about_ozon"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "pre:back"},
            ],
            "special_courses": [
                {"id": "pro_design", "text": "PRO Дизайн", "type": "callback", "value": "special:pro_design"},
                {"id": "sxr_ai", "text": "Нейросети от SXR Studio", "type": "callback", "value": "special:sxr_ai"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "pre:back"},
            ],
            "help": [
                {"id": "write", "text": "Написать в поддержку", "type": "url", "value": "tg://help_contact"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "courses:back"},
            ],
            "tech_support": [
                {"id": "write", "text": "Написать в поддержку", "type": "url", "value": "tg://pro_contact"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "courses:back"},
            ],
            "webinars": [
                {"id": "webinar", "text": "Вебинар тут", "type": "url", "value": "meta://webinar_url"},
                {"id": "channel", "text": "Подписаться на канал", "type": "url", "value": "meta://channel_url"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "courses:back"},
            ],
            "new_courses": [
                {"id": "pre", "text": "📚 Предзаписанные курсы", "type": "callback", "value": "courses:pre"},
                {"id": "channel", "text": "Подписаться на канал", "type": "url", "value": "meta://channel_url"},
                {"id": "back", "text": "↩️ Назад", "type": "callback", "value": "courses:back"},
            ],
            "calculator": [
                {"id": "calc", "text": "Калькулятор здесь", "type": "url", "value": "meta://calc_url"},
                {"id": "channel", "text": "Подписаться на канал", "type": "url", "value": "meta://channel_url"},
            ],
            "consult": [
                {"id": "form", "text": "📅 ЗАПОЛНИТЬ ЗАЯВКУ", "type": "url", "value": "meta://consult_form_url"},
            ],
        },
    }


_CFG_CACHE: Optional[Dict[str, Any]] = None


async def cfg_load() -> Dict[str, Any]:
    global _CFG_CACHE
    if _CFG_CACHE is not None:
        return _CFG_CACHE
    data = await kv_get(CFG_KEY)
    if not data:
        data = default_cfg()
        await kv_set(CFG_KEY, data)
    _CFG_CACHE = data
    return data


async def cfg_save(cfg: Dict[str, Any]) -> None:
    global _CFG_CACHE
    await kv_set(CFG_KEY, cfg)
    _CFG_CACHE = cfg


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ================== KEYBOARDS ==================
def main_menu_kb(cfg: Dict[str, Any], user_id: int) -> ReplyKeyboardMarkup:
    rb = cfg["reply_buttons"]
    rows = [
        [KeyboardButton(text=rb["courses"])],
        [KeyboardButton(text=rb["calc"])],
        [KeyboardButton(text=rb["partnership"])],
        [KeyboardButton(text=rb["consult"])],
    ]
    if is_owner(user_id):
        rows.append([KeyboardButton(text=rb["owner"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def resolve_url(cfg: Dict[str, Any], value: str) -> str:
    if value.startswith("meta://"):
        key = value.split("meta://", 1)[1]
        return (cfg.get("meta", {}).get(key) or "").strip()

    if value == "tg://help_contact":
        username = (cfg["meta"].get("help_contact") or HELP_CONTACT_FALLBACK).strip()
        return tg_link(username, "Добрый день. Помогите с выбором курса.")

    if value == "tg://pro_contact":
        username = (cfg["meta"].get("pro_contact") or PRO_CONTACT_FALLBACK).strip()
        return tg_link(username, "Добрый день. Возникла техническая проблема: [опишите, пожалуйста].")

    return value


def inline_kb(cfg: Dict[str, Any], section: str) -> InlineKeyboardMarkup:
    items = cfg["inline"].get(section, [])
    rows: List[List[InlineKeyboardButton]] = []

    for b in items:
        b_type = b.get("type")
        text = b.get("text", "—")
        val = b.get("value", "")

        if b_type == "callback":
            rows.append([InlineKeyboardButton(text=text, callback_data=val)])
        elif b_type == "url":
            url = resolve_url(cfg, val)
            rows.append([InlineKeyboardButton(text=text, url=url)])
        else:
            rows.append([InlineKeyboardButton(text=text, callback_data="noop")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def course_actions_kb(cfg: Dict[str, Any], course: Course) -> InlineKeyboardMarkup:
    pro_contact = (cfg["meta"].get("pro_

