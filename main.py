import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
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
WEBHOOK_PATH = "/webhook"

# ✅ ЧАСЫ РАБОТЫ (ПРОДАКТ ФИЧА)
WORK_START = time(9, 0)   # 9:00
WORK_END = time(21, 0)    # 21:00

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

MENU = {
    "☕ <b>Капучино</b>": 250,
    "🥛 <b>Латте</b>": 270,
    "🍵 <b>Чай</b>": 180,
    "☕ <b>Американо</b>": 200
}

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("☕ <b>Капучино</b>")
    kb.add("🥛 <b>Латте</b>")
    kb.add("🍵 <b>Чай</b>")
    kb.add("☕ <b>Американо</b>")
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
    kb.row("⏰ Часы работы", "ℹ️ О боте")
    return kb

# ========================================
def is_cafe_open():
    now = datetime.now().time()
    return WORK_START <= now <= WORK_END

def get_work_status():
    now = datetime.now().time()
    if is_cafe_open():
        return "🟢 <b>Открыто сейчас</b> (до 21:00)"
    else:
        return "🔴 <b>Закрыто</b>\n🕐 Работаем с 9:00 до 21:00"

# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    
    status = get_work_status()
    
    welcome_text = (
        "🤖 <b>CAFEBOTIFY</b>\n"
        "🍽️ <i>Бот вместо администратора</i>\n\n"
        f"🏪 {status}\n\n"
        "👇 <b>Выберите напиток:</b>"
    )
    
    await message.answer(welcome_text, reply_markup=get_menu_keyboard())
    logger.info(f"👤 /start от {message.from_user.id}")

# ========================================
@dp.message_handler(lambda m: any(k in m.text for k in MENU.keys()))
async def drink_selected(message: types.Message, state: FSMContext):
    if not is_cafe_open():
        await message.answer(
            "🔴 <b>Кафе закрыто!</b>\n\n"
            f"📞 {CAFE_PHONE}\n"
            f"🕐 {get_work_status()}",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Находим точное совпадение
    drink_key = next((k for k in MENU.keys() if k in message.text), None)
    if not drink_key:
        return
        
    await state.finish()
    drink = drink_key
    price = MENU[drink]
    
    await state.update_data(drink=drink, price=price)
    await OrderStates.waiting_for_quantity.set()
    
    await message.answer(
        f"{drink}\n"
        f"💰 <b>{price} ₽</b>\n\n"
        f"📝 <b>Сколько порций?</b>",
        reply_markup=get_quantity_keyboard()
    )
    logger.info(f"🥤 Выбрано: {drink}")

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
            total = data['price'] * qty
            
            await state.finish()
            await send_order_to_admin({
                'user_id': message.from_user.id,
                'first_name': message.from_user.first_name or "Гость",
                'username': message.from_user.username or "",
                'drink': data['drink'],
                'quantity': qty,
                'total': total
            })
            
            await message.answer(
                f"🎉 <b>Заказ #{message.from_user.id}</b>\n\n"
                f"{data['drink']}\n"
                f"📊 <b>{qty} порций</b>\n"
                f"💰 <b>{total} ₽</b>\n\n"
                f"📞 {CAFE_PHONE}\n"
                "✅ Готовим!",
                reply_markup=get_main_keyboard()
            )
            logger.info(f"✅ Заказ {total}₽")
            return
    except:
        pass
    
    data = await state.get_data()
    await message.answer(
        f"{data['drink']}\n💰 <b>{data['price']} ₽</b>\n\n"
        "❌ Выберите <b>1️⃣-5️⃣</b> или <b>🔙 Отмена</b>",
        reply_markup=get_quantity_keyboard()
    )

# ========================================
@dp.message_handler(text=["☕ Меню", "📞 Позвонить", "⏰ Часы работы", "ℹ️ О боте"])
async def menu_actions(message: types.Message, state: FSMContext):
    await state.finish()
    
    if "📞" in message.text:
        await message.answer(
            f"📞 <b>Связь с кафе:</b>\n"
            f"<code>{CAFE_PHONE}</code>\n\n"
            f"Или закажите ☕:",
            reply_markup=get_menu_keyboard()
        )
    elif "⏰" in message.text:
        await message.answer(
            f"🕐 <b>Часы работы кафе:</b>\n"
            f"🟢 9:00 - 21:00 ежедневно\n\n"
            f"{get_work_status()}\n\n"
            "👇 Заказ:",
            reply_markup=get_menu_keyboard()
        )
    elif "О боте" in message.text:
        await message.answer(
            "🤖 <b>CAFEBOTIFY — 2 990 ₽/мес</b>\n\n"
            "✅ Цифровое меню в Telegram\n"
            "✅ Приём заказов 24/7\n"
            "✅ Уведомления владельцу\n"
            "✅ Часы работы + автоответ\n\n"
            "🎯 Для малых кафе (1 точка)",
            reply_markup=get_main_keyboard()
        )
    else:  # ☕ Меню
        menu_text = "🍽️ <b>Наше меню:</b>\n\n" + "\n".join([f"{k} — <b>{v}₽</b>" for k,v in MENU.items()])
        await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler()
async def unknown(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "❓ <b>Выберите из меню ☕</b>\n\n"
        f"{get_work_status()}",
        reply_markup=get_menu_keyboard()
    )

# ========================================
async def send_order_to_admin(order_data):
    """🚨 КРАСИВОЕ УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ"""
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']}</b>\n\n"
        f"👤 <b>{order_data['first_name']}</b>\n"
        f"🆔 <code>{order_data['user_id']}</code>\n"
        f"📱 <a href='tg://user?id={order_data['user_id']}'>Написать</a>\n\n"
        f"🥤 <b>{order_data['drink']}</b>\n"
        f"📊 <b>{order_data['quantity']} порций</b>\n"
        f"💰 <b>{order_data['total']} ₽</b>\n\n"
        f"📞 {CAFE_PHONE}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
        logger.info("✅ Админ уведомлён")
    except:
        logger.error("❌ Админ не уведомлён")

# ========================================
# ✅ EXECUTOR.START_WEBHOOK — РАБОТАЕТ НА RENDER!
if __name__ == '__main__':
    logger.info("🎬 CAFEBOTIFY v7.1 — Бот вместо администратора!")
    logger.info(f"🌐 {WEBHOOK_URL}")
    
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=lambda *_: logger.info("🚀 v7.1 LIVE!"),
        on_shutdown=lambda *_: logger.info("🛑 v7.1 STOP"),
        skip_updates=True,
        host=HOST,
        port=PORT,
    )
