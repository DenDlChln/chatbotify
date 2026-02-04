import os
import json
import logging
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import datetime, time
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            config = data.get('cafe', {})
            return {
                'name': config.get('name', 'Кофейня «Уют» ☕'),
                'phone': config.get('phone', '+7 989 273-67-56'),
                'admin_chat_id': config.get('admin_chat_id', 1471275603),
                'menu': config.get('menu', {"☕ Капучино": 250, "🥛 Латте": 270})
            }
    except:
        return {
            "name": "Кофейня «Уют» ☕",
            "phone": "+7 989 273-67-56",
            "admin_chat_id": 1471275603,
            "menu": {"☕ Капучино": 250, "🥛 Латте": 270}
        }

cafe_config = load_config()
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = dict(cafe_config["menu"])

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10007))

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
    await message.answer(f"<b>{CAFE_NAME}</b>\n☕ Выберите:", reply_markup=get_menu_keyboard())
    logger.info(f"👤 /start от {message.from_user.id}")

@dp.message_handler(lambda m: m.text in MENU)
async def drink_selected(message: types.Message, state: FSMContext):
    drink = message.text
    price = MENU[drink]
    await state.finish()
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    await message.answer(f"🥤 <b>{drink}</b>\n💰 <b>{price}₽</b>\n📝 Сколько?", reply_markup=get_quantity_keyboard())

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Отменено ☕", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text[0])
        if 1 <= qty <= 5:
            data = await state.get_data()
            total = data['price'] * qty
            await state.update_data(quantity=qty, total=total)
            await OrderStates.waiting_for_confirmation.set()
            await message.answer(f"📋 <b>{data['drink']} ×{qty} = {total}₽</b>\n📞 {CAFE_PHONE}", reply_markup=get_confirm_keyboard())
            return
    except:
        pass
    
    data = await state.get_data()
    await message.answer(f"{data['drink']} — {data['price']}₽\n1️⃣-5️⃣", reply_markup=get_quantity_keyboard())

@dp.message_handler(state=OrderStates.waiting_for_confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "✅ Подтвердить":
        await send_order_to_admin({
            'user_id': message.from_user.id,
            'first_name': message.from_user.first_name or "Гость",
            'drink': data['drink'],
            'quantity': data['quantity'],
            'total': data['total']
        })
        await state.finish()
        await message.answer(f"🎉 <b>ЗАКАЗ #{message.from_user.id}</b>\n📞 {CAFE_PHONE}")
        return
    
    await state.finish()
    await message.answer("🔙 Меню ☕", reply_markup=get_menu_keyboard())

async def send_order_to_admin(order_data):
    try:
        await bot.send_message(ADMIN_ID, f"🔔 ЗАКАЗ #{order_data['user_id']}\n{order_data['drink']} ×{order_data['quantity']} = {order_data['total']}₽")
        logger.info(f"✅ Заказ #{order_data['user_id']}")
    except:
        pass

@dp.message_handler()
async def echo(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(f"{CAFE_NAME}\n☕ Выберите:", reply_markup=get_menu_keyboard())

# ========================================
# ✅ RENDER PORT — Критично для Web Service!
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(f'v8.15 LIVE - {CAFE_NAME}'.encode())
    
    def log_message(self, *args): pass

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"🌐 HTTP на PORT {PORT}")
    server.serve_forever()

# ========================================
if __name__ == '__main__':
    logger.info(f"🚀 v8.15 Web Service — {CAFE_NAME}")
    
    # ✅ 1. HTTP сервер для Render (обязательно!)
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # ✅ 2. Telegram Bot polling
    executor.start_polling(dp, skip_updates=True)
