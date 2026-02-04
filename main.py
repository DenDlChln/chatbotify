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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")
PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"  # ✅ ПРОСТОЙ ПУТЬ!

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
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("☕ Капучино")
    kb.add("🥛 Латте")
    kb.add("🍵 Чай")
    kb.add("📞 Позвонить")
    return kb

def get_quantity_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    kb.add("1", "2", "3")
    kb.add("4", "5", "🔙 Отмена")
    return kb

# ========================================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    logger.info(f"👤 /start от {message.from_user.id}")
    await message.answer(
        "🎉 <b>CAFEBOTIFY v6.4 LIVE!</b>\n\n"
        "👋 Выберите напиток:",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda m: m.text in MENU)
async def drink_selected(message: types.Message, state: FSMContext):
    await state.finish()
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
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Отменено", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text)
        if 1 <= qty <= 10:
            data = await state.get_data()
            total = data['price'] * qty
            await state.finish()
            
            await send_order_to_admin({
                'user_id': message.from_user.id,
                'first_name': message.from_user.first_name or "",
                'drink': data['drink'],
                'quantity': qty,
                'total': total
            })
            
            await message.answer(
                f"✅ <b>ЗАКАЗ #{message.from_user.id}</b>\n\n"
                f"🥤 {data['drink']}\n📊 {qty} шт\n💰 <b>{total}₽</b>\n"
                f"📞 {CAFE_PHONE}",
                reply_markup=get_menu_keyboard()
            )
            logger.info(f"✅ Заказ {total}₽")
            return
    except:
        pass
    
    await message.answer("❌ 1-10 или Отмена", reply_markup=get_quantity_keyboard())

@dp.message_handler()
async def echo(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("👋 /start", reply_markup=get_menu_keyboard())

# ========================================
async def send_order_to_admin(data):
    text = (
        f"🔔 <b>ЗАКАЗ #{data['user_id']}</b>\n\n"
        f"👤 {data['first_name']}\n"
        f"🥤 <b>{data['drink']}</b>\n📊 <b>{data['quantity']}x</b>\n"
        f"💰 <b>{data['total']}₽</b>"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except:
        pass

# ========================================
# ✅ v6.4 ФИНАЛЬНЫЙ WEBHOOK
async def webhook_handler(request):
    logger.info(f"🔥 WEBHOOK ПОЛУЧЕН: {request.path}")
    
    try:
        update = await request.json()
        update_id = update.get('update_id')
        logger.info(f"📨 Update #{update_id}")
        
        Bot.set_current(bot)
        Dispatcher.set_current(dp)
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ OK")
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"💥 {e}")
        return web.Response(text="OK", status=200)  # ✅ ВСЕГДА 200 Telegram!

async def healthcheck(request):
    return web.Response(text="CafeBotify v6.4 LIVE ✅", status=200)

# ========================================
async def on_startup(app):
    logger.info("🚀 v6.4 STARTUP")
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    await bot.set_webhook(WEBHOOK_URL)
    
    info = await bot.get_webhook_info()
    logger.info(f"✅ WEBHOOK: {info.url}")
    
    await bot.send_message(ADMIN_ID, f"🔥 v6.4 LIVE!\n{WEBHOOK_URL}\n/start")

async def on_shutdown(app):
    await bot.delete_webhook()
    await dp.storage.close()

# ========================================
def create_app():
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)  # ✅ ПРОСТОЙ ПУТЬ /webhook
    app.router.add_get("/", healthcheck)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == '__main__':
    logger.info("🎬 v6.4 - PATH FIXED!")
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)
