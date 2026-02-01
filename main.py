import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

# Токен
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ГЛАВНОЕ МЕНЮ с БРОНЬЮ
MAIN_MENU = ReplyKeyboardMarkup(resize_keyboard=True)
MAIN_MENU.row(KeyboardButton('☕ Кофе 200₽'), KeyboardButton('📋 Бронь столика'))
MAIN_MENU.row(KeyboardButton('🍵 Чай 150₽'), KeyboardButton('🛒 Оформить заказ'))
MAIN_MENU.row(KeyboardButton('❓ Помощь'))

# СОСТОЯНИЯ БРОНИРОВАНИЯ
class BookingForm(StatesGroup):
    waiting_date = State()
    waiting_time = State()
    waiting_people = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "👋 Привет!\n\n☕️ **МЕНЮ КАФЕ BOTIFY**\n\n"
        "☕ Кофе 200₽ | 🍵 Чай 150₽ | 🥧 Пирог 100₽\n"
        "📋 Бронь столика\n\n"
        "_Выбери кнопку или напиши заказ_",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# 🆕 БРОНИРОВАНИЕ СТОЛИКА (ФИКС!)
@dp.message_handler(lambda message: message.text == '📋 Бронь столика')
async def book_table_start(message: types.Message, state: FSMContext):
    await BookingForm.waiting_date.set()
    await message.reply(
        "📅 **Введите дату бронирования**\n\n"
        "_Примеры:_ `завтра`, `02.02`, `пятница`\n\n"
        "_или /отмена_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('/отмена'))
    )

@dp.message_handler(state=BookingForm.waiting_date)
async def process_date(message: types.Message, state: FSMContext):
    date = message.text
    await state.update_data(date=date)
    await BookingForm.next()
    
    # КНОПКИ ВРЕМЕНИ
    keyboard = InlineKeyboardMarkup(row_width=2)
    times = ["18:00", "19:00", "20:00", "21:00"]
    for t in times:
        keyboard.add(InlineKeyboardButton(t, callback_data=f"time_{t}"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
    
    await message.reply(
        f"⏰ **Выберите время** для `{date}`:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@dp.callback_query_handler(lambda c: c.data.startswith('time_'), state=BookingForm.waiting_time)
async def pick_time(callback_query: types.CallbackQuery, state: FSMContext):
    time = callback_query.data.replace('time_', '')
    await state.update_data(time=time)
    await BookingForm.next()
    
    # КНОПКИ КОЛИЧЕСТВА ЛЮДЕЙ
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("👤 1-2", callback_data="people_2"))
    keyboard.add(InlineKeyboardButton("👥 3-4", callback_data="people_4"))
    keyboard.add(InlineKeyboardButton("👨‍👩‍👧‍👦 5+", callback_data="people_6"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
    
    await callback_query.message.edit_text(
        f"👥 **Сколько человек?**\n⏰ {time}",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('people_'), state=BookingForm.waiting_people)
async def pick_people(callback_query: types.CallbackQuery, state: FSMContext):
    people = callback_query.data.replace('people_', '')
    data = await state.get_data()
    
    await callback_query.message.edit_text(
        f"✅ **Бронь подтверждена!**\n\n"
        f"📅 `{data['date']}`\n"
        f"⏰ `{data['time']}`\n"
        f"👥 `{people}` человек\n\n"
        f"📞 **Позвоните для подтверждения:**\n"
        f"`8 (861) 123-45-67`\n\n"
        f"☕ Спасибо за выбор CafeBotify!",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

# ✅ ОТМЕНА БРОНИ (ФИКС!)
@dp.message_handler(commands=['отмена'], state='*')
@dp.callback_query_handler(text="cancel_booking", state="*")
async def cancel_booking(item, state: FSMContext):
    await state.finish()
    if isinstance(item, types.CallbackQuery):
        await item.message.edit_text("❌ Бронь отменена.", reply_markup=MAIN_MENU)
    else:
        await item.reply("❌ Бронь отменена.", reply_markup=MAIN_MENU)

# 🔥 ОСНОВНОЙ ОБРАБОТЧИК ЗАКАЗОВ (ТОЛЬКО state=None!)
@dp.message_handler(state=None)  # ← ГЛАВНЫЙ ФИКС!
async def handle_order(message: types.Message):
    text = message.text.lower()
    
    if 'кофе' in text or '☕' in text:
        await message.reply(
            "☕ **Кофе классический 200₽** принят!\n\n"
            "_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    elif 'чай' in text or '🍵' in text:
        await message.reply(
            "🍵 **Чай 150₽** принят!\n\n"
            "_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    elif 'пирог' in text or '🥧' in text:
        await message.reply(
            "🥧 **Пирог яблочный 100₽** принят!\n\n"
            "_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    else:
        await message.reply(
            "❓ **Не понял заказ**\n\n"
            "_Напиши:_ `кофе` `чай` `пирог`\n"
            "_или выбери кнопку ☝️_\n\n"
            "📋 **Бронь столика** тоже доступна!",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )

# WEBHOOK
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    bot = Bot(token=TOKEN)
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook activated! CafeBotifyBot LIVE!")

if __name__ == '__main__':
    executor.start_webhook(
        dp, WEBHOOK_PATH, on_startup=on_startup,
        host="0.0.0.0", port=int(os.getenv('PORT', 10000))
    )

