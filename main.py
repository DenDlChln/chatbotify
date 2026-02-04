import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import aiohttp
from aiohttp import web
import contextvars  # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ

# ========================================
# ЛОГИРОВАНИЕ
# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# ENV
# ========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")

PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

# ✅ ГЛОБАЛЬНЫЙ BOT CONTEXT
bot_ctx = contextvars.ContextVar('bot', default=None)

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
# ОБРАБОТЧИКИ (работают!)
# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    logger.info(f"✅ /start от {message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY LIVE!</b>\n\n"
        "👋 Выберите напиток:",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda message: message.text in MENU.keys())
async def drink_selected(message: types.Message, state: FSMContext):
    logger.info(f"🥤 {message.text}")
    drink = message.text
    price = MENU[drink]
    
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    
    await message.answer(
        f"✅ <b>{drink}</b>\n💰 <b>{price}₽</b>\n\n"
        "📝 Сколько порций?",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logger.info(f"📊 {message.text}")
    
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Отменено", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text)
        if qty < 1 or qty > 10:
            await message.answer("❌ 1-10")
            return
        
        data = await state.get_data()
        total = data['price'] * qty
        
        order_data = {
            'user_id': message.from_user.id,
            'first_name': message.from_user.first_name or "",
            'username': message.from_user.username or "",
            'drink': data['drink'],
            'quantity': qty,
            'total': total,
            'phone': CAFE_PHONE
        }
        
        await state.finish()
        await send_order_to_admin(order_data)
        
        await message.answer(
            f"✅ <b>ЗАКАЗ #{message.from_user.id}</b>\n\n"
            f"🥤 {data['drink']}\n"
            f"📊 {qty} шт\n"
            f"💰 <b>{total}₽</b>\n\n"
            f"📞 {CAFE_PHONE}",
            reply_markup=get_main_keyboard()
        )
        
    except:
        await message.answer("❌ Число 1-10")

@dp.message_handler(text=["☕ Меню", "📞 Позвонить"])
async def menu_phone(message: types.Message):
    if "📞" in message.text:
        await message.answer(f"📞 <b>{CAFE_PHONE}</b>", reply_markup=get_menu_keyboard())
    else:
        text = "🍽️ <b>Меню:</b>\n\n"
        for d, p in MENU.items():
            text += f"{d} — <b>{p}₽</b>\n"
        await message.answer(text, reply_markup=get_menu_keyboard())

@dp.message_handler()
async def echo(message: types.Message):
    await message.answer("👋 /start", reply_markup=get_menu_keyboard())

# ========================================
# АДМИН
# ========================================
async def send_order_to_admin(data):
    text = (
        f"🔔 <b>ЗАКАЗ #{data['user_id']}</b>\n\n"
        f"👤 {data['first_name']} (@{data['username']})\n\n"
        f"🥤 <b>{data['drink']}</b>\n"
        f"📊 <b>{data['quantity']}x</b>\n"
        f"💰 <b>{data['total']}₽</b>\n"
        f"📞 {data['phone']}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except:
        pass

# ========================================
# ✅ ИСПРАВЛЕННЫЙ WEBHOOK
# ========================================
async def webhook_handler(request):
    """🎯 WEBHOOK С BOT CONTEXT"""
    try:
        logger.info("🔥 WEBHOOK HIT")
        
        # ✅ УСТАНАВЛИВАЕМ BOT CONTEXT
        bot_ctx.set(bot)
        
        update = await request.json()
        logger.info(f"📨 #{update.get('update_id')}")
        
        # ✅ Aiogram обработка
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ WEBHOOK OK")
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"💥 {e}")
        return web.Response(text="ERROR", status=500)

async
