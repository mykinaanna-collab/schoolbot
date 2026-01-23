 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/main.py b/main.py
index 71c2a9ed50822a4849cf835f5d3ae01fe48625dc..527e674a40585a9ebcdbe3e437b8eccd34ca9ebc 100644
--- a/main.py
+++ b/main.py
@@ -1,1315 +1,508 @@
- (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
-diff --git a/main.py b/main.py
-index be958a3dd94ca45df54ad1878a42e369af589cfd..5f7727a1414d33ec70158996867a4668c7b62be9 100644
---- a/main.py
-+++ b/main.py
-@@ -224,78 +224,89 @@ async def init_db() -> None:
-                 text TEXT NOT NULL,
-                 buttons_json TEXT NOT NULL,
-                 photo_file_id TEXT,
-                 run_at TIMESTAMPTZ NOT NULL,
-                 created_by BIGINT NOT NULL,
-                 created_at TIMESTAMPTZ DEFAULT NOW()
-             );
-         """)
- 
-         await conn.execute("""
-             CREATE TABLE IF NOT EXISTS posts (
-                 id TEXT PRIMARY KEY,
-                 channel_id TEXT NOT NULL,
-                 message_id BIGINT NOT NULL,
-                 text_msg_id BIGINT,
-                 text TEXT NOT NULL,
-                 buttons_json TEXT NOT NULL,
-                 photo_file_id TEXT,
-                 created_by BIGINT NOT NULL,
-                 created_at TIMESTAMPTZ DEFAULT NOW()
-             );
-         """)
- 
-         # OWNER is admin
-         if OWNER_ID:
-+            await conn.execute(
-+                "UPDATE admins SET name=NULL WHERE name='OWNER' AND user_id<>$1",
-+                OWNER_ID,
-+            )
-             await conn.execute("""
-                 INSERT INTO admins (user_id, username, name)
-                 VALUES ($1, NULL, 'OWNER')
--                ON CONFLICT (user_id) DO NOTHING;
-+                ON CONFLICT (user_id) DO UPDATE
-+                SET name=EXCLUDED.name;
-             """, OWNER_ID)
- 
-         # Seed ENV admins
-         for uid in ENV_ADMINS:
-             if uid == OWNER_ID:
-                 continue
-             await conn.execute("""
-                 INSERT INTO admins (user_id, username, name)
-                 VALUES ($1, NULL, NULL)
-                 ON CONFLICT (user_id) DO NOTHING;
-             """, uid)
- 
- 
- async def db_is_admin(user_id: int) -> bool:
-     assert POOL is not None
-     async with POOL.acquire() as conn:
-         row = await conn.fetchrow("SELECT user_id FROM admins WHERE user_id=$1", user_id)
-         return row is not None
- 
- 
- def is_owner(user_id: int) -> bool:
-     return user_id == OWNER_ID
- 
- 
-+async def is_admin(user_id: int) -> bool:
-+    if is_owner(user_id):
-+        return True
-+    return await db_is_admin(user_id)
-+
-+
- def admin_display(row: asyncpg.Record) -> str:
-     uid = row["user_id"]
-     username = row["username"]
-     name = row["name"]
-     if username:
-         return f"@{username} ({uid})"
-     if name:
-         return f"{name} ({uid})"
-     return str(uid)
- 
- 
- # ================== INLINE CONTROLS ==================
- def post_controls_kb(post_id: str) -> InlineKeyboardMarkup:
-     return InlineKeyboardMarkup(inline_keyboard=[
-         [
-             InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post:edit:{post_id}"),
-             InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post:del:{post_id}"),
-         ]
-     ])
- 
- 
- def post_delete_confirm_kb(post_id: str) -> InlineKeyboardMarkup:
-     return InlineKeyboardMarkup(inline_keyboard=[
-         [
-             InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"post:del_yes:{post_id}"),
-@@ -416,110 +427,110 @@ async def publish_and_store(
-     post_id = make_post_id(created_by, main_mid)
-     buttons_json = json.dumps(buttons, ensure_ascii=False)
- 
-     async with POOL.acquire() as conn:
-         await conn.execute("""
-             INSERT INTO posts (id, channel_id, message_id, text_msg_id, text, buttons_json, photo_file_id, created_by)
-             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
-         """, post_id, channel_id, main_mid, text_mid, text, buttons_json, photo_file_id, created_by)
- 
-     return post_id
- 
- 
- async def safe_delete_message(bot: Bot, chat_id: str, message_id: Optional[int]) -> None:
-     if not message_id:
-         return
-     try:
-         await bot.delete_message(chat_id=chat_id, message_id=message_id)
-     except Exception:
-         pass
- 
- 
- # ================== COMMON ==================
- @dp.message(Command("start"))
- async def start(m: Message):
-     uid = m.from_user.id
--    if await db_is_admin(uid):
-+    if await is_admin(uid):
-         await m.answer(
-             "Привет! Меню доступно админам.\nНажми кнопки ниже 👇",
-             reply_markup=admin_menu_kb(is_owner(uid))
-         )
-     else:
-         await m.answer(
-             "Привет! Я бот для публикации постов в канал.\n"
-             "Если тебе нужен доступ — попроси владельца добавить тебя в админы.\n\n"
-             "Команда для тебя:\n"
-             "/myid — узнать свой user_id",
-             reply_markup=ReplyKeyboardRemove()
-         )
- 
- 
- @dp.message(Command("menu"))
- async def menu(m: Message):
-     uid = m.from_user.id
--    if not await db_is_admin(uid):
-+    if not await is_admin(uid):
-         return await m.answer("Меню доступно только админам.")
-     await m.answer("Меню 👇", reply_markup=admin_menu_kb(is_owner(uid)))
- 
- 
- @dp.message(Command("myid"))
- async def myid(m: Message):
-     uid = m.from_user.id
--    isadm = await db_is_admin(uid)
-+    isadm = await is_admin(uid)
-     await m.answer(
-         "Диагностика:\n"
-         f"- твой user_id: {uid}\n"
-         f"- ты админ по мнению бота: {isadm}\n"
-         f"- TIMEZONE: {TIMEZONE}\n"
-         f"- CHANNEL_ID: {CHANNEL_ID!r}\n"
-         f"- DB: {'ok' if bool(DATABASE_URL) else 'missing'}\n"
-     )
- 
- 
- @dp.message(Command("cancel"))
- async def cancel_cmd(m: Message, state: FSMContext):
-     await state.clear()
--    if await db_is_admin(m.from_user.id):
-+    if await is_admin(m.from_user.id):
-         await m.answer("Ок, отменено.", reply_markup=admin_menu_kb(is_owner(m.from_user.id)))
-     else:
-         await m.answer("Ок, отменено.", reply_markup=ReplyKeyboardRemove())
- 
- 
- # ================== MENU BUTTONS ==================
- @dp.message(F.text == BTN_MYID)
- async def menu_myid(m: Message):
-     await myid(m)
- 
- 
- @dp.message(F.text == BTN_CANCEL)
- async def menu_cancel(m: Message, state: FSMContext):
-     await cancel_cmd(m, state)
- 
- 
- @dp.message(F.text == BTN_HELP)
- async def menu_help(m: Message):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Доступ к функциям — только админам.")
-     await m.answer(
-         "Что умею:\n"
-         "• 📝 Новый пост (текст + кнопки + фото)\n"
-         "• 📅 Запланированные (посмотреть/редактировать/перенести/удалить)\n"
-         "• 🧾 Опубликованные (редактировать/удалить)\n\n"
-         "Если меню пропало — /menu",
-         reply_markup=admin_menu_kb(is_owner(m.from_user.id))
-     )
- 
- 
- # ================== ADMIN MGMT (OWNER) ==================
- @dp.message(F.text == BTN_ADMINS)
- async def menu_admins(m: Message):
-     if not is_owner(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
-     async with POOL.acquire() as conn:
-         rows = await conn.fetch("SELECT * FROM admins ORDER BY user_id ASC")
-     await m.answer("Админы:\n" + "\n".join(admin_display(r) for r in rows))
- 
- 
- @dp.message(Command("admins"))
- async def cmd_admins(m: Message):
-     if not is_owner(m.from_user.id):
-@@ -570,131 +581,131 @@ async def cmd_addadmin(m: Message, bot: Bot):
- async def cmd_deladmin(m: Message):
-     if not is_owner(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
- 
-     parts = (m.text or "").split()
-     if len(parts) != 2 or not parts[1].isdigit():
-         return await m.answer("Использование: /deladmin 123456789")
- 
-     uid = int(parts[1])
-     if uid == OWNER_ID:
-         return await m.answer("OWNER удалить нельзя 🙂")
- 
-     async with POOL.acquire() as conn:
-         res = await conn.execute("DELETE FROM admins WHERE user_id=$1", uid)
- 
-     if res.startswith("DELETE 1"):
-         await m.answer(f"✅ Удалила админа: {uid}")
-     else:
-         await m.answer("Такого админа нет.")
- 
- 
- # ================== CREATE POST ==================
- @dp.message(F.text == BTN_NEWPOST)
- async def menu_newpost(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     await state.clear()
-     await state.set_state(CreatePost.text)
-     await m.answer("Пришли текст поста.")
- 
- 
- @dp.message(Command("newpost"))
- async def cmd_newpost(m: Message, state: FSMContext):
-     await menu_newpost(m, state)
- 
- 
- @dp.message(CreatePost.text)
- async def create_get_text(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     text = (m.text or "").strip()
-     if not text:
-         return await m.answer("Нужен текст поста.")
-     await state.update_data(text=text)
-     await state.set_state(CreatePost.buttons)
-     await m.answer(
-         "Теперь кнопки (по одной строке):\n"
-         "Текст - https://example.com\n\n"
-         "Если кнопки не нужны — напиши `нет`",
-         parse_mode="Markdown"
-     )
- 
- 
- @dp.message(CreatePost.buttons)
- async def create_get_buttons(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     raw = (m.text or "").strip()
-     buttons = [] if raw.lower() == "нет" else parse_buttons(raw)
-     await state.update_data(buttons=buttons)
-     await state.set_state(CreatePost.photo)
-     await m.answer("Теперь пришли ОДНО фото для поста или напиши `нет`.", parse_mode="Markdown")
- 
- 
- @dp.message(CreatePost.photo)
- async def create_get_photo(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
- 
-     data = await state.get_data()
-     text = data.get("text", "")
-     buttons = data.get("buttons", [])
- 
-     raw = (m.text or "").strip().lower()
-     photo_file_id: Optional[str] = None
- 
-     if raw == "нет":
-         photo_file_id = None
-     elif m.photo:
-         photo_file_id = m.photo[-1].file_id
-     elif m.document and (m.document.mime_type or "").startswith("image/"):
-         photo_file_id = m.document.file_id
-     else:
-         return await m.answer("Не вижу фото 😅 Пришли фото или напиши `нет`.")
- 
-     await state.update_data(photo_file_id=photo_file_id)
- 
-     if photo_file_id and caption_too_long(text):
-         await state.set_state(CreatePost.long_with_photo_choice)
-         kb = InlineKeyboardMarkup(inline_keyboard=[
-             [InlineKeyboardButton(text="📷 Короткий caption + текст отдельно", callback_data="longphoto:split")],
-             [InlineKeyboardButton(text="📝 Без фото (весь текст одним сообщением)", callback_data="longphoto:nophoto")],
-             [InlineKeyboardButton(text="❌ Отмена", callback_data="draft:cancel")],
-         ])
-         return await m.answer(
-             f"Текст слишком длинный для подписи к фото (лимит ~{CAPTION_LIMIT}). Как поступаем?",
-             reply_markup=kb
-         )
- 
-     await show_preview_create(m, state, text=text, buttons=buttons, photo_file_id=photo_file_id, split_text=False)
- 
- 
- @dp.callback_query(F.data.startswith("longphoto:"))
- async def cb_longphoto_choice(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
- 
-     data = await state.get_data()
-     text = data.get("text", "")
-     buttons = data.get("buttons", [])
-     photo_file_id = data.get("photo_file_id")
- 
-     if c.data == "longphoto:nophoto":
-         await state.update_data(photo_file_id=None, split_text=False)
-         await state.set_state(CreatePost.preview)
-         await c.message.answer("🧾 Предпросмотр поста (без фото):")
-         await c.message.answer(text, reply_markup=build_kb(buttons))
-         await c.message.answer("Что делаем дальше?", reply_markup=preview_actions_kb())
-         await c.answer()
-         return
- 
-     if c.data == "longphoto:split":
-         await state.update_data(split_text=True)
-         await state.set_state(CreatePost.preview)
-         short_caption = (text[:CAPTION_LIMIT - 1] + "…") if len(text) > CAPTION_LIMIT else text
-         await c.message.answer("🧾 Предпросмотр поста (фото + текст отдельным сообщением):")
-         await c.message.answer_photo(photo_file_id, caption=short_caption, reply_markup=None)
-         await c.message.answer(text, reply_markup=build_kb(buttons))
-         await c.message.answer("Что делаем дальше?", reply_markup=preview_actions_kb())
-@@ -720,107 +731,107 @@ async def show_preview_create(
-         if split_text:
-             caption = (text[:CAPTION_LIMIT - 1] + "…") if len(text) > CAPTION_LIMIT else text
-             await m.answer_photo(photo_file_id, caption=caption, reply_markup=None)
-             await m.answer(text, reply_markup=build_kb(buttons))
-         else:
-             await m.answer_photo(photo_file_id, caption=text, reply_markup=build_kb(buttons))
-     else:
-         await m.answer(text, reply_markup=build_kb(buttons))
- 
-     await m.answer("Что делаем дальше?", reply_markup=preview_actions_kb())
- 
- 
- # ================== DRAFT ACTIONS ==================
- @dp.callback_query(F.data == "draft:cancel")
- async def cb_draft_cancel(c: CallbackQuery, state: FSMContext):
-     await state.clear()
-     try:
-         await c.message.edit_text("Ок, отменено.")
-     except Exception:
-         await c.message.answer("Ок, отменено.")
-     await c.answer()
- 
- 
- @dp.callback_query(F.data == "draft:pub_now")
- async def cb_pub_now(c: CallbackQuery, state: FSMContext, bot: Bot):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     if not CHANNEL_ID:
-         await c.answer("Не задан CHANNEL_ID (Render → Environment).", show_alert=True)
-         return
- 
-     data = await state.get_data()
-     text = data.get("text", "")
-     buttons = data.get("buttons", [])
-     photo_file_id = data.get("photo_file_id")
-     split_text = bool(data.get("split_text", False))
- 
-     try:
-         post_id = await publish_and_store(
-             bot=bot,
-             channel_id=CHANNEL_ID,
-             text=text,
-             buttons=buttons,
-             created_by=c.from_user.id,
-             photo_file_id=photo_file_id,
-             split_text=split_text,
-         )
-     except Exception as e:
-         await c.answer("Не смогла опубликовать. Проверь права бота в канале.", show_alert=True)
-         await c.message.answer(f"Ошибка: {e}")
-         return
- 
-     await state.clear()
-     try:
-         await c.message.edit_text("✅ Опубликовано!")
-     except Exception:
-         await c.message.answer("✅ Опубликовано!")
- 
-     await c.message.answer(
-         f"Управление постом (id: `{post_id}`):",
-         parse_mode="Markdown",
-         reply_markup=post_controls_kb(post_id),
-     )
-     await c.answer()
- 
- 
- @dp.callback_query(F.data == "draft:schedule")
- async def cb_schedule_start(c: CallbackQuery):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     await c.message.answer(
-         f"Выбери время публикации ({tz_label()}):",
-         reply_markup=quick_times_kb("draft_time", "draft"),
-     )
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("draft_time:draft:"))
- async def cb_draft_time(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
- 
-     code = c.data.split(":", 2)[2]
- 
-     if code == "manual":
-         await state.update_data(
-             awaiting_manual_datetime=True,
-             manual_dt_for="draft",
-         )
-         await c.message.answer(
-             "Введи дату и время в формате:\n"
-             "`DD.MM.YYYY HH:MM`\n"
-             f"Например: `{now_tz().strftime('%d.%m.%Y %H:%M')}`",
-             parse_mode="Markdown"
-         )
-         await c.answer()
-         return
- 
-     run_at = calc_quick_dt(code)
-     await state.update_data(run_at_iso=run_at.isoformat())
-     await finalize_schedule(c.message, state)
-     await c.answer()
- 
- 
-@@ -848,310 +859,310 @@ async def finalize_schedule(target: Message, state: FSMContext):
-     buttons_json = json.dumps(buttons, ensure_ascii=False)
- 
-     async with POOL.acquire() as conn:
-         await conn.execute("""
-             INSERT INTO jobs (id, channel_id, text, buttons_json, photo_file_id, run_at, created_by)
-             VALUES ($1, $2, $3, $4, $5, $6, $7)
-         """, job_id, CHANNEL_ID, text, buttons_json, photo_file_id, run_at, target.from_user.id)
- 
-     await state.clear()
-     await target.answer(f"✅ Запланировано на {fmt_dt(run_at)} ({tz_label()})")
-     await target.answer(
-         f"Управление запланированным (id: `{job_id}`):",
-         parse_mode="Markdown",
-         reply_markup=job_controls_kb(job_id),
-     )
- 
- 
- # ================== JOBS ==================
- @dp.message(F.text == BTN_JOBS)
- async def menu_jobs(m: Message):
-     await cmd_jobs(m)
- 
- 
- @dp.message(Command("jobs"))
- async def cmd_jobs(m: Message):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
- 
-     async with POOL.acquire() as conn:
-         rows = await conn.fetch("""
-             SELECT id, text, run_at
-             FROM jobs
-             ORDER BY run_at ASC
-             LIMIT 20
-         """)
- 
-     if not rows:
-         return await m.answer("Запланированных постов нет.", reply_markup=admin_menu_kb(is_owner(m.from_user.id)))
- 
-     await m.answer("📅 Запланированные (последние 20):")
-     for r in rows:
-         job_id = r["id"]
-         dt = r["run_at"]
-         short = (r["text"] or "").strip().replace("\n", " ")
-         if len(short) > 60:
-             short = short[:60] + "…"
-         await m.answer(
-             f"⏰ {fmt_dt(dt)} ({tz_label()})\n🆔 `{job_id}`\n📝 {short}",
-             parse_mode="Markdown",
-             reply_markup=job_controls_kb(job_id),
-         )
- 
- 
- @dp.callback_query(F.data.startswith("job:view:"))
- async def cb_job_view(c: CallbackQuery):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     job_id = c.data.split(":", 2)[2]
-     async with POOL.acquire() as conn:
-         r = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
- 
-     if not r:
-         await c.answer("Не нашла задачу.", show_alert=True)
-         return
- 
-     dt = r["run_at"]
-     buttons = json.loads(r["buttons_json"])
-     photo_file_id = r["photo_file_id"]
-     text = r["text"]
- 
-     await c.message.answer(
-         f"👁 Запланировано на: {fmt_dt(dt)} ({tz_label()})\n🆔 `{job_id}`",
-         parse_mode="Markdown"
-     )
- 
-     # отображение (если текст слишком длинный для caption — покажем split превью)
-     if photo_file_id:
-         if caption_too_long(text):
-             short_caption = (text[:CAPTION_LIMIT - 1] + "…") if len(text) > CAPTION_LIMIT else text
-             await c.message.answer_photo(photo_file_id, caption=short_caption, reply_markup=None)
-             await c.message.answer(text, reply_markup=build_kb(buttons))
-         else:
-             await c.message.answer_photo(photo_file_id, caption=text, reply_markup=build_kb(buttons))
-     else:
-         await c.message.answer(text, reply_markup=build_kb(buttons))
- 
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("job:del:"))
- async def cb_job_del_ask(c: CallbackQuery):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     job_id = c.data.split(":", 2)[2]
-     await c.message.answer("Подтвердить удаление?", reply_markup=job_delete_confirm_kb(job_id))
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("job:del_no:"))
- async def cb_job_del_no(c: CallbackQuery):
-     await c.message.edit_text("Ок, не удаляю.")
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("job:del_yes:"))
- async def cb_job_del_yes(c: CallbackQuery):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     job_id = c.data.split(":", 2)[2]
-     async with POOL.acquire() as conn:
-         res = await conn.execute("DELETE FROM jobs WHERE id=$1", job_id)
- 
-     if res.startswith("DELETE 1"):
-         await c.message.edit_text("✅ Удалила запланированный пост.")
-     else:
-         await c.message.edit_text("Не нашла задачу (возможно, уже отправлена).")
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("job:move:"))
- async def cb_job_move_start(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
- 
-     job_id = c.data.split(":", 2)[2]
-     await state.clear()
-     await state.update_data(move_job_id=job_id)
-     await c.message.answer(
-         f"Выбери новое время ({tz_label()}):",
-         reply_markup=quick_times_kb("job_time", job_id),
-     )
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("job_time:"))
- async def cb_job_time_pick(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     _, job_id, code = c.data.split(":", 2)
- 
-     if code == "manual":
-         await state.update_data(
-             awaiting_manual_datetime=True,
-             manual_dt_for="job_move",
-             move_job_id=job_id,
-         )
-         await c.message.answer(
-             "Введи дату и время в формате:\n"
-             "`DD.MM.YYYY HH:MM`\n"
-             f"Например: `{now_tz().strftime('%d.%m.%Y %H:%M')}`",
-             parse_mode="Markdown"
-         )
-         await c.answer()
-         return
- 
-     new_dt = calc_quick_dt(code)
-     async with POOL.acquire() as conn:
-         res = await conn.execute("UPDATE jobs SET run_at=$1 WHERE id=$2", new_dt, job_id)
- 
-     await state.clear()
-     if res.startswith("UPDATE 1"):
-         await c.message.answer(f"✅ Перенесла на {fmt_dt(new_dt)} ({tz_label()})")
-     else:
-         await c.message.answer("Не нашла задачу.")
-     await c.answer()
- 
- 
- # ---- edit job (content) ----
- @dp.callback_query(F.data.startswith("job:edit:"))
- async def cb_job_edit_start(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     job_id = c.data.split(":", 2)[2]
-     async with POOL.acquire() as conn:
-         r = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
-     if not r:
-         await c.answer("Не нашла задачу.", show_alert=True)
-         return
- 
-     await state.clear()
-     await state.set_state(EditJob.text)
-     await state.update_data(edit_job_id=job_id)
-     await c.message.answer("✏️ Редактирование отложки: пришли НОВЫЙ текст поста.")
-     await c.answer()
- 
- 
- @dp.message(EditJob.text)
- async def editjob_get_text(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     text = (m.text or "").strip()
-     if not text:
-         return await m.answer("Нужен текст.")
-     await state.update_data(new_text=text)
-     await state.set_state(EditJob.buttons)
-     await m.answer(
-         "Теперь НОВЫЕ кнопки (по одной строке):\n"
-         "Текст - https://example.com\n\n"
-         "Если кнопки не нужны — напиши `нет`",
-         parse_mode="Markdown"
-     )
- 
- 
- @dp.message(EditJob.buttons)
- async def editjob_get_buttons(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     raw = (m.text or "").strip()
-     buttons = [] if raw.lower() == "нет" else parse_buttons(raw)
-     await state.update_data(new_buttons=buttons)
-     await state.set_state(EditJob.photo)
-     await m.answer(
-         "Теперь пришли НОВОЕ фото (если хочешь заменить).\n"
-         "Если оставить старое фото — напиши `оставить`.\n"
-         "Если убрать фото — напиши `убрать`.",
-         parse_mode="Markdown"
-     )
- 
- 
- @dp.message(EditJob.photo)
- async def editjob_get_photo(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
- 
-     data = await state.get_data()
-     job_id = data.get("edit_job_id")
-     new_text = data.get("new_text", "")
-     new_buttons = data.get("new_buttons", [])
- 
-     async with POOL.acquire() as conn:
-         r = await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)
-     if not r:
-         await state.clear()
-         return await m.answer("Не нашла задачу.")
- 
-     incoming = (m.text or "").strip().lower()
-     photo_file_id: Optional[str] = None
- 
-     if m.photo:
-         photo_file_id = m.photo[-1].file_id
-     elif m.document and (m.document.mime_type or "").startswith("image/"):
-         photo_file_id = m.document.file_id
-     elif incoming == "оставить":
-         photo_file_id = r["photo_file_id"]
-     elif incoming == "убрать":
-         photo_file_id = None
-     else:
-         return await m.answer("Не вижу фото 😅 Пришли фото или напиши `оставить` / `убрать`.")
- 
-     await state.update_data(photo_file_id=photo_file_id)
- 
-     if photo_file_id and caption_too_long(new_text):
-         await state.set_state(EditJob.long_with_photo_choice)
-         kb = InlineKeyboardMarkup(inline_keyboard=[
-             [InlineKeyboardButton(text="📷 Короткий caption + текст отдельно", callback_data="editjoblong:split")],
-             [InlineKeyboardButton(text="📝 Без фото (весь текст одним сообщением)", callback_data="editjoblong:nophoto")],
-             [InlineKeyboardButton(text="❌ Отмена", callback_data="draft:cancel")],
-         ])
-         return await m.answer(
-             f"Текст слишком длинный для подписи к фото (лимит ~{CAPTION_LIMIT}). Как поступаем?",
-             reply_markup=kb
-         )
- 
-     await show_preview_editjob(m, state, new_text, new_buttons, photo_file_id, split_text=False)
- 
- 
- @dp.callback_query(F.data.startswith("editjoblong:"))
- async def cb_editjoblong_choice(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
- 
-     data = await state.get_data()
-     new_text = data.get("new_text", "")
-     new_buttons = data.get("new_buttons", [])
-     photo_file_id = data.get("photo_file_id")
- 
-     if c.data == "editjoblong:nophoto":
-         await state.update_data(photo_file_id=None, split_text=False)
-         await show_preview_editjob(c.message, state, new_text, new_buttons, None, split_text=False)
-         await c.answer()
-         return
- 
-     if c.data == "editjoblong:split":
-         await state.update_data(split_text=True)
-         await show_preview_editjob(c.message, state, new_text, new_buttons, photo_file_id, split_text=True)
-         await c.answer()
-         return
- 
-     await c.answer()
- 
- 
- async def show_preview_editjob(
-     target: Message,
-@@ -1162,268 +1173,268 @@ async def show_preview_editjob(
-     split_text: bool
- ):
-     await state.update_data(split_text=split_text)
-     await state.set_state(EditJob.preview)
- 
-     await target.answer("🧾 Предпросмотр обновлённой отложки:")
-     if photo_file_id:
-         if split_text:
-             short_caption = (text[:CAPTION_LIMIT - 1] + "…") if len(text) > CAPTION_LIMIT else text
-             await target.answer_photo(photo_file_id, caption=short_caption, reply_markup=None)
-             await target.answer(text, reply_markup=build_kb(buttons))
-         else:
-             await target.answer_photo(photo_file_id, caption=text, reply_markup=build_kb(buttons))
-     else:
-         await target.answer(text, reply_markup=build_kb(buttons))
- 
-     kb = InlineKeyboardMarkup(inline_keyboard=[
-         [InlineKeyboardButton(text="✅ Сохранить изменения", callback_data="job:apply_edit")],
-         [InlineKeyboardButton(text="❌ Отменить", callback_data="draft:cancel")],
-     ])
-     await target.answer("Сохранить изменения в отложке?", reply_markup=kb)
- 
- 
- @dp.callback_query(F.data == "job:apply_edit")
- async def cb_job_apply_edit(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     data = await state.get_data()
-     job_id = data.get("edit_job_id")
-     new_text = data.get("new_text", "")
-     new_buttons = data.get("new_buttons", [])
-     photo_file_id = data.get("photo_file_id")
- 
-     if not job_id:
-         await c.answer("Не вижу задачу.", show_alert=True)
-         await state.clear()
-         return
- 
-     buttons_json = json.dumps(new_buttons, ensure_ascii=False)
- 
-     async with POOL.acquire() as conn:
-         exists = await conn.fetchrow("SELECT id FROM jobs WHERE id=$1", job_id)
-         if not exists:
-             await c.answer("Не нашла задачу.", show_alert=True)
-             await state.clear()
-             return
- 
-         await conn.execute("""
-             UPDATE jobs
-             SET text=$1, buttons_json=$2, photo_file_id=$3
-             WHERE id=$4
-         """, new_text, buttons_json, photo_file_id, job_id)
- 
-     await state.clear()
-     await c.message.answer("✅ Обновила отложенный пост. Время публикации осталось прежним.", reply_markup=job_controls_kb(job_id))
-     await c.answer()
- 
- 
- # ================== POSTS ==================
- @dp.message(F.text == BTN_POSTS)
- async def menu_posts(m: Message):
-     await cmd_posts(m)
- 
- 
- @dp.message(Command("posts"))
- async def cmd_posts(m: Message):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
- 
-     async with POOL.acquire() as conn:
-         rows = await conn.fetch("""
-             SELECT id, text, created_at
-             FROM posts
-             ORDER BY created_at DESC
-             LIMIT 10
-         """)
- 
-     if not rows:
-         return await m.answer("Пока нет постов, опубликованных ботом.")
- 
-     await m.answer("🧾 Последние 10 опубликованных ботом:")
-     for r in rows:
-         post_id = r["id"]
-         dt = r["created_at"]
-         short = (r["text"] or "").strip().replace("\n", " ")
-         if len(short) > 60:
-             short = short[:60] + "…"
-         await m.answer(
-             f"🕒 {fmt_dt(dt)} ({tz_label()})\n🆔 `{post_id}`\n📝 {short}",
-             parse_mode="Markdown",
-             reply_markup=post_controls_kb(post_id)
-         )
- 
- 
- @dp.callback_query(F.data.startswith("post:del:"))
- async def cb_post_del_ask(c: CallbackQuery):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     post_id = c.data.split(":", 2)[2]
-     await c.message.answer("Подтвердить удаление?", reply_markup=post_delete_confirm_kb(post_id))
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("post:del_no:"))
- async def cb_post_del_no(c: CallbackQuery):
-     await c.message.edit_text("Ок, не удаляю.")
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("post:del_yes:"))
- async def cb_post_del_yes(c: CallbackQuery, bot: Bot):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     post_id = c.data.split(":", 2)[2]
-     async with POOL.acquire() as conn:
-         p = await conn.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
- 
-     if not p:
-         await c.answer("Пост не найден.", show_alert=True)
-         return
- 
-     await safe_delete_message(bot, p["channel_id"], p["message_id"])
-     await safe_delete_message(bot, p["channel_id"], p["text_msg_id"])
- 
-     async with POOL.acquire() as conn:
-         await conn.execute("DELETE FROM posts WHERE id=$1", post_id)
- 
-     await c.message.edit_text("✅ Удалила пост из канала.")
-     await c.answer()
- 
- 
- @dp.callback_query(F.data.startswith("post:edit:"))
- async def cb_post_edit_start(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
-     assert POOL is not None
- 
-     post_id = c.data.split(":", 2)[2]
-     async with POOL.acquire() as conn:
-         p = await conn.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
-     if not p:
-         await c.answer("Пост не найден.", show_alert=True)
-         return
- 
-     await state.clear()
-     await state.set_state(EditPost.text)
-     await state.update_data(edit_post_id=post_id)
-     await c.message.answer("✏️ Редактирование: пришли НОВЫЙ текст поста.")
-     await c.answer()
- 
- 
- @dp.message(EditPost.text)
- async def edit_get_text(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     text = (m.text or "").strip()
-     if not text:
-         return await m.answer("Нужен текст.")
-     await state.update_data(new_text=text)
-     await state.set_state(EditPost.buttons)
-     await m.answer(
-         "Теперь НОВЫЕ кнопки (по одной строке):\n"
-         "Текст - https://example.com\n\n"
-         "Если кнопки не нужны — напиши `нет`",
-         parse_mode="Markdown"
-     )
- 
- 
- @dp.message(EditPost.buttons)
- async def edit_get_buttons(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     raw = (m.text or "").strip()
-     buttons = [] if raw.lower() == "нет" else parse_buttons(raw)
-     await state.update_data(new_buttons=buttons)
-     await state.set_state(EditPost.photo)
-     await m.answer(
-         "Теперь пришли НОВОЕ фото (если хочешь заменить).\n"
-         "Если оставить старое фото — напиши `оставить`.\n"
-         "Если убрать фото — напиши `убрать`.",
-         parse_mode="Markdown"
-     )
- 
- 
- @dp.message(EditPost.photo)
- async def edit_get_photo(m: Message, state: FSMContext):
--    if not await db_is_admin(m.from_user.id):
-+    if not await is_admin(m.from_user.id):
-         return await m.answer("Нет доступа.")
-     assert POOL is not None
- 
-     data = await state.get_data()
-     post_id = data.get("edit_post_id")
-     new_text = data.get("new_text", "")
-     new_buttons = data.get("new_buttons", [])
- 
-     async with POOL.acquire() as conn:
-         p = await conn.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
-     if not p:
-         await state.clear()
-         return await m.answer("Пост не найден.")
- 
-     incoming = (m.text or "").strip().lower()
-     if m.photo:
-         photo_file_id = m.photo[-1].file_id
-     elif m.document and (m.document.mime_type or "").startswith("image/"):
-         photo_file_id = m.document.file_id
-     elif incoming == "оставить":
-         photo_file_id = p["photo_file_id"]
-     elif incoming == "убрать":
-         photo_file_id = None
-     else:
-         return await m.answer("Не вижу фото 😅 Пришли фото или напиши `оставить` / `убрать`.")
- 
-     await state.update_data(photo_file_id=photo_file_id)
- 
-     # если фото есть и текст длинный — спросим split/без фото
-     if photo_file_id and caption_too_long(new_text):
-         await state.set_state(EditPost.long_with_photo_choice)
-         kb = InlineKeyboardMarkup(inline_keyboard=[
-             [InlineKeyboardButton(text="📷 Короткий caption + текст отдельно", callback_data="editlong:split")],
-             [InlineKeyboardButton(text="📝 Без фото (весь текст одним сообщением)", callback_data="editlong:nophoto")],
-             [InlineKeyboardButton(text="❌ Отмена", callback_data="draft:cancel")],
-         ])
-         return await m.answer(
-             f"Текст слишком длинный для подписи к фото (лимит ~{CAPTION_LIMIT}). Как поступаем?",
-             reply_markup=kb
-         )
- 
-     await show_preview_editpost(m, state, new_text, new_buttons, photo_file_id, split_text=False)
- 
- 
- @dp.callback_query(F.data.startswith("editlong:"))
- async def cb_editlong_choice(c: CallbackQuery, state: FSMContext):
--    if not await db_is_admin(c.from_user.id):
-+    if not await is_admin(c.from_user.id):
-         await c.answer("Нет доступа.", show_alert=True)
-         return
- 
-     data = await state.get_data()
-     new_text = data.get("new_text", "")
-     new_buttons = data.get("new_buttons", [])
-     photo_file_id = data.get("photo_file_id")
- 
-     if c.data == "editlong:nophoto":
-         await state.update_data(photo_file_id=None, split_text=False)
-         await show_preview_editpost(c.message, state, new_text, new_buttons, None, split_text=False)
-         await c.answer()
-         return
- 
-     if c.data == "editlong:split":
-         await state.update_data(split_text=True)
-         await show_preview_editpost(c.message, state, new_text, new_buttons, photo_file_id, split_text=True)
-         await c.answer()
-         return
- 
-     await c.answer()
- 
- 
- async def show_preview_editpost(
-     target: Message,
-@@ -1432,27 +1443,250 @@ async def show_preview_editpost(
-     buttons: list,
-     photo_file_id: Optional[str],
-     split_text: bool
- ):
-     await state.update_data(split_text=split_text)
-     await state.set_state(EditPost.preview)
- 
-     await target.answer("🧾 Предпросмотр обновлённого поста:")
-     if photo_file_id:
-         if split_text:
-             short_caption = (text[:CAPTION_LIMIT - 1] + "…") if len(text) > CAPTION_LIMIT else text
-             await target.answer_photo(photo_file_id, caption=short_caption, reply_markup=None)
-             await target.answer(text, reply_markup=build_kb(buttons))
-         else:
-             await target.answer_photo(photo_file_id, caption=text, reply_markup=build_kb(buttons))
-     else:
-         await target.answer(text, reply_markup=build_kb(buttons))
- 
-     kb = InlineKeyboardMarkup(inline_keyboard=[
-         [InlineKeyboardButton(text="✅ Применить изменения", callback_data="post:apply_edit")],
-         [InlineKeyboardButton(text="❌ Отменить", callback_data="draft:cancel")],
-     ])
-     await target.answer("Применить изменения?", reply_markup=kb)
- 
- 
--@dp
-+@dp.callback_query(F.data == "post:apply_edit")
-+async def cb_post_apply_edit(c: CallbackQuery, state: FSMContext, bot: Bot):
-+    if not await is_admin(c.from_user.id):
-+        await c.answer("Нет доступа.", show_alert=True)
-+        return
-+    assert POOL is not None
-+
-+    data = await state.get_data()
-+    post_id = data.get("edit_post_id")
-+    new_text = data.get("new_text", "")
-+    new_buttons = data.get("new_buttons", [])
-+    photo_file_id = data.get("photo_file_id")
-+    split_text = bool(data.get("split_text", False))
-+
-+    if not post_id:
-+        await c.answer("Не вижу пост.", show_alert=True)
-+        await state.clear()
-+        return
-+
-+    async with POOL.acquire() as conn:
-+        p = await conn.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
-+
-+    if not p:
-+        await c.answer("Пост не найден.", show_alert=True)
-+        await state.clear()
-+        return
-+
-+    if photo_file_id and caption_too_long(new_text) and not split_text:
-+        await c.answer("Текст слишком длинный для подписи. Выбери режим split.", show_alert=True)
-+        return
-+
-+    if split_text and not photo_file_id:
-+        split_text = False
-+
-+    existing_split = bool(p["text_msg_id"])
-+    existing_photo = bool(p["photo_file_id"])
-+    replace_messages = False
-+
-+    if photo_file_id != p["photo_file_id"]:
-+        replace_messages = True
-+    if split_text != existing_split:
-+        replace_messages = True
-+
-+    buttons_kb = build_kb(new_buttons)
-+
-+    if replace_messages:
-+        await safe_delete_message(bot, p["channel_id"], p["message_id"])
-+        await safe_delete_message(bot, p["channel_id"], p["text_msg_id"])
-+        main_mid, text_mid = await send_post_to_channel(
-+            bot=bot,
-+            channel_id=p["channel_id"],
-+            text=new_text,
-+            buttons=new_buttons,
-+            photo_file_id=photo_file_id,
-+            split_text=split_text,
-+        )
-+        async with POOL.acquire() as conn:
-+            await conn.execute("""
-+                UPDATE posts
-+                SET message_id=$1, text_msg_id=$2, text=$3, buttons_json=$4, photo_file_id=$5
-+                WHERE id=$6
-+            """, main_mid, text_mid, new_text, json.dumps(new_buttons, ensure_ascii=False), photo_file_id, post_id)
-+    else:
-+        if photo_file_id:
-+            if split_text:
-+                if not p["text_msg_id"]:
-+                    await c.answer("Не вижу текстовое сообщение.", show_alert=True)
-+                    await state.clear()
-+                    return
-+                short_caption = (new_text[:CAPTION_LIMIT - 1] + "…") if len(new_text) > CAPTION_LIMIT else new_text
-+                await bot.edit_message_caption(
-+                    chat_id=p["channel_id"],
-+                    message_id=p["message_id"],
-+                    caption=short_caption,
-+                    reply_markup=None,
-+                )
-+                await bot.edit_message_text(
-+                    chat_id=p["channel_id"],
-+                    message_id=p["text_msg_id"],
-+                    text=new_text,
-+                    reply_markup=buttons_kb,
-+                )
-+            else:
-+                await bot.edit_message_caption(
-+                    chat_id=p["channel_id"],
-+                    message_id=p["message_id"],
-+                    caption=new_text,
-+                    reply_markup=buttons_kb,
-+                )
-+        else:
-+            await bot.edit_message_text(
-+                chat_id=p["channel_id"],
-+                message_id=p["message_id"],
-+                text=new_text,
-+                reply_markup=buttons_kb,
-+            )
-+
-+        async with POOL.acquire() as conn:
-+            await conn.execute("""
-+                UPDATE posts
-+                SET text=$1, buttons_json=$2, photo_file_id=$3
-+                WHERE id=$4
-+            """, new_text, json.dumps(new_buttons, ensure_ascii=False), photo_file_id, post_id)
-+
-+    await state.clear()
-+    await c.message.answer("✅ Обновила пост.", reply_markup=post_controls_kb(post_id))
-+    await c.answer()
-+
-+
-+@dp.message(AwaitingManualDatetime())
-+async def manual_datetime_input(m: Message, state: FSMContext):
-+    if not await is_admin(m.from_user.id):
-+        return await m.answer("Нет доступа.")
-+    assert POOL is not None
-+
-+    data = await state.get_data()
-+    mode = data.get("manual_dt_for")
-+
-+    try:
-+        run_at = parse_dt_local(m.text or "")
-+    except ValueError:
-+        return await m.answer("Не смогла разобрать дату. Формат: `DD.MM.YYYY HH:MM`", parse_mode="Markdown")
-+
-+    if run_at <= now_tz() + timedelta(seconds=30):
-+        return await m.answer("Время должно быть хотя бы на 1 минуту позже текущего.")
-+
-+    if mode == "draft":
-+        await state.update_data(run_at_iso=run_at.isoformat(), awaiting_manual_datetime=False)
-+        await finalize_schedule(m, state)
-+        return
-+
-+    if mode == "job_move":
-+        job_id = data.get("move_job_id")
-+        if not job_id:
-+            await state.clear()
-+            return await m.answer("Не вижу задачу.")
-+        async with POOL.acquire() as conn:
-+            res = await conn.execute("UPDATE jobs SET run_at=$1 WHERE id=$2", run_at, job_id)
-+        await state.clear()
-+        if res.startswith("UPDATE 1"):
-+            return await m.answer(f"✅ Перенесла на {fmt_dt(run_at)} ({tz_label()})")
-+        return await m.answer("Не нашла задачу.")
-+
-+    await state.clear()
-+    await m.answer("Не вижу контекста для даты. Попробуй ещё раз.")
-+
-+
-+async def scheduler_loop(bot: Bot) -> None:
-+    assert POOL is not None
-+    while True:
-+        try:
-+            async with POOL.acquire() as conn:
-+                rows = await conn.fetch("""
-+                    SELECT *
-+                    FROM jobs
-+                    WHERE run_at <= NOW()
-+                    ORDER BY run_at ASC
-+                    LIMIT 10
-+                """)
-+            if not rows:
-+                await asyncio.sleep(5)
-+                continue
-+
-+            for r in rows:
-+                job_id = r["id"]
-+                text = r["text"]
-+                buttons = json.loads(r["buttons_json"])
-+                photo_file_id = r["photo_file_id"]
-+                split_text = bool(photo_file_id and caption_too_long(text))
-+                try:
-+                    await publish_and_store(
-+                        bot=bot,
-+                        channel_id=r["channel_id"],
-+                        text=text,
-+                        buttons=buttons,
-+                        created_by=r["created_by"],
-+                        photo_file_id=photo_file_id,
-+                        split_text=split_text,
-+                    )
-+                except Exception:
-+                    continue
-+
-+                async with POOL.acquire() as conn:
-+                    await conn.execute("DELETE FROM jobs WHERE id=$1", job_id)
-+        except Exception:
-+            await asyncio.sleep(5)
-+
-+
-+async def start_web_app() -> web.AppRunner:
-+    app = web.Application()
-+
-+    async def health(_: web.Request) -> web.Response:
-+        return web.Response(text="ok")
-+
-+    app.router.add_get("/", health)
-+    app.router.add_get("/health", health)
-+
-+    runner = web.AppRunner(app)
-+    await runner.setup()
-+    port = int(os.getenv("PORT", "10000"))
-+    site = web.TCPSite(runner, "0.0.0.0", port)
-+    await site.start()
-+    return runner
-+
-+
-+async def main() -> None:
-+    if not BOT_TOKEN:
-+        raise RuntimeError("BOT_TOKEN is empty. Set it in Render → Environment.")
-+
-+    await init_db()
-+    bot = Bot(BOT_TOKEN)
-+
-+    scheduler_task = asyncio.create_task(scheduler_loop(bot))
-+    web_runner = await start_web_app()
-+
-+    try:
-+        await dp.start_polling(bot)
-+    finally:
-+        scheduler_task.cancel()
-+        await web_runner.cleanup()
-+        await bot.session.close()
-+
- 
-+if __name__ == "__main__":
-+    asyncio.run(main())
- 
-EOF
+import asyncio
+import os
+from dataclasses import dataclass
+from typing import Optional
+from urllib.parse import quote
+
+from aiogram import Bot, Dispatcher, F
+from aiogram.enums import ParseMode
+from aiogram.filters import CommandStart
+from aiogram.types import (
+    CallbackQuery,
+    InlineKeyboardButton,
+    InlineKeyboardMarkup,
+    KeyboardButton,
+    Message,
+    ReplyKeyboardMarkup,
+    ReplyKeyboardRemove,
 )
+from dotenv import load_dotenv
+
+load_dotenv()
+
+BOT_TOKEN = os.getenv("BOT_TOKEN", "")
+
+BTN_COURSES = "Наши курсы"
+BTN_CALC = "Калькулятор OZON/ЯМ"
+BTN_PARTNERSHIP = "Сотрудничество"
+BTN_CONSULT = "Личная консультация"
+
+CHANNEL_URL = "https://t.me/ozonbluerise"
+
+CONSULT_FORM_URL = os.getenv("CONSULTATION_FORM_URL")
+
+
+@dataclass(frozen=True)
+class Course:
+    title: str
+    description: str
+    link: str
+    invoice_text: str
+
+
+PRO_CONTACT = "ilya_bolsheglazov"
+HELP_CONTACT = "yashiann"
+
+
+BEGINNER_COURSE = Course(
+    title="Грамотный старт на Озон",
+    description=(
+        "«Грамотный старт на Озон» — для селлеров и менеджеров, которые делают первые "
+        "шаги в Озон и хотят начать уверенно разбираться во всех основных вещах, "
+        "необходимых для ведения прибыльного бизнеса."
+    ),
+    link="https://bluerise.getcourse.ru/GSO_VC",
+    invoice_text="Здравствуйте, мне нужен счет для оплаты курса «Грамотный старт на Озон».",
+)
+
+
+ADVANCED_COURSES = {
+    "pro_logistics": Course(
+        title="PRO логистику",
+        description=(
+            "Курс PRO логистику для тех, кто хочет снизить СВД в своем кабинете, понимать "
+            "сколько товара грузить в каждый кластер и понять, как не переплачивать за логистику."
+        ),
+        link="https://bluerise.getcourse.ru/PRO_logistics",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO логистику».",
+    ),
+    "pro_ads": Course(
+        title="PRO рекламу",
+        description=(
+            "Курс PRO рекламу — для тех, кто хочет оптимизировать свои рекламные расходы, "
+            "научиться выстраивать рекламные стратегии и понимать, какими инструментами "
+            "продвижения пользоваться для разных типов товаров и в различных ситуациях."
+        ),
+        link="https://bluerise.getcourse.ru/PRO_Reklamu",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO рекламу».",
+    ),
+    "pro_analytics": Course(
+        title="PRO Аналитику",
+        description=(
+            "Курс PRO Аналитику — для тех, кто хочет изучить все значимые нюансы и все "
+            "инструменты, которые необходимы для анализа."
+        ),
+        link="https://bluerise.getcourse.ru/PRO_Analytics",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Аналитику».",
+    ),
+    "pro_finance": Course(
+        title="PRO Финансы",
+        description=(
+            "Курс «PRO Финансы» — для тех, кто хочет научиться считать юнит-план и юнит-факт, "
+            "ROI и маржинальность. Разбираться в финансовых отчетах Озона, иметь представление "
+            "о кредитных инструментах."
+        ),
+        link="https://bluerise.getcourse.ru/PRO_Finance",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Финансы».",
+    ),
+    "all_about_ozon": Course(
+        title="Всё про Озон",
+        description=(
+            "Все 4 блока курсов PRO логистику, PRO рекламу, PRO аналитику, PRO финансы "
+            "в одном со скидкой 20%."
+        ),
+        link="https://bluerise.getcourse.ru/all_about_ozon",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты комплекта «Всё про Озон».",
+    ),
+}
+
+
+SPECIAL_COURSES = {
+    "pro_design": Course(
+        title="PRO Дизайн",
+        description=(
+            "Курс «PRO Дизайн» — для тех, кто хочет понять принципы продающей инфографики, "
+            "уберечь себя от ошибок в дизайне карточек товара, которые ведут к снижению CTR, "
+            "научиться выстраивать взаимоотношения с дизайнерами и «считывать» их квалификацию."
+        ),
+        link="https://bluerise.getcourse.ru/PRO_design",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «PRO Дизайн».",
+    ),
+    "sxr_ai": Course(
+        title="Нейросети от SXR Studio",
+        description=(
+            "Курс по нейросетям от SXR Studio для тех, кто смотрит в будущее и хочет "
+            "научиться генерировать нейро-контент для своих карточек товара."
+        ),
+        link="https://bluerise.getcourse.ru/SXR_AI",
+        invoice_text="Здравствуйте, мне нужен счет для оплаты курса «Нейросети от SXR Studio».",
+    ),
+}
+
+
+def tg_link(username: str, text: str) -> str:
+    return f"https://t.me/{username}?text={quote(text)}"
+
+
+def main_menu_kb() -> ReplyKeyboardMarkup:
+    return ReplyKeyboardMarkup(
+        keyboard=[
+            [KeyboardButton(text=BTN_COURSES)],
+            [KeyboardButton(text=BTN_CALC)],
+            [KeyboardButton(text=BTN_PARTNERSHIP)],
+            [KeyboardButton(text=BTN_CONSULT)],
+        ],
+        resize_keyboard=True,
+    )
+
+
+def courses_menu_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="📚 Предзаписанные курсы", callback_data="courses:pre")],
+            [InlineKeyboardButton(text="🆕 Новинки и потоки", callback_data="courses:new")],
+            [InlineKeyboardButton(text="🔶 Бесплатные вебинары по ЯМ", callback_data="courses:webinars")],
+            [InlineKeyboardButton(text="❓ Помощь с выбором курса", callback_data="courses:help")],
+            [InlineKeyboardButton(text="🛠️ Техническая поддержка", callback_data="courses:support")],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
+        ]
+    )
+
+
+def pre_courses_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="🚀 Ozon: Начальный уровень", callback_data="pre:beginner")],
+            [InlineKeyboardButton(text="⚡ Ozon: Продвинутый уровень", callback_data="pre:advanced")],
+            [InlineKeyboardButton(text="🛠️ Спецкурсы и инструменты", callback_data="pre:special")],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
+        ]
+    )
+
+
+def course_actions_kb(course: Course) -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [
+                InlineKeyboardButton(
+                    text="Узнать подробности и купить курс",
+                    url=course.link,
+                )
+            ],
+            [
+                InlineKeyboardButton(
+                    text="Выставить счет для оплаты с р/с",
+                    url=tg_link(PRO_CONTACT, course.invoice_text),
+                )
+            ],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
+        ]
+    )
+
+
+def advanced_courses_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="PRO логистику", callback_data="advanced:pro_logistics")],
+            [InlineKeyboardButton(text="PRO рекламу", callback_data="advanced:pro_ads")],
+            [InlineKeyboardButton(text="PRO Аналитику", callback_data="advanced:pro_analytics")],
+            [InlineKeyboardButton(text="PRO Финансы", callback_data="advanced:pro_finance")],
+            [InlineKeyboardButton(text="Всё про Озон", callback_data="advanced:all_about_ozon")],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
+        ]
+    )
+
+
+def special_courses_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="PRO Дизайн", callback_data="special:pro_design")],
+            [InlineKeyboardButton(text="Нейросети от SXR Studio", callback_data="special:sxr_ai")],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="pre:back")],
+        ]
+    )
+
+
+def help_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [
+                InlineKeyboardButton(
+                    text="Написать в поддержку",
+                    url=tg_link(HELP_CONTACT, "Добрый день. Помогите с выбором курса."),
+                )
+            ],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
+        ]
+    )
+
+
+def tech_support_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [
+                InlineKeyboardButton(
+                    text="Написать в поддержку",
+                    url=tg_link(
+                        PRO_CONTACT,
+                        "Добрый день. Возникла техническая проблема: [опишите, пожалуйста].",
+                    ),
+                )
+            ],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
+        ]
+    )
+
+
+def webinars_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [
+                InlineKeyboardButton(
+                    text="Вебинар тут",
+                    url="https://bluerise.getcourse.ru/teach/control/stream/view/id/934642226",
+                )
+            ],
+            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
+        ]
+    )
+
+
+def new_courses_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="📚 Предзаписанные курсы", callback_data="courses:pre")],
+            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
+            [InlineKeyboardButton(text="↩️ Назад", callback_data="courses:back")],
+        ]
+    )
+
+
+def calculator_kb() -> InlineKeyboardMarkup:
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [
+                InlineKeyboardButton(
+                    text="Калькулятор здесь",
+                    url="https://docs.google.com/spreadsheets/d/1e4AVf3dDueEoPxQHeKOVFHgSpbcLvnbGnn6_I6ApRwg/edit?gid=246238448#gid=246238448",
+                )
+            ],
+            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
+        ]
+    )
+
+
+def consult_kb() -> Optional[InlineKeyboardMarkup]:
+    if not CONSULT_FORM_URL:
+        return None
+    return InlineKeyboardMarkup(
+        inline_keyboard=[
+            [InlineKeyboardButton(text="📅 ЗАПОЛНИТЬ ЗАЯВКУ", url=CONSULT_FORM_URL)]
+        ]
+    )
+
+
+dp = Dispatcher()
+
+
+@dp.message(CommandStart())
+async def start(m: Message) -> None:
+    name = m.from_user.first_name if m.from_user else "друг"
+    await m.answer(
+        f"Приветствую, {name}!\n\n"
+        "Это «Синий рассвет» — здесь мы систематизируем бизнес на маркетплейсах: "
+        "от основ до продвинутых стратегий.",
+        reply_markup=main_menu_kb(),
+    )
+
+
+@dp.message(F.text == BTN_COURSES)
+async def courses_menu(m: Message) -> None:
+    await m.answer("Выберите раздел 👇", reply_markup=courses_menu_kb())
+
+
+@dp.callback_query(F.data == "courses:back")
+async def courses_back(c: CallbackQuery) -> None:
+    await c.message.answer("Главное меню 👇", reply_markup=main_menu_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data == "courses:pre")
+async def pre_courses(c: CallbackQuery) -> None:
+    text = (
+        "Все курсы в нашей линейке предзаписанные и с постоянными апдейтами под изменения в Озон.\n\n"
+        "Не надо ждать потоков, курс идет по принципу «Купи и смотри». Доступ к нему и ко всем его "
+        "изменениям остается навсегда.\n\n"
+        "Вся линейка курсов задумана, как постоянно обновляемая База Знаний, с помощью которых вы "
+        "сможете обучать новых сотрудников и постоянно актуализировать свои знания. Доступ ко всем "
+        "обновлениям купленного курса БЕСПЛАТНЫЙ."
+    )
+    await c.message.answer(text, reply_markup=pre_courses_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data == "pre:beginner")
+async def pre_beginner(c: CallbackQuery) -> None:
+    await c.message.answer(
+        f"<b>{BEGINNER_COURSE.title}</b>\n\n{BEGINNER_COURSE.description}",
+        reply_markup=course_actions_kb(BEGINNER_COURSE),
+        parse_mode=ParseMode.HTML,
+    )
+    await c.answer()
+
+
+@dp.callback_query(F.data == "pre:advanced")
+async def pre_advanced(c: CallbackQuery) -> None:
+    await c.message.answer(
+        "Продвинутый уровень: выберите курс 👇",
+        reply_markup=advanced_courses_kb(),
+    )
+    await c.answer()
+
+
+@dp.callback_query(F.data == "pre:special")
+async def pre_special(c: CallbackQuery) -> None:
+    await c.message.answer(
+        "Спецкурсы и инструменты: выберите курс 👇",
+        reply_markup=special_courses_kb(),
+    )
+    await c.answer()
+
+
+@dp.callback_query(F.data == "pre:back")
+async def pre_back(c: CallbackQuery) -> None:
+    await c.message.answer("Наши курсы 👇", reply_markup=courses_menu_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data.startswith("advanced:"))
+async def advanced_course(c: CallbackQuery) -> None:
+    key = c.data.split(":", 1)[1]
+    course = ADVANCED_COURSES.get(key)
+    if not course:
+        await c.answer("Курс не найден.", show_alert=True)
+        return
+    await c.message.answer(
+        f"<b>{course.title}</b>\n\n{course.description}",
+        reply_markup=course_actions_kb(course),
+        parse_mode=ParseMode.HTML,
+    )
+    await c.answer()
+
+
+@dp.callback_query(F.data.startswith("special:"))
+async def special_course(c: CallbackQuery) -> None:
+    key = c.data.split(":", 1)[1]
+    course = SPECIAL_COURSES.get(key)
+    if not course:
+        await c.answer("Курс не найден.", show_alert=True)
+        return
+    await c.message.answer(
+        f"<b>{course.title}</b>\n\n{course.description}",
+        reply_markup=course_actions_kb(course),
+        parse_mode=ParseMode.HTML,
+    )
+    await c.answer()
+
+
+@dp.callback_query(F.data == "courses:new")
+async def courses_new(c: CallbackQuery) -> None:
+    text = (
+        "Здесь будут появляться анонсы новых курсов и специальных форматов обучения.\n\n"
+        "Мы регулярно работаем над тем, чтобы обучение было еще полезнее и эффективнее. "
+        "Возможно, это будут обновленные программы или новые проекты.\n\n"
+        "Хотите быть в курсе всех новинок первыми?\n"
+        f"👉 Подпишитесь на наш канал: {CHANNEL_URL}\n\n"
+        "А пока все наши основные курсы для старта и уверенного роста уже ждут вас в "
+        "📚 Предзаписанные курсы."
+    )
+    await c.message.answer(text, reply_markup=new_courses_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data == "courses:webinars")
+async def courses_webinars(c: CallbackQuery) -> None:
+    text = (
+        "Поздравляю! Вам открыт доступ к вебинарам по Яндекс маркету.\n\n"
+        "Что вы получите внутри:\n"
+        "1. Запись 3-х дней вебинаров по ЯМ, в которых разобраны все аспекты работы с площадкой.\n"
+        "2. Ссылка на чат единомышленников.\n\n"
+        "Кстати, подписывайтесь на мой канал «Синий рассвет» — там куча полезной информации "
+        "по Озон и про бизнес на маркетплейсах в целом."
+    )
+    await c.message.answer(text, reply_markup=webinars_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data == "courses:help")
+async def courses_help(c: CallbackQuery) -> None:
+    text = (
+        "Чтобы подобрать курс, который решит именно вашу задачу, напишите напрямую "
+        "@yashiann. Опишите ваш опыт и цель — и вы получите персональную рекомендацию."
+    )
+    await c.message.answer(text, reply_markup=help_kb())
+    await c.answer()
+
+
+@dp.callback_query(F.data == "courses:support")
+async def courses_support(c: CallbackQuery) -> None:
+    text = (
+        "По любым техническим вопросам (доступ к курсам, проблемы с оплатой) "
+        "напишите напрямую @ilya_bolsheglazov. Опишите проблему как можно подробнее — "
+        "это поможет решить её быстрее."
+    )
+    await c.message.answer(text, reply_markup=tech_support_kb())
+    await c.answer()
+
+
+@dp.message(F.text == BTN_CALC)
+async def calculator(m: Message) -> None:
+    text = (
+        "Поздравляю! Вам открыт доступ к обновленному калькулятору.\n\n"
+        "Что вы получите внутри:\n"
+        "1. Калькулятор с FBS и новой логистикой.\n"
+        "2. Подробное видеообъяснение к калькулятору: как пользоваться, что ввести, на что смотреть.\n\n"
+        "Кстати, подписывайтесь на мой канал «Синий рассвет». Там куча полезной информации по Озон "
+        "и про бизнес на маркетплейсах в целом."
+    )
+    await m.answer(text, reply_markup=calculator_kb())
+
+
+@dp.message(F.text == BTN_PARTNERSHIP)
+async def partnership(m: Message) -> None:
+    text = (
+        "Привет! 👋\n\n"
+        "Этот раздел — для обсуждения профессионального партнёрства. Мы открыты к совместным "
+        "проектам, интеграциям, аффилированным программам и другим форматам взаимовыгодного "
+        "сотрудничества.\n\n"
+        "Чтобы предложить свою идею, напишите напрямую @yashiann в Telegram. В первом сообщении "
+        "кратко опишите суть предложения — это поможет начать диалог максимально предметно.\n\n"
+        "Жду вашего сообщения! 🤝"
+    )
+    await m.answer(text, reply_markup=ReplyKeyboardRemove())
+
+
+@dp.message(F.text == BTN_CONSULT)
+async def consult(m: Message) -> None:
+    text = (
+        "Индивидуальный разбор вашего кейса. Мы проанализируем текущую ситуацию, определим точки "
+        "роста и сформируем план на ближайший период.\n\n"
+        "Формат и продолжительность консультации определяются под ваш запрос.\n\n"
+        "Для записи заполните, пожалуйста, форму. Это поможет подготовиться к нашей встрече."
+    )
+    kb = consult_kb()
+    if kb:
+        await m.answer(text, reply_markup=kb)
+        return
+    await m.answer(
+        f"{text}\n\nСсылка на форму пока не указана. Добавьте CONSULTATION_FORM_URL в окружение.",
+        reply_markup=ReplyKeyboardRemove(),
+    )
+
+
+@dp.message()
+async def fallback(m: Message) -> None:
+    await m.answer("Используйте меню ниже 👇", reply_markup=main_menu_kb())
+
+
+async def main() -> None:
+    if not BOT_TOKEN:
+        raise RuntimeError("BOT_TOKEN is empty. Set it in environment variables.")
+
+    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
+    await dp.start_polling(bot)
+
+
+if __name__ == "__main__":
+    asyncio.run(main())
 
EOF
)
