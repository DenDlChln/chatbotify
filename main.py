import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import aiohttp
from aiohttp import web
from datetime import datetime, time

# ========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")

PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_URL = "https://chatbotify-2tjd.onrender.com/webhook"

# ✅ ЧАСЫ РАБОТЫ КАФЕ
WORK_START = time(9, 0)   # 9:00
WORK_END = time(21, 0)    # 21:00

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

MENU = {
    "☕ <b>Капучино</b>": 250,
    "🥛 <b>Латте</b>": 270,
    "🍵 <b>Чай</b>": 180,
    "🍫 <b>Горячий шоколад</b>": 220,
    "☕ <b>Американо</b>": 200
}

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
def get_menu_keyboard():
    """🍽️ Цифровое меню — главная фича"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for item in MENU.keys():
        kb.add(item)
    kb.row("📞 Позвонить", "⏰ Часы работы")
    return kb

def get_quantity_keyboard():
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True, 
        one_time_keyboard=True, 
        row_width=3
    )
    kb.add("1️⃣", "2️⃣", "3️⃣")
    kb.add("4️⃣", "5️⃣", "🔙 Отмена")
    return kb

def get_main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("☕ Меню", "📞 Позвонить")
    kb.row("⏰ Часы работы", "ℹ️ Помощь")
    return kb

# ========================================
def is_cafe_open():
    """Проверяем часы работы"""
    now = datetime.now().time()
    return WORK_START <= now <= WORK_END

def get_work_status():
    """Статус работы кафе"""
    now = datetime.now().time()
    if is_cafe_open():
        return "🟢 <b>Открыто</b> (до 21:00)"
    else:
        next_open = WORK_START.strftime("%H:%M") if now > WORK_END else "завтра"
        return f"🔴 <b>Закрыто</b>\nРаботаем с 9:00 до 21:00{next_open}"

# ========================================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    
    status = get_work_status()
    
    welcome_text = (
        "🤖 <b>CAFEBOTIFY</b>\n"
        "🍽️ Бот вместо администратора\n\n"
        f"{status}\n\n"
        "👇 <b>Выберите напиток из меню:</b>"
    )
    
    await message.answer(welcome_text, reply_markup=get_menu_keyboard())
    logger.info(f"👤 /start от {message.from_user.id}")

# ========================================
@dp.message_handler(lambda m: m.text in MENU.keys())
async def drink_selected(message: types.Message, state: FSMContext):
    if not is_cafe_open():
        await message.answer(
            "🔴 Кафе закрыто\n"
            "📞 Позвоните: <code>" + CAFE_PHONE + "</code>",
            reply_markup=get_main_keyboard()
        )
        return
    
    await state.finish()
    drink = message.text
    price = MENU[drink]
    
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    
    await message.answer(
        f"{drink}\n"
        f"💰 <b>{price} ₽</b>\n\n"
        f"📝 <b>Сколько порций?</b>",
        reply_markup=get_quantity_keyboard()
    )

# ========================================
@dp.message_handler(state=OrderStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.finish()
        await message.answer("❌ Заказ отменён", reply_markup=get_menu_keyboard())
        return
    
    try:
        qty = int(message.text[0])  # 1️⃣ → 1
        if 1 <= qty <= 5:
            data = await state.get_data()
            drink = data['drink']
            price = data['price']
            total = price * qty
            
            # ✅ ПОЛНАЯ ОЧИСТКА
            await state.finish()
            
            # ✅ АДМИН УВЕДОМЛЕНИЕ (ПРОДАКТ ФИЧА!)
            await send_order_to_admin({
                'user_id': message.from_user.id,
                'first_name': message.from_user.first_name or "",
                'username': message.from_user.username or "",
                'drink': drink,
                'quantity': qty,
                'total': total
            })
            
            success_text = (
                f"🎉 <b>Заказ принят #{message.from_user.id}</b>\n\n"
                f"{drink}\n"
                f"📊 <b>{qty} порций</b>\n"
                f"💰 <b>{total} ₽</b>\n\n"
                f"📞 {CAFE_PHONE}"
            )
            
            await message.answer(success_text, reply_markup=get_main_keyboard())
            logger.info(f"✅ Заказ {total}₽ от {message.from_user.id}")
            return
    except:
        pass
    
    data = await state.get_data()
    await message.answer(
        f"{data['drink']}\n💰 <b>{data['price']} ₽</b>\n\n"
        "❌ Введите <b>1️⃣-5️⃣</b> или <b>🔙 Отмена</b>",
        reply_markup=get_quantity_keyboard()
    )

# ========================================
@dp.message_handler(text=["☕ Меню", "📞 Позвонить", "⏰ Часы работы", "ℹ️ Помощь"])
async def menu_actions(message: types.Message, state: FSMContext):
    await state.finish()
    
    if "📞" in message.text:
        await message.answer(
            f"📞 <b>Позвонить в кафе:</b>\n"
            f"<code>{CAFE_PHONE}</code>\n\n"
            "Или оформите заказ ☕",
            reply_markup=get_menu_keyboard()
        )
    
    elif "⏰" in message.text:
        await message.answer(
            f"🕐 <b>Часы работы:</b>\n"
            f"🟢 9:00 - 21:00\n\n"
            f"{get_work_status()}\n\n"
            "👇 Оформите заказ:",
            reply_markup=get_menu_keyboard()
        )
    
    elif "ℹ️" in message.text:
        await message.answer(
            "🤖 <b>CAFEBOTIFY — бот вместо администратора</b>\n\n"
            "✅ Цифровое меню в Telegram\n"
            "✅ Приём заказов 24/7\n"
            "✅ Уведомления владельцу\n\n"
            "💰 <b>2 990 ₽/мес</b>\n"
            "🚀 Для малых кафе (1 точка)",
            reply_markup=get_main_keyboard()
        )
    
    else:  # ☕ Меню
        menu_text = "🍽️ <b>Меню кафе:</b>\n\n" + "\n".join(MENU.keys())
        await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler()
async def unknown(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "❓ Выберите из меню или /start\n\n"
        f"{get_work_status()}",
        reply_markup=get_menu_keyboard()
    )

# ========================================
async def send_order_to_admin(order_data):
    """🚨 ПРОДАКТ ФИЧА: Красивое уведомление владельцу"""
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n"
        f"📱 @{order_data['username']}\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']} ₽</b>\n\n"
        f"📞 {CAFE_PHONE}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info("✅ Админ уведомлён")
    except Exception as e:
        logger.error(f"❌ Админ ошибка: {e}")

# ========================================
async def webhook_handler(request):
    logger.info("🔥 WEBHOOK HIT!")
    
    try:
        update = await request.json()
        logger.info(f"📨 Update #{update.get('update_id')}")
        
        Bot.set_current(bot)
        Dispatcher.set_current(dp)
        await dp.process_update(types.Update(**update))
        
        logger.info("✅ OK")
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"💥 {e}")
        return web.Response(text="OK", status=200)

async def healthcheck(request):
    return web.Response(text="CAFEBOTIFY v7.0 LIVE ✅", status=200)

# ========================================
async def on_startup(app):
    logger.info("🚀 CAFEBOTIFY v7.0 STARTUP")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    await bot.set_webhook(WEBHOOK_URL)
    
    info = await bot.get_webhook_info()
    logger.info(f"✅ WEBHOOK: {info.url}")
    
    await bot.send_message(
        ADMIN_ID,
        "🎉 <b>CAFEBOTIFY v7.0 LIVE!</b>\n\n"
        f"🌐 {WEBHOOK_URL}\n"
        "✅ Тест: /start → ☕ → 2️⃣\n"
        "💰 Цена: 2990₽/мес"
    )

async def on_shutdown(app):
    await bot.delete_webhook()
    await dp.storage.close()

# ========================================
def create_app():
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/", healthcheck)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == '__main__':
    logger.info("🎬 CAFEBOTIFY v7.0 — Бот вместо администратора!")
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)
