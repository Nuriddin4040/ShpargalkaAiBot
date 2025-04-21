import logging
import asyncio
import os
import aiosqlite
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Кнопка связи с админом
menu_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📬 Связаться с админом", url="https://t.me/mr_admincmd")]
])

# Промт GPT-4
PROMPT = """Ты опытный репетитор по математике. Твоя задача — решать задачи и подробно объяснять решение по шагам.
Формат ответа:
1. Условие.
2. Пошаговое объяснение.
3. Финальный ответ.
Объясняй так, чтобы понял даже новичок."""

# Инициализация БД
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()

# Сохранение пользователя
async def save_user(user_id: int):
    async with aiosqlite.connect("users.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

# Получение количества пользователей
async def count_users():
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await save_user(message.from_user.id)
    await message.answer(
        "<b>Привет, я Вера Логик — твой AI-репетитор по математике 🧠</b>\n\nПросто пришли мне свою задачу, и я помогу тебе решить её пошагово.",
        reply_markup=menu_kb
    )

# Команда /admin
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ У вас нет доступа к админ-панели.")
    count = await count_users()
    panel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="send_broadcast")]
    ])
    await message.answer(f"<b>👑 Админ-панель</b>\n📊 Подписчиков: <b>{count}</b>", reply_markup=panel)

# Приём команды /send
@dp.callback_query(F.data == "send_broadcast")
async def start_broadcast(callback):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("✏️ Пришли текст, который нужно разослать.")
    dp.workflow_data["awaiting_broadcast"] = True

# Обработка рассылки
@dp.message(F.text)
async def handle_text(message: Message):
    # Админ делает рассылку
    if dp.workflow_data.get("awaiting_broadcast") and message.from_user.id == ADMIN_ID:
        dp.workflow_data["awaiting_broadcast"] = False
        async with aiosqlite.connect("users.db") as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                users = await cursor.fetchall()
                for user in users:
                    try:
                        await bot.send_message(user[0], message.text)
                    except Exception:
                        continue
        return await message.answer("📢 Рассылка завершена.")

    # GPT-4: решение задачи
    await message.answer("Поняла, решаю задачу... 🧠")
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": message.text}
            ]
        )
        await message.answer(response.choices[0].message.content.strip())
    except Exception as e:
        logging.error(e)
        await message.answer("⚠️ Произошла ошибка при обращении к GPT-4. Попробуй позже.")

# Запуск
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
