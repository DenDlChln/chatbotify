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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# КОНФИГУРАЦИЯ
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")

PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

# ========================================
# BOT И DISPATCHER
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ========================================
# МЕНЮ И СОСТОЯНИЯ
MENU = {
    "☕ Капучино": 250,
    "🥛 Латте": 270,
    "🍵 Чай": 180
}

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
# КЛАВИАТУРЫ
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("☕ Капучино")
    kb.add("🥛 Латте")
    kb.add("🍵 Чай")
    kb.add("📞 Позвонить")
    return kb

def get_quantity_keyboard():
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True,
        row_width=3
    )
    kb.add("1", "2", "3")
    kb.add("4", "5", "🔙 Отмена")
    return kb

def get_main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("☕ Меню", "📞 Позвонить")
    return kb

# ========================================
# ОБРАБОТЧИКИ КОМАНД
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    logger.info(f"👤 /start от {message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY LIVE v6.1!</b>\n\n"
        "👋 Добро пожаловать в кафе!\n"
        "Выберите напиток:",
        reply_markup=get_menu_keyboard()
    )

# ========================================
# ВЫБОР НАПИТКА
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

# ========================================
# ОБРАБОТКА КОЛИЧЕСТВА (КРИТИЧЕСКАЯ ЛОГИКА)
@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logger.info(f"📊 Количество: {message.text}")
    
    # Отмена заказа
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Заказ отменен", reply_markup=get_menu_keyboard())
        return
    
    # Проверка количества
    try:
        qty = int(message.text)
        if 1 <= qty <= 10:
            # ✅ УСПЕШНЫЙ ЗАКАЗ
            data = await state.get_data()
            total = data['price'] * qty
            
            order_data = {
                'user_id': message.from_user.id,
                'first_name': message.from_user.first_name or "Не указано",
                'username': message.from_user.username or "Не указан",
                'drink': data['drink'],
                'quantity': qty,
                'total': total,
                'phone': CAFE_PHONE
            }
            
            await state.finish()
            await send_order_to_admin(order_data)
            
            await message.answer(
                f"🎉 <b>Заказ принят #{message.from_user.id}</b>\n\n"
                f"🥤 <b>{data['drink']}</b>\n"
                f"📊 <b>{qty}</b> порций\n"
                f"💰 <b>{total}₽</b>\n\n"
                f"📞 Наш номер: <b>{CAFE_PHONE}</b>",
                reply_markup=get_main_keyboard()
            )
            logger.info(f"✅ Заказ {total}₽ от {message.from_user.id}")
            return
    except ValueError:
        pass
    
    # ❌ НЕВЕРНОЕ КОЛИЧЕСТВО
    await message.answer(
        "❌ Введите число от 1 до 10\n"
        "или <b>🔙 Отмена</b>",
        reply_markup=get_quantity_keyboard()
    )

# ========================================
# МЕНЮ И ТЕЛЕФОН
@dp.message_handler(text=["☕ Меню", "📞 Позвонить"])
async def menu_phone(message: types.Message):
    if message.text == "📞 Позвонить":
        await message.answer(
            f"📞 <b>Телефон кафе:</b>\n<code>{CAFE_PHONE}</code>",
            reply_markup=get_menu_keyboard()
        )
    else:  # ☕ Меню
        text = "🍽️ <b>Наше меню:</b>\n\n"
        for drink, price in MENU.items():
            text += f"{drink} — <b>{price}₽</b>\n"
        await message.answer(text, reply_markup=get_menu_keyboard())

# ========================================
# ОСТАЛЬНЫЕ СООБЩЕНИЯ
@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await message.answer(
        "❓ Не понял команду.\n"
        "👉 Нажмите /start или выберите из меню",
        reply_markup=get_menu_keyboard()
    )

# ========================================
# АДМИН УВЕДОМЛЕНИЯ
async def send_order_to_admin(order_data):
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n"
        f"📱 <a href='tg://user?id={order_data['user_id']}'>Написать</a>\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']}₽</b>\n\n"
        f"📞 {order_data['phone']}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info("✅ Админ уведомлен")
    except Exception as e:
        logger.error(f"❌ Админ ошибка: {e}")

# ========================================
# WEBHOOK ОБРАБОТЧИК (v6.1 ОПТИМИЗИРОВАН)
async def webhook_handler(request):
    try:
        logger.info("🔥 WEBHOOK ПОЛУЧЕН")
        
        update = await request.json()
        update_id = update.get('update_id', 'unknown')
        logger.info(f"📨 Update #{update_id}")
        
        # ✅ КРИТИЧЕСКИЙ CONTEXT FIX
        Bot.set_current(bot)
        Dispatcher.set_current(dp)
        
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ WEBHOOK OK")
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"💥 WEBHOOK: {e}")
        return web.Response(text="ERROR", status=500)

async def healthcheck(request):
    return web.Response(text="CafeBotify v6.1 LIVE ✅", status=200)

# ========================================
# STARTUP/SHUTDOWN
async def on_startup(app):
    logger.info("🚀 ЗАПУСК CAFEBOTIFY v6.1")
    logger.info(f"👑 АДМИН: {ADMIN_ID}")
    logger.info(f"📱 ТЕЛЕФОН: {CAFE_PHONE}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🧹 Старые webhook удалены")
    
    await bot.set_webhook(WEBHOOK_URL)
    info = await bot.get_webhook_info()
    logger.info(f"✅ WEBHOOK: {info.url}")
    
    await bot.send_message(
        ADMIN_ID,
        "🎉 <b>CaféBotify v6.1 LIVE!</b>\n\n"
        f"🌐 {WEBHOOK_URL}\n"
        "✅ Тестируйте: /start → ☕ → 2"
    )

async def on_shutdown(app):
    logger.info("🛑 ОСТАНОВКА")
    await bot.delete_webhook()
    await dp.storage.close()

# ========================================
# AIOHTTP APP
def create_app():
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/", healthcheck)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

# ========================================
# ЗАПУСК
if __name__ == '__main__':
    logger.info("🎬 CAFEBOTIFY v6.1 - ПОЛНЫЙ РАБОЧИЙ")
    logger.info(f"🌐 HOST: {HOST}:{PORT}")
    
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)
