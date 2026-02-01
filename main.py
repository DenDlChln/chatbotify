import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

# Токен из .env
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Главное меню - БРОНЬ ДОБАВЛЕНА! 🔥
MAIN_MENU = ReplyKeyboardMarkup(resize_keyboard=True)
MAIN_MENU.row(KeyboardButton('☕ Кофе 200₽'), KeyboardButton('📋 Бронь столика'))
MAIN_MENU.row(KeyboardButton('🍵 Чай 150₽'), KeyboardButton('🛒 Оформить заказ'))
MAIN_MENU.row(KeyboardButton('❓ Помощь'))

# СОСТОЯНИЯ БРОНИРОВАНИЯ
class BookingForm(StatesGroup):
    waiting_date = State()
    waiting_time = State()
    waiting_people = State()
    waiting_name = State()
    waiting_phone = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "👋 Привет!\n\n☕️ **МЕНЮ КАФЕ BOTIFY**\n\n"
        "☕ Кофе 200₽\n🍵 Чай 150₽\n🥧 Пирог 100₽\n📋 Бронь столика\n\n"
        "_Выбери кнопку или напиши заказ_",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# 🆕 БРОНИРОВАНИЕ (БЕЗ calendar!)
@dp.message_handler(lambda message: message.text == '📋 Бронь столика')
async def book_table_start(message: types.Message, state: FSMContext):
    await BookingForm.waiting_date.set()
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton("Сегодня", callback_data="date_today"),
        InlineKeyboardButton("Завтра", callback_data="date_tomorrow")
    )
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
    await message.reply("📅 Выберите дату:", reply_markup=keyboard)

@dp.callback_query_handler(text=["date_today", "date_tomorrow"], state=BookingForm.waiting_date)
async def pick_date(callback_query: types.CallbackQuery, state: FSMContext):
    date_text = "Сегодня" if callback_query.data == "date_today" else "Завтра"
    await state.update_data(date=date_text)
    await BookingForm.next()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    times = ["18:00", "19:00", "20:00", "21:00"]
    for t in times:
        keyboard.add(InlineKeyboardButton(t, callback_data=f"time_{t}"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
    
    await callback_query.message.edit_text(f"⏰ Выберите время ({date_text}):", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('time_'), state=BookingForm.waiting_time)
async def pick_time(callback_query: types.CallbackQuery, state: FSMContext):
    time = callback_query.data.replace('time_', '')
    await state.update_data(time=time)
    await BookingForm.next()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("👤 1-2", callback_data="people_2"))
    keyboard.add(InlineKeyboardButton("👥 3-4", callback_data="people_4"))
    keyboard.add(InlineKeyboardButton("👨‍👩‍👧‍👦 5+", callback_data="people_6"))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
    
    await callback_query.message.edit_text(f"👥 Сколько человек?\n⏰ {time}", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('people_'), state=BookingForm.waiting_people)
async def pick_people(callback_query: types.CallbackQuery, state: FSMContext):
    people = callback_query.data.replace('people_', '')
    data = await state.get_data()
    
    await callback_query.message.edit_text(
        f"✅ **Бронь подтверждена!**\n\n"
        f"📅 {data['date']}\n⏰ {data['time']}\n👥 {people} человек\n\n"
        f"📞 Позвоните для подтверждения:\n**8 (861) 123-45-67**\n\n"
        f"Спасибо за выбор CafeBotify! ☕",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

@dp.callback_query_handler(text="cancel_booking", state="*")
async def cancel_booking(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("❌ Бронь отменена.", reply_markup=MAIN_MENU)
    await state.finish()

# ТВОИ СТАРЫЕ ЗАКАЗЫ (БЕЗ ИЗМЕНЕНИЙ)
@dp.message_handler()
async def handle_order(message: types.Message):
    text = message.text.lower()
    
    if 'кофе' in text or '☕' in text:
        await message.reply(
            "☕ **Заказ принят**\n💰 Кофе классический — 200₽\n\n_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    elif 'чай' in text or '🍵' in text:
        await message.reply(
            "🍵 **Заказ принят**\n💰 Чай — 150₽\n\n_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    elif 'пирог' in text or '🥧' in text:
        await message.reply(
            "🥧 **Заказ принят**\n💰 Пирог яблочный — 100₽\n\n_✅ Подтвердить заказ?_",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('✅ Подтвердить'), KeyboardButton('❌ Отмена')]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
    else:
        await message.reply(
            "❓ **Не понял заказ**\n\n_Напиши:_\n• `кофе`\n• `чай`\n• `пирог`\n\n_или выбери кнопку ☝️_",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )

# WEBHOOK
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    bot = Bot(token=TOKEN)
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook activated!")

if __name__ == '__main__':
    executor.start_webhook(
        dp,
        WEBHOOK_PATH,
        on_startup=on_startup,
        host="0.0.0.0", 
        port=int(os.getenv('PORT', 10000))
    )
