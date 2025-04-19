import logging
import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv
import openai
import asyncio

# Загрузка переменных среды (только локально, если не Railway)
if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Кнопки
menu_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 Оплата", callback_data="pay")],
    [InlineKeyboardButton(text="📤 Отправить чек", callback_data="send_check")],
    [InlineKeyboardButton(text="📋 Все команды", callback_data="menu")],
    [InlineKeyboardButton(text="📞 Связаться с админом", url="https://t.me/mr_admincmd")]
])

# Стартовое сообщение
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я — <b>Вера Логик</b> 🤖\n"
        "Я помогу тебе с математикой.\n\n"
        "<b>📅 15 дней бесплатно</b>, потом 25,000 сум/мес.\n\n"
        "💳 Оплата: /pay\n"
        "📤 Отправить чек: /send_check\n"
        "📋 Все команды: /menu",
        reply_markup=menu_kb
    )

# Команда /menu
@dp.message_handler(commands=["menu"])
async def menu_handler(message: types.Message):
    await message.answer(
        "📋 <b>Команды:</b>\n"
        "/start — начать сначала\n"
        "/menu — показать это меню\n"
        "/pay — как оплатить\n"
        "/send_check — отправить чек"
    )

# Команда /pay
@dp.message_handler(commands=["pay"])
async def pay_handler(message: types.Message):
    await message.answer(
        "💳 <b>Оплата</b>\n"
        "Переведите 25,000 сум на карту: <code>5614 6822 0399 1668</code>\n"
        "После оплаты отправьте фото чека командой /send_check"
    )

# Команда /send_check
@dp.message_handler(commands=["send_check"])
async def send_check_handler(message: types.Message):
    await message.answer("📤 Пожалуйста, отправьте фото чека одним сообщением.")

# Получение чека
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def receive_check(message: types.Message):
    user_id = message.from_user.id
    photo = message.photo[-1].file_id
    file = await bot.get_file(photo)
    file_path = file.file_path
    file_name = f"check_images/user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await bot.download_file(file_path, file_name)
    await bot.send_message(ADMIN_ID, f"🧾 Новый чек от пользователя <code>{user_id}</code>:")
    await bot.send_photo(ADMIN_ID, photo=photo)
    await message.answer("✅ Чек отправлен на проверку. Ожидайте подтверждение.")

# Команда /admin
@dp.message_handler(commands=["admin"])
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = await get_user_count()
    await message.answer(f"🛠 Панель администратора\n👥 Подписчиков: <b>{count}</b>")

# Подсчёт пользователей
async def get_user_count():
    conn = sqlite3.connect("subscribers.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined TIMESTAMP)")
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count

# Добавление пользователя
async def add_user(user_id):
    conn = sqlite3.connect("subscribers.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined TIMESTAMP)")
    cur.execute("INSERT OR IGNORE INTO users (user_id, joined) VALUES (?, ?)", (user_id, datetime.now()))
    conn.commit()
    conn.close()

# Обработка всех новых сообщений — задача или команда
@dp.message_handler()
async def solve_math(message: types.Message):
    if message.text.startswith("/"):
        return
    await add_user(message.from_user.id)
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — профессиональный репетитор по математике. Отвечай строго по делу и с пошаговым решением."},
                {"role": "user", "content": message.text}
            ]
        )
        reply = resp.choices[0].message.content
        await message.answer(f"{reply}\n\n👩🏻‍🏫 <i>С тобой была Вера Логик</i>")
    except Exception as e:
        await message.answer("Произошла ошибка при обращении к AI. Попробуй позже.")

# Запуск бота
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
