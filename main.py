import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.utils.exceptions import CantParseEntities

# 🛠️ ЛОГИ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔥 ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1471275603"))
CAFE_PHONE = os.getenv("CAFE_PHONE", "+7 989 273-67-56")

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN обязателен!")
    exit(1)

logger.info(f"🚀 START | ADMIN: {ADMIN_ID} | PHONE: {CAFE_PHONE}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# 🍽️ МЕНЮ
CAFE_MENU = {
    "☕ Капучино": 250,
    "🥛 Латте": 270, 
    "🍵 Чай": 180,
    "⚡ Эспрессо": 200
}

MAIN_MENU = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton("☕ Капучино — 250₽")],
        [KeyboardButton("🥛 Латте — 270₽")],
        [KeyboardButton("🔧 Настроить уведомления")]
    ]
)

class OrderStates(StatesGroup):
    waiting_quantity = State()
    waiting_confirm = State()

# 🔔 START
@dp.message_handler(commands=['start', 'help'])
async def start_cmd(message: types.Message):
    logger.info(f"✅ START от {message.from_user.id}")
    await message.reply(
        "☕ *Добро пожаловать в Кофейню!* ☕\n\n"
        "Выберите товар из меню:",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# 🔧 ДЕМО
@dp.message_handler(lambda m: "Настроить уведомления" in m.text)
async def demo_click(message: types.Message):
    logger.info(f"🎉 ДЕМО от {message.from_user.id}")
    await bot.send_message(
        ADMIN_ID,
        f"🎉 *НОВЫЙ КЛИЕНТ!*\n🆔 `{message.from_user.id}`\n👤 `{message.from_user.username or 'no_username'}`",
        parse_mode="Markdown"
    )
    await message.reply("✅ Уведомления настроены! Тестируйте меню ☕", reply_markup=MAIN_MENU)

# 🛒 ЗАКАЗЫ
@dp.message_handler(lambda m: any(item in m.text for item in CAFE_MENU.keys()))
async def process_order(message: types.Message, state: FSMContext):
    logger.info(f"☕ ЗАКАЗ '{message.text}' от {message.from_user.id}")
    
    for item, price in CAFE_MENU.items():
        if item in message.text:
            await state.update_data(item=item, price=price)
            await message.reply(
                f"*{item}* — {price}₽\n\nСколько порций?",
                reply_markup=ReplyKeyboardMarkup(
                    resize_keyboard=True, one_time_keyboard=True,
                    keyboard=[["1", "2", "3"], ["❌ Отмена"]]
                ),
                parse_mode="Markdown"
            )
            await OrderStates.waiting_quantity.set()
            return

# 🔢 КОЛИЧЕСТВО
@dp.message_handler(state=OrderStates.waiting_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await message.reply("❌ Заказ отменён", reply_markup=MAIN_MENU)
        return
    
    try:
        qty = int(message.text)
        data = await state.get_data()
        total = data['price'] * qty
        
        await state.update_data(quantity=qty, total=total)
        await message.reply(
            f"*Ваш заказ:*\n`{data['item']}` ×{qty}\n*Итого:* `{total}₽`\n\nПодтвердить?",
            reply_markup=ReplyKeyboardMarkup(
                resize_keyboard=True, one_time_keyboard=True,
                keyboard=[["✅ Да", "❌ Нет"]]
            ),
            parse_mode="Markdown"
        )
        await OrderStates.waiting_confirm.set()
    except:
        await message.reply("❌ Введите число 1-3 или Отмена")

# ✅ ПОДТВЕРЖДЕНИЕ
@dp.message_handler(state=OrderStates.waiting_confirm)
async def process_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if "Да" in message.text:
        # АДМИНУ
        admin_msg = (
            f"☕ *НОВЫЙ ЗАКАЗ!*\n\n"
            f"`{data['item']}` ×{data['quantity']}\n"
            f"*Сумма:* `{data['total']}₽`\n\n"
            f"👤 {message.from_user.first_name}\n"
            f"🆔 `{message.from_user.id}`\n"
            f"📞 {CAFE_PHONE}"
        )
        await bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        logger.info(f"✅ ЗАКАЗ {data['total']}₽ от {message.from_user.id}")
        
        # КЛИЕНТУ
        await message.reply(
            f"🎉 *Заказ #{data['total']}₽ принят!*\n"
            f"📞 Звоните: {CAFE_PHONE}",
            reply_markup=MAIN_MENU,
            parse_mode="Markdown"
        )
    else:
        await message.reply("❌ Заказ отменён", reply_markup=MAIN_MENU)
    
    await state.finish()

# 🛑 ОТМЕНА В ЛЮБОМ СОСТОЯНИИ
@dp.message_handler(lambda m: m.text == "❌ Отмена", state="*")
async def cancel_any(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("❌ Отменено", reply_markup=MAIN_MENU)

# 🛠️ ЛЮБЫЕ ДРУГИЕ СООБЩЕНИЯ
@dp.message_handler(state="*")
async def unknown(message: types.Message):
    logger.info(f"📨 '{message.text}' от {message.from_user.id}")
    await message.reply("👆 Нажмите кнопку из меню ☕", reply_markup=MAIN_MENU)

# 🛑 ОШИБКИ
@dp.errors_handler()
async def errors_handler(update, exception):
    logger.error(f"❌ ОШИБКА: {exception}")
    if isinstance(exception, CantParseEntities):
        logger.info("⚠️ Markdown ошибка - игнор")
    return True

# 🚀 WEBHOOK ДЛЯ RENDER
async def on_startup(dp):
    webhook_url = "https://chatbotify-2tjd.onrender.com/webhook"
    # УДАЛЯЕМ старый webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🧹 Старые сообщения удалены")
    # УСТАНАВЛИВАЕМ новый
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ WEBHOOK: {webhook_url}")

async def on_shutdown(dp):
    await bot.delete_webhook()
    logger.info("🔴 BOT STOPPED")

if __name__ == '__main__':
    logger.info("🚀 ЗАПУСК WEBHOOK SERVER...")
    executor.start_webhook(
        dispatcher=dp,
        webhook_path='/webhook',
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,  # ← ПРОПУСТИТЬ 32 старых сообщения!
        host='0.0.0.0',
        port=int(os.getenv("PORT", 10000))
    )
