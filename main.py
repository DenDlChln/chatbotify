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
# НАСТРОЙКИ ЛОГИРОВАНИЯ (DEBUG для отладки)
# ========================================
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ========================================
# ENV ПЕРЕМЕННЫЕ (Render.com)
# ========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "cafesecret123")

# Render.com обязательные настройки
PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ========================================
# МЕНЮ КАФЕ
# ========================================
MENU = {
    "☕ Капучино": 250,
    "🥛 Латте": 270,
    "🍵 Чай": 180
}

# ========================================
# СОСТОЯНИЯ ЗАКАЗА (FSM)
# ========================================
class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
# КЛАВИАТУРЫ
# ========================================
def get_menu_keyboard():
    """Меню напитков"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add("☕ Капучино")
    keyboard.add("🥛 Латте") 
    keyboard.add("🍵 Чай")
    keyboard.add("📞 Позвонить")
    return keyboard

def get_quantity_keyboard():
    """Клавиатура количества"""
    keyboard = types.ReplyKeyboardMarkup(
        resize_keyboard=True, 
        one_time_keyboard=True, 
        row_width=3
    )
    keyboard.add("1", "2", "3")
    keyboard.add("4", "5", "🔙 Отмена")
    return keyboard

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add("☕ Меню", "📞 Позвонить")
    return keyboard

# ========================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ (УПРОЩЕННЫЕ ДЛЯ ТЕСТА)
# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    """Стартовое сообщение"""
    logger.info(f"👤 /start от user_id={message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY LIVE!</b>\n\n"
        "👋 Добро пожаловать!\n"
        "Выберите напиток:",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda message: message.text in MENU.keys())
async def drink_selected(message: types.Message, state: FSMContext):
    """Выбор напитка"""
    logger.info(f"🥤 Выбрали напиток: {message.text}")
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
    """Обработка количества"""
    logger.info(f"📊 Количество: {message.text}")
    
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Заказ отменен", reply_markup=get_menu_keyboard())
        return
    
    try:
        quantity = int(message.text)
        if quantity <= 0 or quantity > 10:
            await message.answer("❌ Введите от 1 до 10")
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
            f"🎉 <b>Заказ принят!</b>\n\n"
            f"🥤 {drink}\n"
            f"📊 {quantity} шт\n"
            f"💰 {total}₽\n\n"
            f"📞 {CAFE_PHONE}",
            reply_markup=get_main_keyboard()
        )
        logger.info(f"✅ Заказ {total}₽ обработан")
        
    except ValueError:
        await message.answer("❌ Введите число (1-10)")

@dp.message_handler(text="☕ Меню")
async def show_menu(message: types.Message):
    """Показать меню"""
    menu_text = "🍽️ <b>Меню:</b>\n\n"
    for drink, price in MENU.items():
        menu_text += f"{drink} — <b>{price}₽</b>\n"
    await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler(text="📞 Позвонить")
async def call_phone(message: types.Message):
    """Телефон кафе"""
    await message.answer(f"📞 Звоните: <b>{CAFE_PHONE}</b>", reply_markup=get_menu_keyboard())

@dp.message_handler()
async def echo_all(message: types.Message):
    """Эхо для отладки"""
    logger.info(f"📨 Получено: '{message.text}' от {message.from_user.id}")
    await message.answer(f"👤 Получено: {message.text}\nНапишите /start")

# ========================================
# АДМИН УВЕДОМЛЕНИЯ
# ========================================
async def send_order_to_admin(order_data):
    """Уведомление админу"""
    text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ</b>\n\n"
        f"👤 {order_data['first_name']}\n"
        f"🆔 <code>{order_data['user_id']}</code>\n"
        f"📱 @{order_data['username']}\n\n"
        f"🥤 {order_data['drink']}\n"
        f"📊 {order_data['quantity']} шт\n"
        f"💰 <b>{order_data['total']}₽</b>\n"
        f"📞 {order_data['phone']}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info(f"✅ Заказ админу отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка админ уведомления: {e}")

# ========================================
# WEBHOOK СЕРВЕР (ПОЛНАЯ ОТЛАДКА)
# ========================================
async def webhook_handler(request):
    """🚨 ГЛАВНЫЙ WEBHOOK С ОТЛАДКОЙ"""
    logger.info(f"🔥 === WEBHOOK ПОЛУЧЕН ===")
    logger.info(f"📡 Method: {request.method}")
    logger.info(f"📍 Path: {request.path}")
    logger.info(f"📊 Headers: {dict(request.headers)}")
    
    try:
        # Читаем тело запроса
        body = await request.read()
        logger.info(f"📄 Body size: {len(body)} bytes")
        
        if len(body) == 0:
            logger.warning("⚠️ Пустое тело запроса")
            return web.Response(text="Empty body", status=200)
        
        # Парсим JSON
        update = await request.json(loads=body)
        logger.info(f"📨 Update ID: {update.get('update_id', 'NO_ID')}")
        
        if 'message' in update:
            msg = update['message']
            logger.info(f"💬 Сообщение: '{msg.get('text', 'NO_TEXT')}' от {msg['from']['id']}")
        
        # Обрабатываем через aiogram
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ === WEBHOOK УСПЕШНО ОБРАБОТАН ===")
        return web.json_response({"status": "ok", "update_id": update.get('update_id')}, status=200)
        
    except Exception as e:
        logger.error(f"💥 WEBHOOK ОШИБКА: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

async def healthcheck(request):
    """Healthcheck для Render"""
    logger.info("🏥 Healthcheck GET /")
    return web.Response(text="CafeBotify LIVE ✅", status=200)

async def test_endpoint(request):
    """Тестовый endpoint"""
    logger.info("🧪 GET /test")
    return web.Response(text="TEST OK - Webhook работает!", status=200)

# ========================================
# STARTUP/SHUTDOWN
# ========================================
async def on_startup(app):
    """🚀 ЗАПУСК СЕРВЕРА"""
    logger.info("🚀 === STARTUP CAFEBOTIFY ===")
    logger.info(f"🤖 BOT_TOKEN: {'OK' if BOT_TOKEN else 'MISSING'}")
    logger.info(f"👑 ADMIN_ID: {ADMIN_ID}")
    logger.info(f"📱 PHONE: {CAFE_PHONE}")
    logger.info(f"🌐 WEBHOOK: {WEBHOOK_URL}")
    
    # Проверяем текущий webhook
    try:
        current = await bot.get_webhook_info()
        logger.info(f"📡 Текущий webhook: {current.url}")
    except:
        logger.info("📡 Нет текущего webhook")
    
    # Очищаем webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🧹 Старые webhooks удалены")
    
    # Устанавливаем НАШ webhook
    await bot.set_webhook(
        WEBHOOK_URL,
        certificate=None,
        max_connections=40,
        allowed_updates=['message']
    )
    
    # ПРОВЕРЯЕМ установку
    new_webhook = await bot.get_webhook_info()
    logger.info(f"✅ Новый webhook: {new_webhook.url}")
    
    if new_webhook.url == WEBHOOK_URL:
        logger.info("🎉 WEBHOOK УСПЕШНО УСТАНОВЛЕН!")
    else:
        logger.error(f"❌ WEBHOOK НЕ УСТАНОВЛЕН! {new_webhook.url}")
    
    # Тестовое сообщение админу
    try:
        await bot.send_message(
            ADMIN_ID,
            "🔥 <b>CAFEBOTIFY LIVE!</b>\n\n"
            f"🌐 {WEBHOOK_URL}\n"
            f"📱 {CAFE_PHONE}\n\n"
            f"✅ Напишите /start для теста!"
        )
        logger.info("✅ Тестовое сообщение админу отправлено")
    except Exception as e:
        logger.error(f"⚠️ Ошибка тестового сообщения: {e}")

async def on_shutdown(app):
    """🛑 ОСТАНОВКА"""
    logger.info("🛑 === SHUTDOWN ===")
    await bot.delete_webhook()
    await dp.storage.close()
    await bot.session.close()
    logger.info("✅ Сервер остановлен")

# ========================================
# СОЗДАНИЕ AIOHTTP ПРИЛОЖЕНИЯ
# ========================================
def create_app():
    """Создание веб-приложения"""
    app = web.Application()
    
    # Роуты
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/", healthcheck)
    app.router.add_get("/test", test_endpoint)
    
    # Startup/Shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    logger.info("✅ Aiohttp приложение создано")
    return app

# ========================================
# ГЛАВНАЯ ФУНКЦИЯ ЗАПУСКА
# ========================================
if __name__ == '__main__':
    logger.info("🎬 === ЗАПУСК CAFEBOTIFY v2.0 ===")
    logger.info(f"🌐 Host: {HOST}, Port: {PORT}")
    
    # Создаем и запускаем приложение
    app = create_app()
    web.run_app(
        app,
        host=HOST,
        port=PORT,
        access_log=True,
        access_log_format='%t "%r" %s %b "%{User-Agent}i"'
    )
