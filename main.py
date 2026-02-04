import os
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.webhook import get_new_configured_app
from aiohttp import web
from datetime import datetime

# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
def load_config():
    """Загрузка конфигурации кофейни"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            config = data.get('cafe', {})
            return {
                'name': config.get('name', 'Кофейня «Уют» ☕'),
                'phone': config.get('phone', '+7 989 273-67-56'),
                'admin_chat_id': config.get('admin_chat_id', 1471275603),
                'work_hours': config.get('work_hours', [9, 21]),
                'menu': config.get('menu', {
                    "☕ Капучино": 250,
                    "🥛 Латте": 270,
                    "🍵 Чай": 180,
                    "⚡ Эспрессо": 200
                })
            }
    except:
        return {
            "name": "Кофейня «Уют» ☕",
            "phone": "+7 989 273-67-56",
            "admin_chat_id": 1471275603,
            "work_hours": [9, 21],
            "menu": {
                "☕ Капучино": 250,
                "🥛 Латте": 270,
                "🍵 Чай": 180,
                "⚡ Эспрессо": 200
            }
        }

# Глобальная конфигурация
cafe_config = load_config()
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = dict(cafe_config["menu"])
WORK_START = int(cafe_config["work_hours"][0])
WORK_END = int(cafe_config["work_hours"][1])

# Render переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_HOST = os.getenv('WEBAPP_HOST', 'chatbotify-2tjd.onrender.com')
WEBAPP_PORT = int(os.getenv('PORT', 10000))
WEBHOOK_PATH = f'/{BOT_TOKEN}'  # ← ТОЧНО как Telegram шлёт!
WEBHOOK_URL = f'https://{WEBAPP_HOST}{WEBHOOK_PATH}'

logger.info(f"🎯 WEBHOOK_PATH: {WEBHOOK_PATH}")
logger.info(f"🎯 WEBHOOK_URL:  {WEBHOOK_URL}")

# ========================================
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_confirmation = State()

# ========================================
def is_cafe_open():
    """Проверка графика работы"""
    now = datetime.now().hour
    return WORK_START <= now < WORK_END

def get_work_status():
    """Текущее состояние кофейни"""
    now = datetime.now()
    current_hour = now.hour
    if is_cafe_open():
        time_left = WORK_END - current_hour
        return f"🟢 <b>Открыто</b> (ещё {time_left} ч.)"
    else:
        next_open = f"{WORK_START}:00"
        return f"🔴 <b>Закрыто</b>\n🕐 Открываемся: {next_open}"

def get_closed_notification():
    """Уведомление о закрытии"""
    return (
        f"🔒 <b>{CAFE_NAME} закрыто!</b>\n\n"
        f"{get_work_status()}\n\n"
        f"📞 <b>Позвонить:</b>\n"
        f"<code>{CAFE_PHONE}</code>\n\n"
        f"☕ <i>Ждём вас в рабочее время!</i>"
    )

def get_menu_keyboard():
    """Главное меню"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for drink in MENU.keys():
        kb.add(drink)
    kb.row("📞 Позвонить", "⏰ Часы работы")
    return kb

def get_quantity_keyboard():
    """Клавиатура количества"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    kb.add("1️⃣", "2️⃣", "3️⃣")
    kb.add("4️⃣", "5️⃣", "🔙 Отмена")
    return kb

def get_confirm_keyboard():
    """Подтверждение заказа"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    kb.add("✅ Подтвердить", "🔙 Меню")
    return kb

# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message, state: FSMContext):
    """Стартовая команда"""
    await state.finish()
    logger.info(f"👤 /start от {message.from_user.id}")
    await message.answer(
        f"<b>{CAFE_NAME}</b>\n\n"
        f"🏪 {get_work_status()}\n\n"
        f"☕ <b>Выберите напиток:</b>",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda m: m.text in MENU)
async def drink_selected(message: types.Message, state: FSMContext):
    """Выбор напитка"""
    logger.info(f"🥤 {message.text} от {message.from_user.id}")
    
    if not is_cafe_open():
        await message.answer(
            get_closed_notification(),
            reply_markup=get_menu_keyboard()
        )
        return
        
    drink = message.text
    price = MENU[drink]
    await OrderStates.waiting_for_quantity.set()
    await state.update_data(drink=drink, price=price)
    
    await message.answer(
        f"🥤 <b>{drink}</b>\n"
        f"💰 <b>{price} ₽</b>\n\n"
        f"📝 <b>Сколько порций?</b>",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    """Обработка количества"""
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
            logger.info(f"📋 Подтверждение от {message.from_user.id}")
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
    """Подтверждение заказа"""
    logger.info(f"✅ {message.text} от {message.from_user.id}")
    
    data = await state.get_data()
    
    if "Подтвердить" in message.text:
        order_data = {
            'user_id': message.from_user.id,
            'first_name': message.from_user.first_name or "Гость",
            'drink': data['drink'],
            'quantity': data['quantity'],
            'total': data['total']
        }
        
        await message.answer(
            f"🎉 <b>ЗАКАЗ #{message.from_user.id} ПРИНЯТ!</b> ☕✨\n\n"
            f"🥤 <b>{data['drink']}</b>\n"
            f"📊 {data['quantity']} порций\n"
            f"💰 <b>{data['total']} ₽</b>\n\n"
            f"📞 <code>{CAFE_PHONE}</code>\n"
            f"✅ <i>Готовим! ⏳</i>",
            reply_markup=get_menu_keyboard()
        )
        
        await send_order_to_admin(order_data)
        await state.finish()
        return
    
    await state.finish()
    await message.answer("🔙 В меню ☕", reply_markup=get_menu_keyboard())

async def send_order_to_admin(order_data):
    """Уведомление админу"""
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b> ☕\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']} ₽</b>"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info(f"✅ Заказ #{order_data['user_id']} админу")
    except Exception as e:
        logger.error(f"❌ Админ: {e}")

@dp.message_handler(lambda m: m.text == "📞 Позвонить")
async def call_phone(message: types.Message):
    """Номер телефона"""
    await message.answer(
        f"📞 <b>Позвонить:</b>\n<code>{CAFE_PHONE}</code>\n\n{get_work_status()}",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda m: m.text == "⏰ Часы работы")
async def work_hours(message: types.Message):
    """График работы"""
    await message.answer(
        f"⏰ <b>{WORK_START}:00 - {WORK_END}:00</b>\n\n{get_work_status()}\n\n📞 <code>{CAFE_PHONE}</code>",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler()
async def echo(message: types.Message, state: FSMContext):
    """Обработчик неизвестных команд"""
    await state.finish()
    logger.info(f"❓ Неизвестное: {message.text} от {message.from_user.id}")
    await message.answer(
        f"❓ <b>{CAFE_NAME}</b>\n\n"
        f"{get_work_status()}\n\n"
        f"☕ <b>Выберите:</b>",
        reply_markup=get_menu_keyboard()
    )

# ========================================
async def on_startup(_):
    """Инициализация webhook"""
    try:
        # Очистка старого webhook
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🧹 Старый webhook удалён")
        await asyncio.sleep(1)
        
        # Установка нового
        await bot.set_webhook(WEBHOOK_URL)
        info = await bot.get_webhook_info()
        
        logger.info(f"✅ WEBHOOK: {info.url}")
        logger.info(f"📊 Pending updates: {info.pending_update_count}")
        logger.info(f"🚀 v8.25 LIVE — {CAFE_NAME}")
        
        if info.url != WEBHOOK_URL:
            logger.error(f"❌ Webhook НЕ совпадает!")
            
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")

async def on_shutdown(_):
    """Очистка при остановке"""
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logger.info("🛑 v8.25 STOP")

# ========================================
async def healthcheck(request):
    """Healthcheck для Render"""
    logger.info("🏥 Healthcheck OK")
    return web.Response(text="CafeBotify v8.25 LIVE ✅", status=200)

async def main():
    """Главная функция"""
    logger.info(f"🎬 v8.25 CAFEBOTIFY — {CAFE_NAME}")
    logger.info(f"🌐 HOST: {WEBAPP_HOST}:{WEBAPP_PORT}")
    logger.info(f"🎯 PATH: {WEBHOOK_PATH}")
    
    # Создание AIOHTTP приложения
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # ✅ Регистрация webhook endpoint
    app.router.add_post(WEBHOOK_PATH, get_new_configured_app(dispatcher=dp, path=WEBHOOK_PATH))
    
    # ✅ Healthcheck для Render
    app.router.add_get('/', healthcheck)
    
    # Запуск сервера
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBAPP_PORT)
    await site.start()
    
    logger.info(f"🌐 Server запущен: 0.0.0.0:{WEBAPP_PORT}")
    logger.info(f"✅ Готов к POST {WEBHOOK_PATH}")
    
    # Держим сервер живым
    await asyncio.Event().wait()

# ========================================
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
