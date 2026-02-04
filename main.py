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
# ЛОГИРОВАНИЕ
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

# Глобальные объекты
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
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True, 
        one_time_keyboard=True, 
        row_width=3
    )
    keyboard.add("1", "2", "3")
    keyboard.add("4", "5", "🔙 Отмена")
    return keyboard

def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add("☕ Меню", "📞 Позвонить")
    return keyboard

# ========================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    logger.info(f"👤 /start от {message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY LIVE!</b>\n\n"
        "👋 Добро пожаловать в кафе!\n"
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
        f"✅ Вы выбрали <b>{drink}</b>\n"
        f"💰 <b>{price}₽</b> за порцию\n\n"
        f"📝 Сколько порций заказать?",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logger.info(f"📊 Количество: {message.text}")
    
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Заказ отменен", reply_markup=get_menu_keyboard())
        return
    
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 10:
            await message.answer("❌ Введите число от 1 до 10")
            return
        
        data = await state.get_data()
        drink = data['drink']
        price = data['price']
        total = price * quantity
        
        order_data = {
            'user_id': message.from_user.id,
            'first_name': message.from_user.first_name or "Не указано",
            'username': message.from_user.username or "Не указан",
            'drink': drink,
            'quantity': quantity,
            'total': total,
            'phone': CAFE_PHONE
        }
        
        await state.finish()
        await send_order_to_admin(order_data)
        
        await message.answer(
            f"🎉 <b>Заказ принят!</b>\n\n"
            f"🥤 <b>{drink}</b>\n"
            f"📊 <b>{quantity}</b> порций\n"
            f"💰 <b>{total}₽</b>\n\n"
            f"📞 Позвоним: <b>{CAFE_PHONE}</b>",
            reply_markup=get_main_keyboard()
        )
        logger.info(f"✅ Заказ {total}₽")
        
    except ValueError:
        await message.answer("❌ Введите число от 1 до 10")

@dp.message_handler(text="☕ Меню")
async def show_menu(message: types.Message):
    menu_text = "🍽️ <b>Меню кафе:</b>\n\n"
    for drink, price in MENU.items():
        menu_text += f"{drink} — <b>{price}₽</b>\n"
    await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler(text="📞 Позвонить")
async def call_phone(message: types.Message):
    await message.answer(
        f"📞 Телефон кафе: <b>{CAFE_PHONE}</b>\n\n"
        "Или сделайте заказ через меню ☕",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await message.answer(
        "❓ Выберите команду из меню или /start",
        reply_markup=get_menu_keyboard()
    )

# ========================================
# АДМИН УВЕДОМЛЕНИЯ
# ========================================
async def send_order_to_admin(order_data):
    message_text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n"
        f"📱 @{order_data['username']}\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']}₽</b>\n\n"
        f"📞 {order_data['phone']}"
    )
    try:
        await bot.send_message(ADMIN_ID, message_text)
        logger.info(f"✅ Заказ админу отправлен")
    except Exception as e:
        logger.error(f"❌ Админ ошибка: {e}")

# ========================================
# WEBHOOK ОБРАБОТЧИК
# ========================================
async def webhook_handler(request):
    try:
        logger.info("🔥 WEBHOOK ПОЛУЧЕН")
        
        update = await request.json()
        update_id = update.get('update_id', 'unknown')
        logger.info(f"📨 Update ID: {update_id}")
        
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ WEBHOOK ОБРАБОТАН")
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"💥 WEBHOOK ОШИБКА: {e}")
        return web.Response(text="ERROR", status=500)

async def healthcheck(request):
    return web.Response(text="CafeBotify LIVE ✅", status=200)

# ========================================
# STARTUP/SHUTDOWN (ИСПРАВЛЕН)
# ========================================
async def on_startup(app):
    logger.info("🚀 ЗАПУСК BOT")
    logger.info(f"👑 ADMIN: {ADMIN_ID}")
    logger.info(f"📱 PHONE: {CAFE_PHONE}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🧹 Webhook очищен")
    
    await bot.set_webhook(WEBHOOK_URL)
    webhook_info = await bot.get_webhook_info()
    logger.info(f"✅ WEBHOOK: {webhook_info.url}")
    
    try:
        await bot.send_message(
            ADMIN_ID,
            "🎉 <b>CafeBotify LIVE!</b>\n\n"
            f"🌐 {WEBHOOK_URL}\n"
            "✅ Напишите /start для теста!"
        )
        logger.info("✅ Тестовое сообщение отправлено")
    except Exception as e:
        logger.error(f"⚠️ Тестовое сообщение: {e}")

async def on_shutdown(app):
    logger.info("🛑 ОСТАНОВКА")
    await bot.delete_webhook()
    # ✅ ИСПРАВЛЕНО: убираем session.close()
    await dp.storage.close()

# ========================================
# AIOHTTP ПРИЛОЖЕНИЕ
# ========================================
def create_app():
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/", healthcheck)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

# ========================================
# ЗАПУСК
# ========================================
if __name__ == '__main__':
    logger.info("🎬 CAFEBOTIFY v5.1 ✅")
    logger.info(f"🌐 {HOST}:{PORT}")
    
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)
