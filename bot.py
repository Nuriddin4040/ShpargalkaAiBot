import os
import sqlite3
import openai
import logging
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv

# Настройки
logging.basicConfig(level=logging.INFO)
load_dotenv()
TELEGRAM_TOKEN = "7809028777:AAE8ez2suhZGe38HOKWEEr04qNldlkpAK5Q"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1754012821"))

# Инициализация
openai.api_key = OPENAI_API_KEY
DB_PATH = "subscribers.db"
CHECK_DIR = "check_images"
os.makedirs(CHECK_DIR, exist_ok=True)

# FSM для рассылки
class Broadcast(StatesGroup):
    waiting_for_message = State()

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=storage)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            start_date TEXT,
            is_pro INTEGER DEFAULT 0,
            paid_until TEXT
        )
    """)
    conn.commit()
    conn.close()

# /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscribers WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO subscribers(user_id, start_date) VALUES (?, ?)", (user_id, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📋 Меню команд")
    await message.answer(
        "Привет! Я — <b>Вера Логик</b> 🤖\n"
        "Я помогу тебе с математикой.\n\n"
        "📅 <b>15 дней бесплатно</b>, потом 25,000 сум/мес.\n\n"
        "📸 Оплата: /pay\n🧾 Отправить чек: /send_check\n📋 Все команды: /menu",
        reply_markup=keyboard
    )

# /menu
@dp.message_handler(commands=['menu'])
async def cmd_menu(message: types.Message):
    await message.answer(
        "📋 <b>Команды:</b>\n\n"
        "/start — начать сначала\n"
        "/menu — показать это меню\n"
        "/pay — как оплатить\n"
        "/send_check — отправить чек"
    )

# /admin
@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
    conn.close()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📣 Рассылка")
    await message.answer(f"🔧 Панель администратора\n👥 Подписчиков: {count}", reply_markup=keyboard)

# Рассылка по кнопке
@dp.message_handler(lambda m: m.text == "📣 Рассылка")
async def ask_broadcast_text(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("✉️ Введите текст, который хотите отправить подписчикам:")
    await Broadcast.waiting_for_message.set()

@dp.message_handler(state=Broadcast.waiting_for_message, content_types=types.ContentTypes.TEXT)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.finish()
        return
    text = message.text
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM subscribers").fetchall()
    conn.close()
    count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, text)
            count += 1
        except:
            continue
    await message.answer(f"✅ Рассылка завершена. Отправлено: {count}")
    await state.finish()

# /pay
@dp.message_handler(commands=["pay"])
async def pay_info(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="💳 Скопировать карту", callback_data="copy_card"))
    await message.answer(
        "💵 Оплата 25,000 сум на карту:\n<code>5614 6822 0399 1668</code>\n\nПосле оплаты — /send_check",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data == "copy_card")
async def copy_card(callback: types.CallbackQuery):
    await callback.answer("Карта скопирована: 5614 6822 0399 1668", show_alert=True)

# /send_check
@dp.message_handler(commands=['send_check'])
async def send_check(message: types.Message):
    await message.answer("📸 Пришлите фото или скриншот чека")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: types.Message):
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    user_id = message.from_user.id
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"user_{user_id}_{timestamp}.jpg"
    await bot.download_file(file.file_path, f"{CHECK_DIR}/{filename}")
    await message.reply("✅ Чек сохранён, админ скоро проверит")
    await bot.send_message(ADMIN_ID, f"📥 Чек от {user_id}: {filename}")

# /approve
@dp.message_handler(commands=['approve'])
async def approve_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        return await message.reply("Формат: /approve <user_id>")
    user_id = int(parts[1])
    paid_until = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE subscribers SET is_pro = 1, paid_until = ? WHERE user_id = ?", (paid_until, user_id))
    conn.commit()
    conn.close()
    await bot.send_message(user_id, f"✅ Подписка активна до {paid_until}")
    await message.reply(f"✅ Пользователь {user_id} подтверждён")

# Проверка доступа
def has_access(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT start_date, is_pro, paid_until FROM subscribers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    start_date, is_pro, paid_until = row
    today = datetime.date.today()
    if is_pro == 1 and paid_until:
        return today <= datetime.date.fromisoformat(paid_until)
    return (today - datetime.date.fromisoformat(start_date)).days <= 15

# Ответ на математику
@dp.message_handler(lambda m: m.text and not m.text.startswith('/'), state=None)
async def handle_math(message: types.Message):
    user_id = message.from_user.id
    if not has_access(user_id):
        return await message.reply("🔒 Доступ закрыт. Оплатите через /pay и пришлите чек /send_check")
    try:
        resp = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты — репетитор по математике. Дай пошаговое решение."},
                {"role": "user", "content": message.text}
            ]
        )
        ai_text = resp.choices[0].message.content.strip()
        await message.reply(f"📘 <b>Ответ:</b>\n\n<pre>{ai_text}</pre>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка GPT: {e}")
        await message.reply("⚠️ Ошибка при ответе от ИИ")

# Запуск
if __name__ == '__main__':
    init_db()
    executor.start_polling(dp, skip_updates=True)
