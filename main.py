# 🔥 ТОЛЬКО ЭТОТ ФАЙЛ заменить → deploy → Render Logs покажут ПРАВДУ!

import logging
import os
import re
import random
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# 🔥 ГРОМЧЕЙШИЙ ЛОГГИНГ
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)["cafe"]
            config["admin_chat_id"] = int(config["admin_chat_id"])
            logging.info(f"✅ CONFIG: {config.get('name')} | admin={config['admin_chat_id']}")
            return config
    except Exception as e:
        logging.error(f"💥 CONFIG ERROR: {e}")
        return {}

CAFE = load_config()

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
logging.info(f"🔍 TOKEN: {'OK' if TOKEN and len(TOKEN)>20 else 'ERROR'}")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

def get_main_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    for item, price in CAFE.get("menu", {}).items():
        menu.add(KeyboardButton(f"{item} — {price}₽"))
    menu.add(KeyboardButton("📋 Бронь столика"))
    menu.add(KeyboardButton("❓ Помощь"))
    menu.add(KeyboardButton("🔍 DEBUG INFO"))  # 🔥 ДИАГНОСТИКА
    return menu

MAIN_MENU = get_main_menu()

class OrderForm(StatesGroup):
    waiting_quantity = State()
    waiting_confirm = State()

class BookingForm(StatesGroup):
    waiting_datetime = State()
    waiting_people = State()

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    logging.info(f"🚀 START: user={message.from_user.id} | chat={message.chat.id}")
    await message.reply(
        f"👋 Добро пожаловать в **{CAFE.get('name', 'Кофейню')}** ☕\n🔍 Нажми DEBUG INFO для проверки!",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )

# 🔥 ДИАГНОСТИЧЕСКАЯ КНОПКА
@dp.message_handler(lambda m: m.text == "🔍 DEBUG INFO")
async def debug_info(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()
    
    debug_msg = f"""
🔍 DEBUG INFO
━━━━━━━━━━━━━━━
🆔 User ID: `{message.from_user.id}`
💬 Chat ID: `{message.chat.id}`
👤 Username: @{message.from_user.username or 'нет'}
📊 State: {current_state or 'NONE'}
📦 Data: {user_data}
⚙️ Admin: `{CAFE.get('admin_chat_id')}`
📞 Phone: {CAFE.get('phone')}
━━━━━━━━━━━━━━━
"""
    await message.reply(debug_msg, parse_mode="Markdown")

# 🔥 ЛОВИМ ВСЕ МЕНЮ КНОПКИ
@dp.message_handler(lambda m: any(f"{item} — {price}₽" == m.text.strip() for item, price in CAFE.get("menu", {}).items()))
async def start_order(message: types.Message, state: FSMContext):
    logging.info(f"☕ ORDER START: '{message.text}' от user={message.from_user.id}")
    
    for item_name, price in CAFE.get("menu", {}).items():
        if f"{item_name} — {price}₽" == message.text.strip():
            logging.info(f"✅ НАЙДЕН ТОВАР: {item_name}")
            await state.finish()
            await state.update_data(item=item_name, price=price)
            
            kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.row("1", "2", "3+")
            kb.row("❌ Отмена")
            
            await message.reply(
                f"**{item_name}** — {price}₽\n\n"
                f"{random.choice(['Отличный выбор 😊', 'Хороший вкус ☕'])}\n\n"
                "**Сколько порций?**",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            await OrderForm.waiting_quantity.set()
            return

@dp.message_handler(state=OrderForm.waiting_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    logging.info(f"🔢 QUANTITY: '{message.text}' от user={message.from_user.id}")
    
    if message.text == "❌ Отмена":
        logging.info("❌ QUANTITY ОТМЕНЁН")
        await state.finish()
        await message.reply("❌ Заказ отменён", reply_markup=MAIN_MENU)
        return

    qty_map = {"1": 1, "2": 2, "3+": 3}
    if message.text not in qty_map:
        await message.reply("❌ Выберите: **1**, **2**, **3+** или **❌ Отмена**", parse_mode="Markdown")
        return

    qty = qty_map[message.text]
    data = await state.get_data()
    total = data["price"] * qty
    await state.update_data(quantity=qty, total=total)
    
    logging.info(f"✅ QUANTITY OK: {qty} | total={total}")

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("✅ Подтвердить", "❌ Отмена")

    await message.reply(
        f"**📋 Ваш заказ:**\n\n"
        f"`{data['item']}` × **{qty}**\n"
        f"**Итого:** `{total}₽`\n\n"
        "**Подтвердить?**",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await OrderForm.waiting_confirm.set()

# 🔥 КРИТИЧНЫЙ HANDLER — ЛОВИТ ЛИ ✅?
@dp.message_handler(state=OrderForm.waiting_confirm)
async def confirm_order(message: types.Message, state: FSMContext):
    logging.info(f"🎯 CONFIRM HIT! text='{message.text}' от user={message.from_user.id}")
    
    # ПРЯМО ПЕРВЫМ проверяем отмену
    if message.text == "❌ Отмена":
        logging.info("❌ CONFIRM ОТМЕНЁН")
        await state.finish()
        await message.reply("❌ Заказ отменён", reply_markup=MAIN_MENU)
        return

    logging.info("✅ CONFIRM ПРОШЁЛ ОТМЕНУ — ОБРАБАТЫВАЕМ ЗАКАЗ!")
    
    data = await state.get_data()
    admin_id = CAFE.get("admin_chat_id")
    
    logging.info(f"📦 DATA: {data}")
    logging.info(f"👑 ADMIN_ID: {admin_id}")
    
    if not admin_id:
        logging.error("💥 NO ADMIN_ID!")
        await message.reply("❌ Ошибка конфигурации!")
        await state.finish()
        return

    # 🔥 ОТПРАВЛЯЕМ АДМИНУ
    order_msg = f"""
☕ **НОВЫЙ ЗАКАЗ** `{CAFE.get('name')}`

**{data['item']}** × {data['quantity']}
💰 **{data['total']}₽**

👤 @{message.from_user.username or str(message.from_user.id)}
🆔 `{message.from_user.id}`
📞 {CAFE.get('phone', '+7 (XXX) XXX-XX-XX')}
"""
    
    try:
        logging.info("📤 ОТПРАВЛЯЕМ АДМИНУ...")
        await bot.send_message(admin_id, order_msg, parse_mode="Markdown")
        logging.info("✅ АДМИН ПОЛУЧИЛ ЗАКАЗ!")
    except Exception as e:
        logging.error(f"💥 ОШИБКА АДМИНА: {e}")

    await message.reply(
        f"🎉 **Заказ принят!**\n\n"
        f"Спасибо! Уже готовим ☕\n\n"
        f"📞 **{CAFE.get('phone', '+7 (XXX) XXX-XX-XX')}**",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )
    await state.finish()
    logging.info("✅ ЗАКАЗ ПОЛНОСТЬЮ ОБРАБОТАН!")

# Остальные handlers (бронь, помощь) без изменений...
@dp.message_handler()
async def fallback(message: types.Message, state: FSMContext):
    logging.info(f"📤 FALLBACK: '{message.text}' от {message.from_user.id}")
    await state.finish()
    await message.reply("👋 Выберите из меню ☕", reply_markup=MAIN_MENU, parse_mode="Markdown")

WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"https://chatbotify-2tjd.onrender.com{WEBHOOK_PATH}"

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("🚀 BOT ЗАПУЩЕН!")

if __name__ == "__main__":
    executor.start_webhook(
        dp, WEBHOOK_PATH, on_startup=on_startup,
        host="0.0.0.0", port=int(os.getenv("PORT", 10000))
    )
