import os
import json
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
# ✅ ЧИТАЕМ ВАШ config.json
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data['cafe']
    except FileNotFoundError:
        logger.error("❌ config.json не найден!")
        return None
    except KeyError:
        logger.error("❌ Неверный формат config.json!")
        return None

cafe_config = load_config()
if not cafe_config:
    raise Exception("🚫 Нужен config.json с разделом 'cafe'!")

# ✅ ИЗВЛЕКАЕМ ДАННЫЕ ИЗ ВАШЕГО config
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = cafe_config["menu"]
WORK_START_HOUR = cafe_config["work_hours"][0]  # 9
WORK_END_HOUR = cafe_config["work_hours"][1]    # 21

# ✅ ЧАСЫ РАБОТЫ из массива [9, 21]
WORK_START = time(WORK_START_HOUR, 0)
WORK_END = time(WORK_END_HOUR, 0)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
HOST = "0.0.0.0"
WEBHOOK_PATH = "/webhook"

# ========================================
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class OrderStates(StatesGroup):
    waiting_for_quantity = State()

# ========================================
def get_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for drink in MENU.keys():
        kb.add(drink)
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
        return f"🟢 <b>Открыто сейчас</b> (до {WORK_END_HOUR}:00)"
    else:
        return f"🔴 <b>Закрыто</b>\n🕐 Работаем с {WORK_START_HOUR}:00 до {WORK_END_HOUR}:00"

# ========================================
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    
    status = get_work_status()
    
    welcome_text = (
        f"{CAFE_NAME}\n\n"
        f"🏪 {status}\n\n"
        "<b>☕ Выберите напиток или действие ниже 😊</b>"
    )
    
    await message.answer(welcome_text, reply_markup=get_menu_keyboard())
    logger.info(f"👤 /start от {message.from_user.id}")

# ========================================
@dp.message_handler(lambda m: m.text in MENU.keys())
async def drink_selected(message: types.Message, state: FSMContext):
    if not is_cafe_open():
        await message.answer(
            f"🔴 <b>{CAFE_NAME} закрыто!</b>\n\n"
            f"📞 {CAFE_PHONE}\n"
            f"{get_work_status()}",
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
            f"📞 <b>Связь с {CAFE_NAME}:</b>\n"
            f"<code>{CAFE_PHONE}</code>\n\n"
            f"Или закажите ☕:",
            reply_markup=get_menu_keyboard()
        )
    elif "⏰" in message.text:
        await message.answer(
            f"🕐 <b>Часы работы {CAFE_NAME}:</b>\n"
            f"🟢 {WORK_START_HOUR}:00 - {WORK_END_HOUR}:00 ежедневно\n\n"
            f"{get_work_status()}\n\n"
            "👇 Заказ:",
            reply_markup=get_menu_keyboard()
        )
    elif "О боте" in message.text:
        await message.answer(
            f"🤖 <b>CAFEBOTIFY — 2 990 ₽/мес</b>\n\n"
            "✅ Цифровое меню в Telegram\n"
            "✅ Приём заказов 24/7\n"
            "✅ Уведомления владельцу\n"
            "✅ Часы работы + автоответ\n\n"
            f"🎯 Для {CAFE_NAME}",
            reply_markup=get_main_keyboard()
        )
    else:  # ☕ Меню
        menu_text = f"🍽️ <b>Меню {CAFE_NAME}:</b>\n\n"
        for drink, price in MENU.items():
            menu_text += f"{drink} — <b>{price}₽</b>\n"
        await message.answer(menu_text, reply_markup=get_menu_keyboard())

@dp.message_handler()
async def unknown(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        f"❓ <b>Выберите из меню ☕ {CAFE_NAME}</b>\n\n"
        f"{get_work_status()}",
        reply_markup=get_menu_keyboard()
    )

# ========================================
async def send_order_to_admin(order_data):
    text = (
        f"🔔 <b>🚨 НОВЫЙ ЗАКАЗ #{order_data['user_id']} | {CAFE_NAME}</b>\n\n"
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
if __name__ == '__main__':
    logger.info(f"🎬 CAFEBOTIFY v8.1 — {CAFE_NAME}")
    logger.info(f"☕ Меню: {len(MENU)} позиций")
    logger.info(f"🕐 Часы: {WORK_START_HOUR}:00 - {WORK_END_HOUR}:00")
    logger.info(f"📞 Телефон: {CAFE_PHONE}")
    
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=lambda *_: logger.info("🚀 v8.1 LIVE!"),
        on_shutdown=lambda *_: logger.info("🛑 v8.1 STOP"),
        skip_updates=True,
        host=HOST,
        port=PORT,
    )
