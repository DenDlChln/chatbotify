import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import aiohttp
from aiohttp import web

# ========================================
# ✅ ИСПРАВЛЕННАЯ ЛОГИРОВКА (убираем access_log)
# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# ENV ПЕРЕМЕННЫЕ
# ========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")

PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

MENU = {
    "☕ Капучино": 250,
    "🥛 Латте": 270,
    "🍵 Чай": 180
}

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
# КЛАВИАТУРЫ
# ========================================
def get_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add("☕ Капучино")
    keyboard.add("🥛 Латте")
    keyboard.add("🍵 Чай")
    keyboard.add("📞 Позвонить")
    return keyboard

def get_quantity_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    keyboard.add("1", "2", "3")
    keyboard.add("4", "5", "🔙 Отмена")
    return keyboard

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add("☕ Меню", "📞 Позвонить")
    return keyboard

# ========================================
# ОБРАБОТЧИКИ
# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    logger.info(f"👤 /start от {message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY LIVE!</b>\n\n"
        "👋 Добро пожаловать!\n"
        "Выберите напиток:",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda message: message.text in MENU.keys())
async def drink_selected(message: types.Message, state: FSMContext):
    logger.info(f"🥤 Напиток: {message.text}")
    drink = message.text
    price = MENU[drink]
    
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    
    await message.answer(
        f"✅ <b>{drink}</b>\n"
        f"💰 <b>{price}₽</b>/порция\n\n"
        "📝 Сколько порций?",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logger.info(f"📊 Количество: {message.text}")
    
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Отменено", reply_markup=get_menu_keyboard())
        return
    
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 10:
            await message.answer("❌ 1-10 порций")
            return
        
        data = await state.get_data()
        drink = data['drink']
        price = data['price']
        total = price * quantity
        
        order_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username or "Не указан",
            'first_name': message.from_user.first_name or "Не указано",
            'drink': drink,
            'quantity': quantity,
            'total': total,
            'phone': CAFE_PHONE
        }
        
        await state.finish()
        await send_order_to_admin(order_data)
        
        await message.answer(
            f"✅ <b>ЗАКАЗ ПРИНЯТ!</b>\n\n"
            f"🥤 {drink}\n"
            f"📊 {quantity} шт\n"
            f"💰 <b>{total}₽</b>\n\n"
            f"📞 {CAFE_PHONE}",
            reply_markup=get_main_keyboard()
        )
        
    except ValueError:
        await message.answer("❌ Число (1-10)")

@dp.message_handler(text="☕ Меню")
async def show_menu(message: types.Message):
    text = "🍽️ <b>Меню:</b>\n\n"
    for drink, price in MENU.items():
        text += f"{drink} — <b>{price}₽</b>\n"
    await message.answer(text, reply_markup=get_menu_keyboard())

@dp.message_handler(text="📞 Позвонить")
async def call_phone(message: types.Message):
    await message.answer(f"📞 <b>{CAFE_PHONE}</b>", reply_markup=get_menu_keyboard())

@dp.message_handler()
async def echo(message: types.Message):
    logger.info(f"📨 '{message.text}' от {message.from_user.id}")
    await message.answer("👋 /start", reply_markup=get_menu_keyboard())

# ========================================
# АДМИН
# ========================================
async def send_order_to_admin(order_data):
    text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 {order_data['first_name']} (@{order_data['username']})\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} шт</b>\n"
        f"💰 <b>{order_data['total']}₽</b>\n"
        f"📞 {order_data['phone']}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info(f"✅ Заказ #{order_data['user_id']} админу")
    except Exception as e:
        logger.error(f"❌ Админ ошибка: {e}")

# ========================================
# WEBHOOK (ИСПРАВЛЕН)
# ========================================
async def webhook_handler(request):
    """🚀 ГЛАВНЫЙ WEBHOOK"""
    try:
        logger.info("🔥 WEBHOOK ПОЛУЧЕН")
        
        # Читаем JSON
        update = await request.json()
        update_id = update.get('update_id')
        logger.info(f"📨 Update #{update_id}")
        
        if 'message' in update:
            msg = update['message']
            user_id = msg['from']['id']
            text = msg.get('text', '')
            logger.info(f"💬 {user_id}: '{text[:50]}'")
        
        # Aiogram обработка
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ WEBHOOK OK")
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"💥 WEBHOOK ERROR: {e}")
        return web.Response(text="ERROR", status=500)

async def healthcheck(request):
    return web.Response(text="CafeBotify LIVE ✅", status=200)

async def test_endpoint(request):
    return web.Response(text="TEST OK", status=200)

# ========================================
# STARTUP/SHUTDOWN
# ========================================
async def on_startup(app):
    logger.info("🚀 STARTUP")
    
    # Проверка webhook
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)
    
    info = await bot.get_webhook_info()
    logger.info(f"✅ WEBHOOK: {info.url}")
    
    # Тест админу
    await bot.send_message(ADMIN_ID, "🔥 BOT LIVE! /start")
    logger.info("✅ STARTUP OK")

async def on_shutdown(app):
    await bot.delete_webhook()
    logger.info("🛑 SHUTDOWN")

# ========================================
# AIOHTTP APP (БЕЗ access_log)
# ========================================
def create_app():
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/", healthcheck)
    app.router.add_get("/test", test_endpoint)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

# ========================================
# ЗАПУСК
# ========================================
if __name__ == '__main__':
    logger.info("🎬 CAFEBOTIFY v3.0")
    app = create_app()
    
    # ✅ УБРАЛИ access_log_format - ИСПРАВЛЕНА ОСНОВНАЯ ОШИБКА
    web.run_app(app, host=HOST, port=PORT)
