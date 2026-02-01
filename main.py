import logging
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

MAIN_MENU = ReplyKeyboardMarkup(resize_keyboard=True)
MAIN_MENU.row(KeyboardButton('☕ Кофе 200₽'), KeyboardButton('📋 Бронь столика'))
MAIN_MENU.row(KeyboardButton('🍵 Чай 150₽'), KeyboardButton('🛒 Оформить заказ'))
MAIN_MENU.row(KeyboardButton('❓ Помощь'))

class BookingForm(StatesGroup):
    waiting_datetime = State()
    waiting_people = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "👋 Привет!\n\n☕️ **МЕНЮ КАФЕ BOTIFY**\n\n"
        "☕ Кофе 200₽ | 🍵 Чай 150₽ | 🥧 Пирог 100₽\n📋 Бронь столика\n\n"
        "_Выбери кнопку или напиши заказ_",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# 🆕 БРОНИРОВАНИЕ ТЕКСТОМ
@dp.message_handler(lambda message: message.text == '📋 Бронь столика')
async def book_table_start(message: types.Message, state: FSMContext):
    await message.reply(
        "📅 **Дата и время**:\n"
        "`ДД.ММ ЧЧ:ММ` → `15.02 19:00`\n\n"
        "💡 18:00-22:00 (сегодня/завтра)",
        parse_mode='Markdown'
    )
    await BookingForm.waiting_datetime.set()

@dp.message_handler(state=BookingForm.waiting_datetime)
async def process_datetime(message: types.Message, state: FSMContext):
    text = message.text.strip()
    pattern = r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})'
    
    if not re.match(pattern, text):
        await message.reply("❌ **Формат:** `15.02 19:00`", parse_mode='Markdown')
        return
    
    try:
        day, month, hour, minute = map(int, re.match(pattern, text).groups())
        now = datetime.now()
        booking_date = now.replace(day=day, month=month, hour=hour, minute=minute, second=0, microsecond=0)
        
        if booking_date <= now:
            booking_date += timedelta(days=1)
        
        if not (18 <= hour <= 22) or minute not in [0, 30]:
            await message.reply("❌ **Время:** 18:00, 18:30... 22:00", parse_mode='Markdown')
            return
        
        await state.update_data(datetime=booking_date)
        
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row('1-2', '3-4').row('5+', '❌ Отмена')
        
        await message.reply(
            f"✅ **{booking_date.strftime('📅 %d.%m %H:%M')}\n\n👥 Сколько человек?**",
            reply_markup=kb,
            parse_mode='Markdown'
        )
        await BookingForm.waiting_people.set()
        
    except:
        await message.reply("❌ **Формат:** `15.02 19:00`", parse_mode='Markdown')

@dp.message_handler(state=BookingForm.waiting_people)
async def process_people(message: types.Message, state: FSMContext):
    if message.text == '❌ Отмена':
        await message.reply("❌ Бронь отменена.", reply_markup=MAIN_MENU)
        await state.finish()
        return
    
    people_map = {'1-2': 2, '3-4': 4, '5+': 6}
    people = people_map.get(message.text, 2)
    data = await state.get_data()
    
    await message.reply(
        f"✅ **Бронь ОК!**\n\n"
        f"📅 {data['datetime'].strftime('%d.%m %H:%M')}\n"
        f"👥 {people} чел.\n\n"
        f"📞 8 (861) 123-45-67\n\n"
        f"🎉 CafeBotify!",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

# ❌ МЕНЯЕМ ПОРЯДОК: ЗАКАЗЫ ПОСЛЕ FSM
@dp.message_handler()
async def handle_order(message: types.Message):
    text = message.text.lower()
    
    if 'кофе' in text or '☕' in message.text:
        await message.reply("☕ **Кофе 200₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    elif 'чай' in text or '🍵' in message.text:
        await message.reply("🍵 **Чай 150₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    elif 'пирог' in text or '🥧' in message.text:
        await message.reply("🥧 **Пирог 100₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    else:
        await message.reply(
            "❓ **Меню:** кофе, чай, пирог\n_или кнопки ☝️_",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )

# WEBHOOK Render
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook activated!")

if __name__ == '__main__':
    executor.start_webhook(
        dp, WEBHOOK_PATH, on_startup=on_startup,
        host="0.0.0.0", port=int(os.getenv('PORT', 10000))
    )


