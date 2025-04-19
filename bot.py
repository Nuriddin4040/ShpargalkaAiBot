import os
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import openai
import asyncio

# Загрузка переменных из Railway Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

openai.api_key = OPENAI_API_KEY

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Подключение к базе данных
conn = sqlite3.connect("users.db")
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS subscribers (
        user_id INTEGER PRIMARY KEY,
        start_date TEXT,
        is_pro INTEGER DEFAULT 0,
        paid_until TEXT
    )
''')
conn.commit()


# Проверка доступа пользователя
def has_access(user_id):
    cur.execute("SELECT start_date, is_pro, paid_until FROM subscribers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        start_date_str, is_pro, paid_until_str = row
        if is_pro and paid_until_str:
            return datetime.now().date() <= datetime.strptime(paid_until_str, "%Y-%m-%d").date()
        elif start_date_str:
            start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            return (datetime.now().date() - start).days <= 15
    return False


# Приветственное сообщение
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cur.execute("SELECT * FROM subscribers WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO subscribers (user_id, start_date) VALUES (?, ?)",
                    (user_id, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()

    await message.answer(
        "Привет! Я — <b>Вера Логик</b> 🤖\n"
        "Я помогу тебе решать математические задачи шаг за шагом.\n\n"
        "🆓 Бесплатно 15 дней, затем подписка: 25 000 сум/мес.\n"
        "💸 Чтобы оплатить — /pay\n"
        "📤 Отправить чек — /send_check\n"
        "📋 Меню команд — /menu"
    )


# Меню команд
@dp.message_handler(commands=["menu"])
async def cmd_menu(message: types.Message):
    await message.answer(
        "<b>📋 Доступные команды:</b>\n"
        "/start — начать сначала\n"
        "/menu — показать это меню\n"
        "/pay — инструкция по оплате\n"
        "/send_check — отправка чека\n"
        "/admin — панель администратора (только для админа)"
    )


# Инструкция по оплате
@dp.message_handler(commands=["pay"])
async def cmd_pay(message: types.Message):
    await message.answer(
        "💳 Для оплаты переведи <b>25,000 сум</b> на карту:\n"
        "<code>5614 6822 0399 1668</code>\n\n"
        "После оплаты — пришли фото чека через /send_check"
    )


# Обработка команды отправки чека
@dp.message_handler(commands=["send_check"])
async def cmd_send_check(message: types.Message):
    await message.answer("📸 Отправь фото чека прямо сюда сообщением.")


# Обработка фото (чека)
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    file_id = message.photo[-1].file_id
    await bot.send_photo(ADMIN_ID, file_id, caption=f"📤 Новый чек от пользователя {user_id}\nПодтвердить: /approve {user_id}")
    await message.answer("✅ Чек отправлен. Ожидай подтверждения.")


# Админ подтверждает оплату
@dp.message_handler(commands=["approve"])
async def cmd_approve(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        until = datetime.now() + timedelta(days=30)
        cur.execute("UPDATE subscribers SET is_pro = 1, paid_until = ? WHERE user_id = ?", (until.strftime("%Y-%m-%d"), user_id))
        conn.commit()
        await bot.send_message(user_id, f"✅ Оплата подтверждена. Подписка активна до <b>{until.strftime('%Y-%m-%d')}</b>")
        await message.answer("✅ Подписка активирована.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# Панель админа
@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) FROM subscribers")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM subscribers WHERE is_pro = 1")
    pro = cur.fetchone()[0]
    await message.answer(f"👥 Всего пользователей: {total}\n💎 Подписчиков PRO: {pro}")


# Решение задач
@dp.message_handler(lambda m: not m.text.startswith("/"))
async def handle_task(message: types.Message):
    user_id = message.from_user.id
    if not has_access(user_id):
        await message.answer("🔒 Доступ ограничен. Чтобы продолжить, оплати через /pay и отправь чек через /send_check")
        return
    prompt = f"Ты репетитор по математике. Объясни решение задачи пошагово:\n{message.text}"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
        await message.answer(f"{reply}\n\n— <i>Вера Логик</i> 🤖")
    except Exception as e:
        await message.answer(f"❌ Ошибка при обращении к ChatGPT: {e}")


# 🔁 Автоматические напоминания
async def reminder_loop():
    while True:
        cur.execute("SELECT user_id, start_date, is_pro, paid_until FROM subscribers")
        users = cur.fetchall()
        for user_id, start_date_str, is_pro, paid_until_str in users:
            if is_pro == 0 and start_date_str:
                start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                days_used = (datetime.now().date() - start).days
                if days_used == 13:
                    try:
                        await bot.send_message(user_id, "⏳ Завтра закончится бесплатный период. Чтобы продолжить, оплати через /pay и отправь чек.")
                    except:
                        pass
        await asyncio.sleep(86400)  # раз в сутки


# Запуск
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(reminder_loop())
    executor.start_polling(dp, skip_updates=True)
