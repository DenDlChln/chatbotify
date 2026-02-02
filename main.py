import logging
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import CAFE

logging.basicConfig(level=logging.INFO)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# ✅ Инициализация с MemoryStorage (FSM работает!)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ------------------ ГЛАВНОЕ МЕНЮ ------------------
MAIN_MENU = ReplyKeyboardMarkup(resize_keyboard=True)

# Автогенерация кнопок меню из config.CAFE["menu"]
for item, price in CAFE["menu"].items():
    MAIN_MENU.add(KeyboardButton(f"{item} {price}₽"))

MAIN_MENU.add(KeyboardButton("📋 Бронь столика"))
MAIN_MENU.add(KeyboardButton("❓ Помощь"))

# ------------------ FSM СОСТОЯНИЯ ------------------
class OrderForm(StatesGroup):
    waiting_quantity = State()
    waiting_confirm = State()

class BookingForm(StatesGroup):
    waiting_datetime = State()
    waiting_people = State()

# ------------------ /START ------------------
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.reply(
        f"👋 Добро пожаловать в **{CAFE['name']}** ☕\n\n"
        "Выберите действие:",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# ------------------ ЗАКАЗЫ (строго по кнопкам меню) ------------------
@dp.message_handler(lambda m: any(m.text.startswith(name) for name in CAFE["menu"]))
async def start_order(message: types.Message, state: FSMContext):
    # Извлекаем название блюда: "☕ Кофе 200₽" → "☕ Кофе"
    parts = message.text.rsplit(" ", 1)
    if len(parts) < 2:
        await message.reply("Выберите блюдо из меню ☝️", reply_markup=MAIN_MENU)
        return
    
    item_name = parts[0]
    if item_name not in CAFE["menu"]:
        await message.reply("Выберите блюдо из меню ☝️", reply_markup=MAIN_MENU)
        return

    price = CAFE["menu"][item_name]
    
    await state.update_data(item=item_name, price=price)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("1", "2", "3+")
    kb.row("❌ Отмена")

    await message.reply(
        f"**{item_name}** — {price}₽\n\n"
        "**Сколько порций?**\n"
        "`1`, `2`, `3+`",
        reply_markup=kb,
        parse_mode='Markdown'
    )
    await OrderForm.waiting_quantity.set()

@dp.message_handler(state=OrderForm.waiting_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.reply("❌ Заказ отменён ☕", reply_markup=MAIN_MENU)
        await state.finish()
        return

    if message.text not in {"1", "2", "3+"}:
        await message.reply(
            "❌ Выберите количество:\n"
            "`1`, `2`, `3+`\n"
            "или **❌ Отмена**",
            parse_mode='Markdown'
        )
        return

    qty = {"1": 1, "2": 2, "3+": 3}[message.text]
    data = await state.get_data()
    total = data["price"] * qty

    await state.update_data(quantity=qty, total=total)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("✅ Подтвердить", "❌ Отмена")

    await message.reply(
        f"**📋 Ваш заказ:**\n\n"
        f"`{data['item']}` × **{qty}**\n"
        f"**Итого:** `{total}₽`\n\n"
        "**Подтвердить заказ?**",
        reply_markup=kb,
        parse_mode='Markdown'
    )
    await OrderForm.waiting_confirm.set()

@dp.message_handler(state=OrderForm.waiting_confirm)
async def confirm_order(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.reply("❌ Заказ отменён ☕", reply_markup=MAIN_MENU)
        await state.finish()
        return

    if message.text != "✅ Подтвердить":
        await message.reply("❌ Нажмите **✅ Подтвердить** или **❌ Отмена**", parse_mode='Markdown')
        return

    data = await state.get_data()

    # ✅ УВЕДОМЛЕНИЕ АДМИНУ (главная фича для продаж!)
    await bot.send_message(
        CAFE["admin_chat_id"],
        f"☕ **НОВЫЙ ЗАКАЗ** `{CAFE['name']}`\n\n"
        f"**{data['item']}** × {data['quantity']}\n"
        f"💰 **{data['total']}₽**\n\n"
        f"👤 `@{message.from_user.username or message.from_user.id}`",
        parse_mode='Markdown'
    )

    await message.reply(
        "🎉 **Заказ принят!**\n\n"
        f"⏰ Готовим! Подходите к стойке ☕\n\n"
        f"📞 **{CAFE['phone']}** — уточнения",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

# ------------------ БРОНЬ СТОЛИКА ------------------
@dp.message_handler(lambda m: m.text == "📋 Бронь столика")
async def book_start(message: types.Message, state: FSMContext):
    start_h, end_h = CAFE["work_hours"]
    await message.reply(
        f"**📅 БРОНЬ СТОЛИКА** `{CAFE['name']}`\n\n"
        f"`ДД.ММ ЧЧ:ММ`\n"
        f"**Пример:** `15.02 19:00`\n\n"
        f"🕐 Работаем: **{start_h}:00–{end_h}:00**",
        parse_mode='Markdown'
    )
    await BookingForm.waiting_datetime.set()

@dp.message_handler(state=BookingForm.waiting_datetime)
async def parse_datetime(message: types.Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r"^(\d{1,2})\.(\d{1,2})\s+(\d{2}):(\d{2})$", text)
    
    if not match:
        await message.reply(
            "❌ **Неверный формат!**\n\n"
            "`15.02 19:00`\n\n"
            "🕐 **ЧЧ:ММ** — только 00 или 30 минут",
            parse_mode='Markdown'
        )
        return

    day, month, hour, minute = map(int, match.groups())
    now = datetime.now()
    start_h, end_h = CAFE["work_hours"]

    try:
        # Создаём дату/время
        booking_dt = now.replace(day=day, month=month, hour=hour, minute=minute, second=0, microsecond=0)
        if booking_dt <= now:
            booking_dt += timedelta(days=1)

        # Проверяем рабочее время
        if hour < start_h or hour > end_h:
            await message.reply(
                f"❌ Мы работаем **{start_h}:00–{end_h}:00**\n\n"
                "Выберите время в этом диапазоне.",
                parse_mode='Markdown'
            )
            return

        # ✅ Сохраняем дату
        await state.update_data(dt=booking_dt)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row("1-2", "3-4")
        kb.row("5+", "❌ Отмена")

        await message.reply(
            f"✅ **{booking_dt.strftime('%d.%m.%Y %H:%M')}**\n\n"
            "**👥 Сколько человек?**",
            reply_markup=kb,
            parse_mode='Markdown'
        )
        await BookingForm.waiting_people.set()

    except Exception:
        await message.reply("❌ Ошибка даты. Формат: `15.02 19:00`", parse_mode='Markdown')

@dp.message_handler(state=BookingForm.waiting_people)
async def finish_booking(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await message.reply("❌ Бронь отменена ☕", reply_markup=MAIN_MENU)
        await state.finish()
        return

    if message.text not in {"1-2", "3-4", "5+"}:
        await message.reply(
            "❌ Выберите количество человек:\n"
            "**1-2**, **3-4**, **5+**\n"
            "или **❌ Отмена**",
            parse_mode='Markdown'
        )
        return

    people_map = {"1-2": 2, "3-4": 4, "5+": 6}
    people = people_map[message.text]
    data = await state.get_data()

    # ✅ УВЕДОМЛЕНИЕ АДМИНУ
    await bot.send_message(
        CAFE["admin_chat_id"],
        f"📋 **НОВАЯ БРОНЬ** `{CAFE['name']}`\n\n"
        f"**{data['dt'].strftime('%d.%m %H:%M')}**\n"
        f"👥 **{people} человек**\n\n"
        f"👤 `@{message.from_user.username or message.from_user.id}`",
        parse_mode='Markdown'
    )

    await message.reply(
        "✅ **Бронь подтверждена!**\n\n"
        f"📞 **{CAFE['phone']}** — для подтверждения\n\n"
        f"До встречи в **{CAFE['name']}** ☕",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )
    await state.finish()

# ------------------ ПОМОЩЬ ------------------
@dp.message_handler(lambda m: m.text == "❓ Помощь")
async def help_handler(message: types.Message):
    await message.reply(
        f"**{CAFE['name']} — справка**\n\n"
        f"☕ **Меню** — выберите блюдо → количество → подтвердите\n"
        f"📋 **Бронь** — дата/время → количество человек\n\n"
        f"📞 **{CAFE['phone']}** — вопросы\n"
        f"🕐 **{CAFE['work_hours'][0]}:00–{CAFE['work_hours'][1]}:00**",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# ------------------ Fallback (всё остальное) ------------------
@dp.message_handler()
async def fallback(message: types.Message):
    await message.reply(
        f"👋 **{CAFE['name']}**\n\n"
        "Выберите действие в меню ☝️",
        reply_markup=MAIN_MENU,
        parse_mode='Markdown'
    )

# ------------------ WEBHOOK (Render) ------------------
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ {CAFE['name']} LIVE на Render!")

if __name__ == "__main__":
    executor.start_webhook(
        dp,
        WEBHOOK_PATH,
        on_startup=on_startup,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )

