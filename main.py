import os
import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime, time
import aiohttp
from aiohttp import web

# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# ✅ ЧИТАЕМ config.json (ваш формат)
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data['cafe']
    except:
        logger.warning("⚠️ config.json не найден, дефолт")
        return {
            "name": "Кофейня ☕",
            "phone": "+7 989 273-67-56", 
            "admin_chat_id": 1471275603,
            "work_hours": [9, 21],
            "menu": {"☕ Капучино": 250}
        }

cafe_config = load_config()
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = dict(cafe_config["menu"])
WORK_START_HOUR = int(cafe_config["work_hours"][0])
WORK_END_HOUR = int(cafe_config["work_hours"][1])

WORK_START = time(WORK_START_HOUR, 0)
WORK_END = time(WORK_END_HOUR, 0)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

# ========================================
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for drink in list(MENU.keys())[:6]:
        kb.add(drink)
    kb.row("📞 Позвонить", "⏰ Часы работы")
    return kb

def get_quantity_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=3)
    kb.add("1️⃣", "2️⃣", "3️⃣")
    kb.add("4️⃣", "5️⃣", "🔙 Отмена")
    return kb

def get_main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("☕ Меню", "📞 Позвонить")
    kb.row("⏰ Часы работы", "ℹ️ О боте")
    return kb

# ========================================
def is_cafe_open():
    now = datetime.now().time()
    return WORK_START <= now <= WORK_END

def get_work_status():
    if is_cafe_open():
        return f"🟢 <b>Открыто</b> (до {WORK_END_HOUR}:00)"
    return f"🔴 <b>Закрыто</b>\n🕐 {WORK_START_HOUR}:00-{WORK_END_HOUR}:00"

# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        f"{CAFE_NAME}\n\n🏪 {get_work_status()}\n\n"
        "<b>☕ Выберите напиток ниже 😊</b>",
        reply_markup=get_menu_keyboard()
    )

@dp.message_handler(lambda m: m.text in MENU)
async def drink_selected(message: types.Message, state: FSMContext):
    if not is_cafe_open():
        await message.answer(
            f"🔴 <b>{CAFE_NAME} закрыто!</b>\n\n📞 {CAFE_PHONE}",
            reply_markup=get_main_keyboard()
        )
        return
    
    drink = message.text
    price = MENU[drink]
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    
    await message.answer(
        f"{drink}\n💰 <b>{price} ₽</b>\n\n📝 <b>Сколько порций?</b>",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Отменено", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text[0])
        if 1 <= qty <= 5:
            data = await state.get_data()
            total = data['price'] * qty
            await state.finish()
            
            await send_order_to_admin({
                'user_id': message.from_user.id,
                'first_name': message.from_user.first_name or "Гость",
                'drink': data['drink'],
                'quantity': qty,
                'total': total
            })
            
            await message.answer(
                f"🎉 <b>Заказ #{message.from_user.id}</b>\n\n"
                f"{data['drink']}\n📊 <b>{qty}x</b>\n💰 <b>{total}₽</b>\n\n"
                f"📞 {CAFE_PHONE}\n✅ Готовим!",
                reply_markup=get_main_keyboard()
            )
            return
    except:
        pass
    
    data = await state.get_data()
    await message.answer(
        f"{data['drink']} — <b>{data['price']}₽</b>\n\n"
        "❌ <b>1️⃣-5️⃣</b> или <b>🔙</b>",
        reply_markup=get_quantity_keyboard()
    )

@dp.message_handler(text=["☕ Меню", "📞 Позвонить", "⏰ Часы работы", "ℹ️ О боте"])
async def menu_actions(message: types.Message, state: FSMContext):
    await state.finish()
    if "📞" in message.text:
        await message.answer(f"📞 <b>{CAFE_NAME}:</b>\n<code>{CAFE_PHONE}</code>", reply_markup=get_menu_keyboard())
    elif "⏰" in message.text:
        await message.answer(f"🕐 <b>{CAFE_NAME}:</b>\n🟢 {WORK_START_HOUR}:00-{WORK_END_HOUR}:00\n\n{get_work_status()}", reply_markup=get_menu_keyboard())
    elif "О боте" in message.text:
        await message.answer(f"🤖 <b>CAFEBOTIFY 2990₽/мес</b>\n🎯 {CAFE_NAME}", reply_markup=get_main_keyboard())
    else:
        menu_text = f"🍽️ <b>{CAFE_NAME}:</b>\n\n" + "\n".join(f"{k} — {v}₽" for k,v in MENU.items())
        await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler()
async def unknown(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(f"❓ {CAFE_NAME}\n\n{get_work_status()}", reply_markup=get_menu_keyboard())

# ========================================
async def send_order_to_admin(order_data):
    text = (
        f"🔔 <b>🚨 ЗАКАЗ #{order_data['user_id']} | {CAFE_NAME}</b>\n\n"
        f"👤 {order_data['first_name']}\n🆔 <code>{order_data['user_id']}</code>\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n📊 <b>{order_data['quantity']}x</b>\n"
        f"💰 <b>{order_data['total']}₽</b>\n📞 {CAFE_PHONE}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except:
        pass

# ========================================
# ✅ РУЧНОЙ AIOHTTP (v6.1 подход + Healthcheck)
async def webhook_handler(request):
    logger.info("🔥 WEBHOOK!")
    try:
        update = await request.json()
        Bot.set_current(bot)
        Dispatcher.set_current(dp)
        await dp.process_update(types.Update(**update))
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"❌ {e}")
        return web.Response(text="OK", status=200)

async def healthcheck(request):
    return web.Response(text="LIVE", status=200)

async def on_startup(_):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ WEBHOOK: {WEBHOOK_URL}")
    logger.info(f"🎬 v8.3 — {CAFE_NAME} | {len(MENU)} позиций")

async def on_shutdown(_):
    await bot.delete_webhook()

# ========================================
app = web.Application()
app.router.add_post("/webhook", webhook_handler)
app.router.add_get("/", healthcheck)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == '__main__':
    logger.info(f"🚀 v8.3 {CAFE_NAME}")
    web.run_app(app, host=HOST, port=PORT)
