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
    await message.reply("👋 **CafeBotify** ☕\nВыберите:", reply_markup=MAIN_MENU, parse_mode='Markdown')

# БРОНЬ: ШАГ 1
@dp.message_handler(lambda m: m.text == '📋 Бронь столика')
async def book_start(message: types.Message, state: FSMContext):
    await message.reply(
        "📅 **Дата время:**\n`ДД.ММ ЧЧ:ММ`\n`15.02 19:00`",
        parse_mode='Markdown'
    )
    await BookingForm.waiting_datetime.set()

# БРОНЬ: ШАГ 2 - ПАРСЕР
@dp.message_handler(state=BookingForm.waiting_datetime)
async def parse_datetime(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    # СТРОГОЕ совпадение паттерна
    match = re.match(r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})$', text)
    if not match:
        await message.reply("❌ `15.02 19:00`", parse_mode='Markdown')
        return  # ОСТАЁМСЯ В СОСТОЯНИИ
    
    day, mon, hour, min_ = map(int, match.groups())
    now = datetime.now()
    
    try:
        dt = now.replace(day=day, month=mon, hour=hour, minute=min_)
        if dt <= now: dt += timedelta(days=1)
        
        if hour < 18 or hour > 22 or min_ not in [0, 30]:
            await message.reply("❌ 18:00/18:30...22:00")
            return
        
        await state.update_data(dt=dt)
        
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row('1-2', '3-4').row('5+', '❌ Отмена')
        
        await message.reply(
            f"✅ **{dt.strftime('%d.%m %H:%M')}**\n\n👥 **Люди?**",
            reply_markup=kb,
            parse_mode='Markdown'
        )
        await BookingForm.waiting_people.set()  # ПЕРЕХОД
        
    except:
        await message.reply("❌ **Формат:** `15.02 19:00`")
        return  # ОСТАЁМСЯ

# БРОНЬ: ШАГ 3 - ЛЮДИ
@dp.message_handler(state=BookingForm.waiting_people)
async def finish_booking(message: types.Message, state: FSMContext):
    text = message.text
    if text == '❌ Отмена':
        await message.reply("❌ Отмена", reply_markup=MAIN_MENU)
        await state.finish()
        return
    
    people = {'1-2': 2, '3-4': 4, '5+': 6}.get(text, 2)
    data = await state.get_data()
    
    await message.reply(
        f"✅ **БРОНЬ ОК!**\n"
        f"📅 {data['dt'].strftime('%d.%m %H:%M')}\n"
        f"👥 {people} чел\n\n"
        f"📞 8(861)123-45-67\n☕ **CafeBotify**",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

# ❌ ЗАКАЗЫ ТОЛЬКО БЕЗ FSM
@dp.message_handler(state=None)  # ❌ КРИТИЧНО: state=None
async def handle_order(message: types.Message):
    text = message.text.lower()
    
    if any(x in text for x in ['кофе', '☕']):
        await message.reply("☕ **Кофе 200₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    elif any(x in text for x in ['чай', '🍵']):
        await message.reply("🍵 **Чай 150₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    elif any(x in text for x in ['пирог', '🥧']):
        await message.reply("🥧 **Пирог 100₽** ✅", reply_markup=MAIN_MENU, parse_mode='Markdown')
    else:
        await message.reply("☕ **Меню:** кофе/чай/пирог\n📋 Бронь", reply_markup=MAIN_MENU, parse_mode='Markdown')

# WEBHOOK
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ LIVE!")

if __name__ == '__main__':
    executor.start_webhook(
        dp, WEBHOOK_PATH, on_startup=on_startup,
        host="0.0.0.0", port=int(os.getenv('PORT', 10000))
    )


