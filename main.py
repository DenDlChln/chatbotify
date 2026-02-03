import asyncio
import json
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp

# 🛠️ ЛОГИ + КОНФИГ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1471275603  # ТВОЙ ID
CAFE_PHONE = "+7 989 273-67-56"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# 🍽️ МЕНЮ
CAFE_MENU = {
    "☕ Капучино": 250,
    "🥛 Латте": 270,
    "🍵 Чай": 180,
    "⚡ Эспрессо": 200,
    "☕ Американо": 300,
    "🍫 Мокачино": 230,
    "🤍 Раф": 400,
    "🧊 Раф со льдом": 370
}

MAIN_MENU = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton("☕ Капучино — 250₽")],
        [KeyboardButton("🥛 Латте — 270₽"), KeyboardButton("🍵 Чай — 180₽")],
        [KeyboardButton("⚡ Эспрессо — 200₽"), KeyboardButton("☕ Американо — 300₽")],
        [KeyboardButton("🍫 Мокачино — 230₽"), KeyboardButton("🤍 Раф — 400₽")],
        [KeyboardButton("🧊 Раф со льдом — 370₽")],
        [KeyboardButton("📋 Бронь столика"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("🔧 Настроить уведомления"), KeyboardButton("🔍 DEBUG INFO")]
    ]
)

# 🧠 STATES
class OrderStates(StatesGroup):
    waiting_quantity = State()
    waiting_confirm = State()

# 🔔 ГЛАВНОЕ МЕНЮ
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.reply(
        "☕ *Добро пожаловать в Кофейню «Уют»* ☕\n\n"
        "Выберите товар из меню ниже:",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# 🛒 ОБРАБОТКА ЗАКАЗОВ
@dp.message_handler(lambda message: any(item in message.text for item in CAFE_MENU.keys()))
async def process_order(message: types.Message):
    logger.info(f"☕ ORDER START: '{message.text}' от user={message.from_user.id}")
    
    for item_name, price in CAFE_MENU.items():
        if item_name in message.text:
            await message.reply(
                f"*{item_name}* — {price}₽\n\n"
                "Отличный выбор 😊\n\n"
                "*Сколько порций?*",
                reply_markup=ReplyKeyboardMarkup(
                    resize_keyboard=True,
                    one_time_keyboard=True,
                    keyboard=[
                        ["1", "2", "3+"],
                        ["❌ Отмена"]
                    ]
                ),
                parse_mode="Markdown"
            )
            await OrderStates.waiting_quantity.set()
            return
    await message.reply("❌ Товар не найден. Выберите из меню.", reply_markup=MAIN_MENU)

# 🔢 КОЛИЧЕСТВО
@dp.message_handler(state=OrderStates.waiting_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await message.reply("Заказ отменён. Выберите товар:", reply_markup=MAIN_MENU)
        return
    
    try:
        if message.text == "3+":
            quantity = 3
        else:
            quantity = int(message.text)
        
        item = state.get_data().get('item', 'Неизвестно')
        price = state.get_data().get('price', 0)
        total = price * quantity
        
        await state.update_data(item=item_name, price=price, quantity=quantity, total=total)
        
        await message.reply(
            f"📋 *Ваш заказ:*\n\n"
            f"`{item}` × *{quantity}*\n"
            "*Итого:* `{total}₽`\n\n"
            "*Подтвердить?*",
            reply_markup=ReplyKeyboardMarkup(
                resize_keyboard=True,
                one_time_keyboard=True,
                keyboard=[
                    ["✅ Подтвердить", "❌ Отмена"]
                ]
            ),
            parse_mode="Markdown"
        )
        await OrderStates.waiting_confirm.set()
    except:
        await message.reply("❌ Введите число (1, 2, 3+ или Отмена)", reply_markup=MAIN_MENU)

# ✅ ПОДТВЕРЖДЕНИЕ
@dp.message_handler(lambda m: m.text == "✅ Подтвердить", state=OrderStates.waiting_confirm)
async def confirm_order(message: types.Message, state: FSMContext):
    data = await state.get_data()
    logger.info(f"✅ CONFIRM ПРОШЁЛ ОТМЕНУ — ОБРАБОТЫВАЕМ ЗАКАЗ!")
    logger.info(f"📦 DATA: {data}")
    logger.info(f"👑 ADMIN_ID: {ADMIN_ID}")
    
    # 📤 ОТПРАВЛЯЕМ АДМИНУ
    logger.info("📤 ОТПРАВЛЯЕМ АДМИНУ...")
    admin_msg = (
        f"☕ *НОВЫЙ ЗАКАЗ* `Кофейня «Уют» ☕`\n\n"
        f"*{data['item']}* × {data['quantity']}\n"
        f"💰 *{data['total']}₽*\n\n"
        f"👤 @{message.from_user.username or 'no_username'}\n"
        f"🆔 `{message.from_user.id}`\n"
        f"📞 {CAFE_PHONE}"
    )
    
    await bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    logger.info("✅ АДМИН ПОЛУЧИЛ ЗАКАЗ!")
    
    # 👤 ПОДТВЕРЖДЕНИЕ КЛИЕНТУ
    await message.reply(
        f"🎉 *Заказ принят!*\n\n"
        f"Спасибо! Уже готовим ☕\n\n"
        f"📞 *{CAFE_PHONE}*",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )
    logger.info("✅ ЗАКАЗ ПОЛНОСТЬЮ ОБРАБОТАН!")
    await state.finish()

# 🚫 ОТМЕНА
@dp.message_handler(lambda m: m.text == "❌ Отмена", state="*")
async def cancel_order(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("❌ Заказ отменён. Выберите товар:", reply_markup=MAIN_MENU)

# 🔧 ДЕМО КНОПКА
@dp.message_handler(lambda m: m.text == "🔧 Настроить уведомления")
async def setup_notifications(message: types.Message):
    logger.info(f"🎉 ДЕМО КЛИК: user={message.from_user.id}")
    
    await bot.send_message(
        ADMIN_ID,
        f"🎉 **НОВЫЙ КЛИЕНТ ХОЧЕТ ДЕМО!**\n\n"
        f"🆔 `{message.from_user.id}`\n"
        f"👤 @{message.from_user.username or 'no_username'}\n"
        f"📱 {message.from_user.first_name}\n"
        f"⏰ {datetime.now().strftime('%d.%m %H:%M')}",
        parse_mode="Markdown"
    )
    
    await message.reply(
        "✅ *Уведомления настроены!* 🎉\n\n"
        "🔥 Теперь все заказы будут приходить админу!\n\n"
        "Тестируйте меню ☕",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# ❓ ПОМОЩЬ
@dp.message_handler(lambda m: m.text == "❓ Помощь")
async def help_cmd(message: types.Message):
    await message.reply(
        "☕ *Помощь*\n\n"
        "• Выберите товар из меню\n"
        "• Укажите количество\n"
        "• Подтвердите заказ\n\n"
        "📞 " + CAFE_PHONE,
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# 📋 БРОНЬ
@dp.message_handler(lambda m: m.text == "📋 Бронь столика")
async def booking(message: types.Message):
    await message.reply(
        f"📋 *Бронь столика*\n\n"
        f"📞 Звоните: {CAFE_PHONE}\n"
        f"⏰ Режим: 8:00-23:00",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# 🔍 DEBUG (ИСПРАВЛЕННЫЙ)
@dp.message_handler(lambda m: m.text == "🔍 DEBUG INFO")
async def debug_info(message: types.Message):
    """🔧 ИСПРАВЛЕННАЯ версия без Markdown ошибок"""
    try:
        # ✅ HTML вместо Markdown = НИКОГДА не ломается
        debug_msg = f"""
🔍 DEBUG INFO
━━━━━━━━━━━━━━━
🆔 User ID: {message.from_user.id}
💬 Chat ID: {message.chat.id}
👤 Username: @{message.from_user.username or 'no_username'}
📊 State: NONE
📦 Data: {{}}
⚙️ Admin: {ADMIN_ID}
📞 Phone: {CAFE_PHONE}
━━━━━━━━━━━━━━━
        """.strip()
        
        await message.reply(debug_msg, parse_mode="HTML")
        logger.info("✅ DEBUG OK")
    except Exception as e:
        logger.error(f"❌ DEBUG ERROR: {e}")
        await message.reply("❌ Ошибка DEBUG. Продолжаем работу.")

# 🛑 ОСЫЛКИ
@dp.errors_handler()
async def errors_handler(update, exception):
    logger.error(f"❌ ОШИБКА: {exception}")
    return True

if __name__ == '__main__':
    from aiogram import executor
    executor.start_webhook(
        dispatcher=dp,
        webhook_path="/webhook",
        on_startup=None,
        on_shutdown=None,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
