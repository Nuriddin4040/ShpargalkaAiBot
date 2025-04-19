import os
import sqlite3
import logging
import asyncio
import datetime
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.utils.markdown import hbold
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from aiogram.fsm.strategy import FSMStrategy
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import Router
from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import html
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- Database Setup ---
conn = sqlite3.connect("subscribers.db")
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS subscribers
               (user_id INTEGER PRIMARY KEY, start_date TEXT, is_pro INTEGER DEFAULT 0, paid_until TEXT)''')
conn.commit()

def has_access(user_id):
    cur.execute("SELECT start_date, is_pro, paid_until FROM subscribers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        return False
    start_date, is_pro, paid_until = row
    if is_pro:
        return True
    start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    return (datetime.datetime.now() - start_dt).days <= 15

# --- Command Handlers ---
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    cur.execute("INSERT OR IGNORE INTO subscribers (user_id, start_date) VALUES (?, DATE('now'))", (user_id,))
    conn.commit()
    await message.answer(
        "Привет! Я — <b>Вера Логик</b> 🤖\n"
        "Я помогу тебе с математикой.\n\n"
        "📅 <b>15 дней бесплатно</b>, потом 25,000 сум/мес.\n\n"
        "💳 Оплата: /pay\n"
        "📤 Отправить чек: /send_check\n"
        "📋 Все команды: /menu"
    )

@dp.message(Command("menu"))
async def menu(message: types.Message):
    await message.answer(
        "<b>📋 Команды:</b>\n"
        "/start — начать сначала\n"
        "/menu — показать это меню\n"
        "/pay — как оплатить\n"
        "/send_check — отправить чек"
    )

@dp.message(Command("pay"))
async def pay(message: types.Message):
    await message.answer(
        "💳 Оплата: переведите 25,000 сум на карту\n"
        "<code>5614 6822 0399 1668</code>\n\n"
        "📤 После оплаты отправьте чек через /send_check"
    )

@dp.message(Command("send_check"))
async def send_check(message: types.Message):
    await message.answer("📷 Отправьте фото чека об оплате")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) FROM subscribers")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM subscribers WHERE is_pro = 1")
    paid = cur.fetchone()[0]
    await message.answer(f"👑 Панель администратора\n👥 Подписчиков: {total}\n💰 Подписка: {paid}",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast")]]))

@dp.callback_query(F.data == "broadcast")
async def broadcast_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("📨 Напишите текст для рассылки:")

@dp.message(F.reply_to_message, F.from_user.id == ADMIN_ID)
async def handle_broadcast(message: types.Message):
    cur.execute("SELECT user_id FROM subscribers")
    users = cur.fetchall()
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 Рассылка:\n{message.text}")
        except Exception as e:
            print(f"❌ Не удалось отправить сообщение {uid}: {e}")
    await message.answer("✅ Рассылка завершена")

@dp.message(F.photo)
async def handle_check_photo(message: types.Message):
    if message.caption != "оплата":
        await bot.send_message(ADMIN_ID, f"🧾 Пользователь прислал чек: {message.from_user.full_name}\nID: {message.from_user.id}")
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption="Подтвердите оплату командой:\n/approve <user_id>")
        await message.answer("🧾 Чек отправлен на проверку")

@dp.message(Command("approve"))
async def approve(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        cur.execute("UPDATE subscribers SET is_pro = 1, paid_until = DATE('now', '+30 day') WHERE user_id = ?", (user_id,))
        conn.commit()
        await bot.send_message(user_id, "✅ Оплата подтверждена!\nСпасибо, теперь доступ открыт на 30 дней.")
        await message.answer("✅ Подтверждено")
    except:
        await message.answer("⚠️ Неверный формат. Используй: /approve <user_id>")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer("✋ Просто отправь мне математическую задачу, и я объясню пошагово!\n\nЕсли нужна помощь, пиши админу: @mr_admincmd")

# --- AI Handler ---
@dp.message()
async def solve_math(message: types.Message):
    uid = message.from_user.id
    if not has_access(uid):
        await message.answer("🚫 Пробный период завершён.\n\n💳 Оплата: /pay\n📤 Отправить чек: /send_check")
        return
    prompt = message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты репетитор по математике. Решай задачи пошагово, объясняй понятно, будь дружелюбной."},
                {"role": "user", "content": prompt}
            ]
        )
        text = response.choices[0].message.content
        await message.answer(f"{text}\n\n— <i>Вера Логик</i> 🤓")
    except Exception as e:
        await message.answer("Произошла ошибка при обработке. Попробуй позже.")

# --- Автонапоминание ---
async def auto_notify():
    cur.execute("SELECT user_id FROM subscribers WHERE is_pro = 1")
    for (uid,) in cur.fetchall():
        try:
            await bot.send_message(uid, "📚 Готова новая задача! Просто отправь пример и я помогу.\n— <i>Вера Логик</i> 🤓")
        except:
            pass

scheduler.add_job(auto_notify, "cron", hour=12)

# --- Запуск ---
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
