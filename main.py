import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

BTN_COURSES = "Наши курсы"
BTN_CALC = "Калькулятор OZON/ЯМ"
BTN_PARTNERSHIP = "Сотрудничество"
BTN_CONSULT = "Личная консультация"

CHANNEL_URL = "https://t.me/ozonbluerise"
CONSULT_FORM_URL = os.getenv("CONSULTATION_FORM_URL")

PRO_CONTACT = "ilya_bolsheglazov"
HELP_CONTACT = "yashiann"


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
        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Аналитику».",
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


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_COURSES)],
            [KeyboardButton(text=BTN_CALC)],
            [KeyboardButton(text=BTN_PARTNERSHIP)],
            [KeyboardButton(text=BTN_CONSULT)],
        ],
        resize_keyboard=True,
    )


def courses_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Предзаписанные курсы", callback_data="courses:pre")],
            [InlineKeyboardButton(text="🆕 Новинки и потоки", callback_data="courses:new")],
            [InlineKeyboardButton(text="🔶 Бесплатные вебинары по ЯМ", callback_data="courses:webinars")],
            [InlineKeyboardButton(text="❓ Помощь с выбором курса", callback_data="courses:help")],
            [InlineKeyboardButton(text="🛠️ Техническая поддержка", callback_data="courses:support")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
        ]
    )


def pre_courses_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Ozon: Начальный уровень", callback_data="pre:beginner")],
            [InlineKeyboardButton(text="⚡ Ozon: Продвинутый уровень", callback_data="pre:advanced")],
            [InlineKeyboardButton(text="🛠️ Спецкурсы и инструменты", callback_data="pre:special")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
        ]
    )


def course_actions_kb(course: Course) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Узнать подробности и купить курс",
                    url=course.link,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Выставить счет для оплаты с р/с",
                    url=tg_link(PRO_CONTACT, course.invoice_text),
                )
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
        ]
    )


def advanced_courses_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="PRO логистику", callback_data="advanced:pro_logistics")],
            [InlineKeyboardButton(text="PRO рекламу", callback_data="advanced:pro_ads")],
            [InlineKeyboardButton(text="PRO Аналитику", callback_data="advanced:pro_analytics")],
            [InlineKeyboardButton(text="PRO Финансы", callback_data="advanced:pro_finance")],
            [InlineKeyboardButton(text="Всё про Озон", callback_data="advanced:all_about_ozon")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
        ]
    )


def special_courses_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="PRO Дизайн", callback_data="special:pro_design")],
            [InlineKeyboardButton(text="Нейросети от SXR Studio", callback_data="special:sxr_ai")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
        ]
    )


def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать в поддержку",
                    url=tg_link(HELP_CONTACT, "Добрый день. Помогите с выбором курса."),
                )
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
        ]
    )


def tech_support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать в поддержку",
                    url=tg_link(
                        PRO_CONTACT,
                        "Добрый день. Возникла техническая проблема: [опишите, пожалуйста].",
                    ),
                )
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
        ]
    )


def webinars_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Вебинар тут",
                    url="https://bluerise.getcourse.ru/teach/control/stream/view/id/934642226",
                )
            ],
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
        ]
    )


def new_courses_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Предзаписанные курсы", callback_data="courses:pre")],
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
        ]
    )


def calculator_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Калькулятор здесь",
                    url="https://docs.google.com/spreadsheets/d/1e4AVf3dDueEoPxQHeKOVFHgSpbcLvnbGnn6_I6ApRwg/edit?gid=246238448#gid=246238448",
                )
            ],
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
        ]
    )


def consult_kb() -> Optional[InlineKeyboardMarkup]:
    if not CONSULT_FORM_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 ЗАПОЛНИТЬ ЗАЯВКУ", url=CONSULT_FORM_URL)]
        ]
    )


dp = Dispatcher()


@dp.message(CommandStart())
async def start(m: Message) -> None:
    name = m.from_user.first_name if m.from_user else "друг"
    await m.answer(
        f"Приветствую, {name}!\n\n"
        "Это «Синий рассвет» — здесь мы систематизируем бизнес на маркетплейсах: "
        "от основ до продвинутых стратегий.",
        reply_markup=main_menu_kb(),
    )


@dp.message(F.text == BTN_COURSES)
async def courses_menu(m: Message) -> None:
    await m.answer("Выберите раздел 👇", reply_markup=courses_menu_kb())


@dp.callback_query(F.data == "courses:back")
async def courses_back(c: CallbackQuery) -> None:
    await c.message.answer("Главное меню 👇", reply_markup=main_menu_kb())
    await c.answer()


@dp.callback_query(F.data == "courses:pre")
async def pre_courses(c: CallbackQuery) -> None:
    text = (
        "Все курсы в нашей линейке предзаписанные и с постоянными апдейтами под изменения в Озон.\n\n"
        "Не надо ждать потоков, курс идет по принципу «Купи и смотри». Доступ к нему и ко всем его "
        "изменениям остается навсегда.\n\n"
        "Вся линейка курсов задумана, как постоянно обновляемая База Знаний, с помощью которых вы "
        "сможете обучать новых сотрудников и постоянно актуализировать свои знания. Доступ ко всем "
        "обновлениям купленного курса БЕСПЛАТНЫЙ."
    )
    await c.message.answer(text, reply_markup=pre_courses_kb())
    await c.answer()


@dp.callback_query(F.data == "pre:beginner")
async def pre_beginner(c: CallbackQuery) -> None:
    await c.message.answer(
        f"<b>{BEGINNER_COURSE.title}</b>\n\n{BEGINNER_COURSE.description}",
        reply_markup=course_actions_kb(BEGINNER_COURSE),
        parse_mode=ParseMode.HTML,
    )
    await c.answer()


@dp.callback_query(F.data == "pre:advanced")
async def pre_advanced(c: CallbackQuery) -> None:
    await c.message.answer(
        "Продвинутый уровень: выберите курс 👇",
        reply_markup=advanced_courses_kb(),
    )
    await c.answer()


@dp.callback_query(F.data == "pre:special")
async def pre_special(c: CallbackQuery) -> None:
    await c.message.answer(
        "Спецкурсы и инструменты: выберите курс 👇",
        reply_markup=special_courses_kb(),
    )
    await c.answer()


@dp.callback_query(F.data == "pre:back")
async def pre_back(c: CallbackQuery) -> None:
    await c.message.answer("Наши курсы 👇", reply_markup=courses_menu_kb())
    await c.answer()


@dp.callback_query(F.data.startswith("advanced:"))
async def advanced_course(c: CallbackQuery) -> None:
    key = c.data.split(":", 1)[1]
    course = ADVANCED_COURSES.get(key)
    if not course:
        await c.answer("Курс не найден.", show_alert=True)
        return
    await c.message.answer(
        f"<b>{course.title}</b>\n\n{course.description}",
        reply_markup=course_actions_kb(course),
        parse_mode=ParseMode.HTML,
    )
    await c.answer()


@dp.callback_query(F.data.startswith("special:"))
async def special_course(c: CallbackQuery) -> None:
    key = c.data.split(":", 1)[1]
    course = SPECIAL_COURSES.get(key)
    if not course:
        await c.answer("Курс не найден.", show_alert=True)
        return
    await c.message.answer(
        f"<b>{course.title}</b>\n\n{course.description}",
        reply_markup=course_actions_kb(course),
        parse_mode=ParseMode.HTML,
    )
    await c.answer()


@dp.callback_query(F.data == "courses:new")
async def courses_new(c: CallbackQuery) -> None:
    text = (
        "Здесь будут появляться анонсы новых курсов и специальных форматов обучения.\n\n"
        "Мы регулярно работаем над тем, чтобы обучение было еще полезнее и эффективнее. "
        "Возможно, это будут обновленные программы или новые проекты.\n\n"
        "Хотите быть в курсе всех новинок первыми?\n"
        f"👉 Подпишитесь на наш канал: {CHANNEL_URL}\n\n"
        "А пока все наши основные курсы для старта и уверенного роста уже ждут вас в "
        "📚 Предзаписанные курсы."
    )
    await c.message.answer(text, reply_markup=new_courses_kb())
    await c.answer()


@dp.callback_query(F.data == "courses:webinars")
async def courses_webinars(c: CallbackQuery) -> None:
    text = (
        "Поздравляю! Вам открыт доступ к вебинарам по Яндекс маркету.\n\n"
        "Что вы получите внутри:\n"
        "1. Запись 3-х дней вебинаров по ЯМ, в которых разобраны все аспекты работы с площадкой.\n"
        "2. Ссылка на чат единомышленников.\n\n"
        "Кстати, подписывайтесь на мой канал «Синий рассвет» — там куча полезной информации "
        "по Озон и про бизнес на маркетплейсах в целом."
    )
    await c.message.answer(text, reply_markup=webinars_kb())
    await c.answer()


@dp.callback_query(F.data == "courses:help")
async def courses_help(c: CallbackQuery) -> None:
    text = (
        "Чтобы подобрать курс, который решит именно вашу задачу, напишите напрямую "
        "@yashiann. Опишите ваш опыт и цель — и вы получите персональную рекомендацию."
    )
    await c.message.answer(text, reply_markup=help_kb())
    await c.answer()


@dp.callback_query(F.data == "courses:support")
async def courses_support(c: CallbackQuery) -> None:
    text = (
        "По любым техническим вопросам (доступ к курсам, проблемы с оплатой) "
        "напишите напрямую @ilya_bolsheglazov. Опишите проблему как можно подробнее — "
        "это поможет решить её быстрее."
    )
    await c.message.answer(text, reply_markup=tech_support_kb())
    await c.answer()


@dp.message(F.text == BTN_CALC)
async def calculator(m: Message) -> None:
    text = (
        "Поздравляю! Вам открыт доступ к обновленному калькулятору.\n\n"
        "Что вы получите внутри:\n"
        "1. Калькулятор с FBS и новой логистикой.\n"
        "2. Подробное видеообъяснение к калькулятору: как пользоваться, что ввести, на что смотреть.\n\n"
        "Кстати, подписывайтесь на мой канал «Синий рассвет». Там куча полезной информации по Озон "
        "и про бизнес на маркетплейсах в целом."
    )
    await m.answer(text, reply_markup=calculator_kb())


@dp.message(F.text == BTN_PARTNERSHIP)
async def partnership(m: Message) -> None:
    text = (
        "Привет! 👋\n\n"
        "Этот раздел — для обсуждения профессионального партнёрства. Мы открыты к совместным "
        "проектам, интеграциям, аффилированным программам и другим форматам взаимовыгодого "
        "сотрудничества.\n\n"
        "Чтобы предложить свою идею, напишите напрямую @yashiann в Telegram. В первом сообщении "
        "кратко опишите суть предложения — это поможет начать диалог максимально предметно.\n\n"
        "Жду вашего сообщения! 🤝"
    )
    await m.answer(text, reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == BTN_CONSULT)
async def consult(m: Message) -> None:
    text = (
        "Индивидуальный разбор вашего кейса. Мы проанализируем текущую ситуацию, определим точки "
        "роста и сформируем план на ближайший период.\n\n"
        "Формат и продолжительность консультации определяются под ваш запрос.\n\n"
        "Для записи заполните, пожалуйста, форму. Это поможет подготовиться к нашей встрече."
    )
    kb = consult_kb()
    if kb:
        await m.answer(text, reply_markup=kb)
        return
    await m.answer(
        f"{text}\n\nСсылка на форму пока не указана. Добавьте CONSULTATION_FORM_URL в окружение.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message()
async def fallback(m: Message) -> None:
    await m.answer("Используйте меню ниже 👇", reply_markup=main_menu_kb())


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Set it in environment variables.")

    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
