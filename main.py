import os
import json
import logging
import threading
import signal
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('cafe', {})
    except:
        return {
            "name": "Кофейня «Уют» ☕",
            "phone": "+7 989 273-67-56", 
            "admin_chat_id": 1471275603,
            "menu": {
                "☕ Капучино": 250,
                "🥛 Латте": 270,
                "🍵 Чай": 180,
                "⚡ Эспрессо": 200
            }
        }

cafe_config = load_config()
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = dict(cafe_config["menu"])

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN обязателен!")

PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"

# ✅ КАРТИНКИ
ORDER_PHOTO_CLIENT = "https://i.imgur.com/8zX5z0q.jpg"
ORDER_PHOTO_ADMIN = "https://i.imgur.com/Q7jKz8m.jpg"

# ========================================
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_confirmation = State()

# ========================================
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for drink in MENU:
        kb.add(drink)
    kb.row("📞 Позвонить")
    return kb

def get_quantity_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("1️⃣", "2️⃣", "3️⃣")
    kb.row("4️⃣", "5️⃣", "🔙 Отмена")
    return kb

def get_confirm_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("✅ Подтвердить", "🔙 Меню")
    return kb

# ========================================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        f"<b>{CAFE_NAME}</b>\n\n"
        f"☕ <b>Выберите напиток:</b>",
        reply_markup=get_menu_keyboard()
    )
    logger.info(f"👤 /start от {message.from_user.id}")

@dp.message_handler(lambda m: m.text in MENU)
async def drink_selected(message: types.Message, state: FSMContext):
    drink = message.text
    price = MENU[drink]
    await state.finish()
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    await message.answer(
        f"🥤 <b>{drink}</b>\n"
        f"💰 <b>{price} ₽</b>\n\n"
        f"📝 <b>Сколько порций?</b>",
        reply_markup=get_quantity_keyboard()
    )
    logger.info(f"🥤 {drink} от {message.from_user.id}")

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logger.info(f"📊 {message.text} от {message.from_user.id}")
    
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Заказ отменён ☕", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text[0])
        if 1 <= qty <= 5:
            data = await state.get_data()
            total = data['price'] * qty
            await state.update_data(quantity=qty, total=total)
            await OrderStates.waiting_for_confirmation.set()
            await message.answer(
                f"<b>📋 ПОДТВЕРДИТЕ ЗАКАЗ</b>\n\n"
                f"🥤 <b>{data['drink']}</b>\n"
                f"📊 {qty} порций\n"
                f"💰 <b>{total} ₽</b>\n\n"
                f"📞 <code>{CAFE_PHONE}</code>",
                reply_markup=get_confirm_keyboard()
            )
            return
    except:
        pass
    
    data = await state.get_data()
    await message.answer(
        f"🥤 <b>{data['drink']}</b> — {data['price']}₽\n\n"
        "<b>1️⃣-5️⃣</b> или <b>🔙 Отмена</b>",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "✅ Подтвердить":
        order_data = {
            'user_id': message.from_user.id,
            'first_name': message.from_user.first_name or "Гость",
            'drink': data['drink'],
            'quantity': data['quantity'],
            'total': data['total']
        }
        
        # ✅ КАРТИНКА КЛИЕНТУ
        await bot.send_photo(
            chat_id=message.from_user.id,
            photo=ORDER_PHOTO_CLIENT,
            caption=f"🎉 <b>ЗАКАЗ #{message.from_user.id} ПРИНЯТ!</b>\n\n"
                   f"🥤 {data['drink']}\n"
                   f"📊 {data['quantity']} порций\n"
                   f"💰 <b>{data['total']} ₽</b>\n\n"
                   f"📞 <code>{CAFE_PHONE}</code>\n"
                   f"✅ <i>Готовим! ⏳</i>",
            reply_markup=get_menu_keyboard(),
            parse_mode=types.ParseMode.HTML
        )
        
        # ✅ КАРТИНКА АДМИНУ
        await send_order_to_admin(order_data)
        
        await state.finish()
        logger.info(f"✅ Заказ #{message.from_user.id}")
        return
    
    await state.finish()
    await message.answer("🔙 В меню ☕", reply_markup=get_menu_keyboard())

async def send_order_to_admin(order_data):
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']} ₽</b>\n\n"
        f"📞 <code>{CAFE_PHONE}</code>"
    )
    try:
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=ORDER_PHOTO_ADMIN,
            caption=text,
            parse_mode=types.ParseMode.HTML
        )
        logger.info(f"✅ Заказ #{order_data['user_id']} админу")
    except Exception as e:
        logger.error(f"❌ Админ: {e}")

@dp.message_handler()
async def echo(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(f"{CAFE_NAME}\n☕ Выберите:", reply_markup=get_menu_keyboard())

# ========================================
# ✅ RENDER HTTP SERVER
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(f'v8.17 LIVE - {CAFE_NAME}'.encode())
    
    def log_message(self, *args): pass

http_server = None
def run_http_server():
    global http_server
    http_server = HTTPServer((HOST, PORT), HealthHandler)
    logger.info(f"🌐 HTTP сервер на {HOST}:{PORT}")
    http_server.serve_forever()

# ✅ GRACEFUL SHUTDOWN
def signal_handler(sig, frame):
    logger.info("🛑 Получен сигнал остановки...")
    if http_server:
        http_server.shutdown()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ========================================
async def on_startup(dp):
    logger.info(f"🚀 v8.17 LIVE — {CAFE_NAME}")
    logger.info(f"✅ Бот: CafeBotify")
    logger.info(f"📞 Админ: {ADMIN_ID}")
    logger.info(f"🌐 PORT: {PORT}")

async def on_shutdown(dp):
    logger.info("🛑 v8.17 STOP")
    await dp.storage.close()
    await dp.storage.wait_closed()

# ========================================
if __name__ == '__main__':
    logger.info(f"🎬 CAFEBOTIFY v8.17 — {CAFE_NAME}")
    
    # ✅ 1. HTTP сервер (отдельный поток)
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # ✅ 2. Telegram Bot (CRITICAL: skip_updates=True!)
    executor.start_polling(
        dp, 
        skip_updates=True,  # ← ПРОТИВ 409 CONFLICT!
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
