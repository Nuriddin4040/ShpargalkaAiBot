import os
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils import executor
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import hbold
from aiogram import executor
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ─── DATABASE ───────────────────────────────
conn = sqlite3.connect("users.db")
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS subscribers (
    user_id INTEGER PRIMARY KEY,
    start_date TEXT,
    is_pro INTEGER DEFAULT 0,
    paid_until TEXT
)''')
conn.commit()


# ─── ACCESS CHECK ───────────────────────────
def has_access(user_id: int):
    cur.execute("SELECT start_date, is_pro, paid_until FROM subscribers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        start_date_str, is_pro, paid_until_str = row
        if is_pro:
            return True
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        if datetime.now() <= start_date + timedelta(days=15):
            return True
        return False
    return False


# ─── INLINE KEYBOARD ────────────────────────
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💸 Оплата", callback_data="pay"),
        InlineKeyboardButton("📤 Отправить чек", callback_data="send_check"),
        InlineKeyboardButton("📋 Все команды", callback_data="menu"),
        InlineKeyboardButton("📞 Связь с админом", url="https://t.me/mr_admincmd")
    )
    return markup


# ─── /START ──────────────────────────────────
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    uid = message.from_user.id
    cur.execute("SELECT * FROM subscribers WHERE user_id = ?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO subscribers (user_id, start_date) VALUES (?, ?)", (uid, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
    await message.answer(
        f"Привет! Я — <b>Вера Логик</b> 🤖\n"
        f"Я помогу тебе с математикой.\n\n"
        f"🕒 <b>15 дней бесплатно</b>, потом 25,000 сум/мес.\n\n"
        f"💸 Оплата: /pay\n"
        f"📤 Отправить чек: /send_check\n"
        f"📋 Все команды: /menu",
        reply_markup=main_menu()
    )


# ─── /MENU ───────────────────────────────────
@dp.message_handler(commands=["menu"])
async def menu(message: types.Message):
    await message.answer(
        "<b>📌 Команды:</b>\n"
        "/start — начать сначала\n"
        "/menu — показать это меню\n"
        "/pay — как оплатить\n"
        "/send_check — отправить чек",
        reply_markup=ReplyKeyboardRemove()
    )


# ─── /PAY ────────────────────────────────────
@dp.message_handler(commands=["pay"])
async def pay(message: types.Message):
    await message.answer("💳 Оплата на карту: <code>5614 6822 0399 1668</code>\nПосле оплаты отправь чек с помощью /send_check")


# ─── /SEND_CHECK ─────────────────────────────
@dp.message_handler(commands=["send_check"])
async def send_check(message: types.Message):
    await message.answer("📎 Пришли фото чека сюда. Я передам его админу.")


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_check(message: types.Message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    await bot.send_photo(ADMIN_ID, photo_id, caption=f"🧾 Новый чек от ID {uid}\nПодтвердить: /approve {uid}")
    await message.answer("✅ Чек отправлен. Ожидайте подтверждения.")


# ─── /APPROVE ────────────────────────────────
@dp.message_handler(lambda m: m.text.startswith("/approve") and m.from_user.id == ADMIN_ID)
async def approve(message: types.Message):
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        paid_until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        cur.execute("UPDATE subscribers SET is_pro = 1, paid_until = ? WHERE user_id = ?", (paid_until, user_id))
        conn.commit()
        await bot.send_message(user_id, "✅ Оплата подтверждена! У тебя есть доступ на 30 дней. Успешной учёбы с Верой Логик 🧠")
        await message.answer("✅ Подписка активирована.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# ─── /ADMIN ──────────────────────────────────
@dp.message_handler(commands=["admin"])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) FROM subscribers")
    total = cur.fetchone()[0]
    await message.answer(f"🛠 Панель администратора\n👥 Подписчиков: {total}")


# ─── РЕШЕНИЕ ЗАДАЧИ ─────────────────────────
@dp.message_handler()
async def solve_math(message: types.Message):
    uid = message.from_user.id
    if not has_access(uid):
        await message.answer("🚫 Пробный период завершён. Оплати доступ — /pay")
        return

    prompt = f"Ты умный математик. Объясни решение задачи шаг за шагом:\n\n{message.text}"
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response['choices'][0]['message']['content']
        await message.answer(f"{reply}\n\n— <i>Вера Логик</i> 🧠")
    except Exception as e:
        await message.answer(f"Ошибка при получении ответа от AI: {e}")


# ─── АВТОРАССЫЛКА НАПОМИНАНИЙ ────────────────
from asyncio import sleep
from aiogram import executor

async def reminder_loop():
    while True:
        cur.execute("SELECT user_id FROM subscribers")
        users = cur.fetchall()
        for (user_id,) in users:
            await bot.send_message(user_id, "📚 Не забывай практиковаться с Вера Логик! Пришли новую задачу — и я помогу.")
            await sleep(2)
        await sleep(3600 * 4)  # каждые 4 часа

from aiogram import executor

if __name__ == "__main__":
    from asyncio import get_event_loop
    loop = get_event_loop()
    loop.create_task(reminder_loop())
    executor.start_polling(dp, skip_updates=True)
