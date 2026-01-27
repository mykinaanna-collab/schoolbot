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
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")

DEFAULT_ROOT_TEXT = (
    "Приветствую, {name}!\n\n"
    "Это «Синий рассвет» — здесь мы систематизируем бизнес на маркетплейсах: "
    "от основ до продвинутых стратегий."
)

dp = Dispatcher()
POOL: Optional[asyncpg.Pool] = None


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

        root = await conn.fetchrow("SELECT id FROM nodes WHERE slug='root'")
        if not root:
            root_id = await conn.fetchval(
                "INSERT INTO nodes (slug, text) VALUES ($1, $2) RETURNING id",
                "root",
                DEFAULT_ROOT_TEXT.format(name="друг"),
            )
            await seed_default_nodes(conn, root_id)


async def seed_default_nodes(conn: asyncpg.Connection, root_id: int) -> None:
    nodes = [
        ("courses", "Выберите раздел 👇"),
        (
            "calculator",
            "Поздравляю! Вам открыт доступ к обновленному калькулятору.\n\n"
            "Что вы получите внутри:\n"
            "1. Калькулятор с FBS и новой логистикой.\n"
            "2. Подробное видеообъяснение к калькулятору: как пользоваться, что ввести, "
            "на что смотреть.\n\n"
            "Кстати, подписывайтесь на мой канал «Синий рассвет». Там куча полезной "
            "информации по Озон и про бизнес на маркетплейсах в целом.",
        ),
        (
            "partnership",
            "Привет! 👋\n\n"
            "Этот раздел — для обсуждения профессионального партнёрства. Мы открыты к "
            "совместным проектам, интеграциям, аффилированным программам и другим форматам "
            "взаимовыгодного сотрудничества.\n\n"
            "Чтобы предложить свою идею, напишите напрямую @yashiann в Telegram. В первом "
            "сообщении крако опишите суть предложения — это поможет начать диалог максимально "
            "предметно.\n\n"
            "Жду вашего сообщения! 🤝",
        ),
        (
            "consult",
            "Индивидуальный разбор вашего кейса. Мы проанализируем текущую ситуацию, "
            "определим точки роста и сформируем план на ближайший период.\n\n"
            "Формат и продолжительность консультации определяются под ваш запрос.\n\n"
            "Для записи заполните, пожалуйста, форму. Это поможет подготовиться к нашей встрече.",
        ),
    ]

    node_ids = {}
    for slug, text in nodes:
        node_id = await conn.fetchval(
            "INSERT INTO nodes (slug, text) VALUES ($1, $2) RETURNING id",
            slug,
            text,
        )
        node_ids[slug] = node_id

    await conn.executemany(
        """
        INSERT INTO buttons (node_id, label, action_type, target, position)
        VALUES ($1, $2, $3, $4, $5)
        """,
        [
            (root_id, "Наши курсы", "node", "courses", 1),
            (root_id, "Калькулятор OZON/ЯМ", "node", "calculator", 2),
            (root_id, "Сотрудничество", "node", "partnership", 3),
            (root_id, "Личная консультация", "node", "consult", 4),
            (
                node_ids["calculator"],
                "Калькулятор здесь",
                "url",
                "https://docs.google.com/spreadsheets/d/1e4AVf3dDueEoPxQHeKOVFHgSpbcLvnbGnn6_I6ApRwg/edit?gid=246238448#gid=246238448",
                1,
            ),
            (
                node_ids["calculator"],
                "Подписаться на канал",
                "url",
                "https://t.me/ozonbluerise",
                2,
            ),
            (
                node_ids["consult"],
                "📅 ЗАПОЛНИТЬ ЗАЯВКУ",
                "url",
                "https://example.com",
                1,
            ),
        ],
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


def build_kb(buttons: Iterable[Button]) -> Optional[InlineKeyboardMarkup]:
    rows: list[list[InlineKeyboardButton]] = []
    for btn in buttons:
        if btn.action_type == "url":
            rows.append([InlineKeyboardButton(text=btn.label, url=btn.target)])
        else:
            rows.append(
                [InlineKeyboardButton(text=btn.label, callback_data=f"node:{btn.target}")]
            )
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def start(m: Message) -> None:
    name = m.from_user.first_name if m.from_user else "друг"
    node = await fetch_node("root")
    if not node:
        await m.answer("Меню ещё не настроено.")
        return
    text = node.text.replace("{name}", name)
    buttons = await fetch_buttons("root")
    await m.answer(text, reply_markup=build_kb(buttons))


@dp.callback_query(F.data.startswith("node:"))
async def cb_node(c: CallbackQuery) -> None:
    slug = c.data.split(":", 1)[1]
    node = await fetch_node(slug)
    if not node:
        await c.answer("Раздел не найден.", show_alert=True)
        return
    buttons = await fetch_buttons(slug)
    await c.message.answer(node.text, reply_markup=build_kb(buttons))
    await c.answer()


@dp.message(F.text == "/admin")
async def admin_help(m: Message) -> None:
    if not is_owner(m.from_user.id):
        return
    await m.answer(
        "Админ-команды:\n"
        "/nodes — список разделов\n"
        "/node <slug> — показать раздел и кнопки\n"
        "/addnode <slug> <text> — создать раздел\n"
        "/delnode <slug> — удалить раздел\n"
        "/settext <slug> <text> — обновить текст раздела\n"
        "/addbtn <slug> <label> | <node:slug|url:https://...> | [position]\n"
        "/setbtn <id> <label> | <node:slug|url:https://...> | [position]\n"
        "/delbtn <id> — удалить кнопку",
    )


@dp.message(F.text == "/nodes")
async def list_nodes(m: Message) -> None:
    if not is_owner(m.from_user.id):
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
    if not is_owner(m.from_user.id):
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
    if not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer("Формат: /addnode <slug> <text>")
        return
    slug, text = parts[1].strip(), parts[2].strip()
    assert POOL is not None
    async with POOL.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO nodes (slug, text) VALUES ($1, $2)", slug, text
            )
        except asyncpg.UniqueViolationError:
            await m.answer("Раздел с таким slug уже существует.")
            return
    await m.answer(f"Раздел {slug} создан.")


@dp.message(F.text.startswith("/delnode "))
async def del_node(m: Message) -> None:
    if not is_owner(m.from_user.id):
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
    await m.answer(f"Радел {slug} удалён.")


@dp.message(F.text.startswith("/settext "))
async def set_text(m: Message) -> None:
    if not is_owner(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.answer("Формат: /settext <slug> <text>")
        return
    slug, text = parts[1].strip(), parts[2].strip()
    assert POOL is not None
    async with POOL.acquire() as conn:
        res = await conn.execute(
            "UPDATE nodes SET text=$1 WHERE slug=$2", text, slug
        )
    if res.endswith("0"):
        await m.answer("Раздел не найден.")
        return
    await m.answer("Текст обновлён.")


def parse_button_payload(raw: str) -> Optional[tuple[str, str, Optional[int]]]:
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
    if not is_owner(m.from_user.id):
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
            target_exists = await conn.fetchval(
                "SELECT 1 FROM nodes WHERE slug=$1", target
            )
            if not target_exists:
                await m.answer("Целевой раздел не найден.")
                return
        await conn.execute(
            """
            INSERT INTO buttons (node_id, label, action_type, target, position)
            VALUES ($1, $2, $3, $4, $5)
            """,
            node_id,
            label,
            action_type,
            target,
            position or 0,
        )
    await m.answer("Кнопка добавлена.")


@dp.message(F.text.startswith("/setbtn "))
async def set_btn(m: Message) -> None:
    if not is_owner(m.from_user.id):
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
            target_exists = await conn.fetchval(
                "SELECT 1 FROM nodes WHERE slug=$1", target
            )
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
    if not is_owner(m.from_user.id):
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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

