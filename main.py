import os
import json
import logging
import asyncio
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, Any

import redis.asyncio as redis
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.client.default import DefaultBotProperties

# ========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
MSK_TZ = timezone(timedelta(hours=3))
WORK_START = 9
WORK_END = 21

def load_config() -> Dict[str, Any]:
    """Загрузка конфигурации из config.json"""
    default_config = {
        "name": "Кофейня «Уют» ☕",
        "phone": "+7 989 273-67-56", 
        "admin_chat_id": 1471275603,
        "menu": {
            "☕ Капучино": 250,
            "🥛 Латте": 270,
            "🍵 Чай": 180,
            "⚡ Эспрессо": 200,
            "🧋 Bubble Tea": 320
        }
    }
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            config = data.get('cafe', {})
            default_config.update({
                'name': config.get('name', default_config['name']),
                'phone': config.get('phone', default_config['phone']),
                'admin_chat_id': config.get('admin_chat_id', default_config['admin_chat_id']),
                'menu': config.get('menu', default_config['menu'])
            })
    except Exception as e:
        logger.warning(f"Ошибка загрузки config.json: {e}")
    
    return default_config

# Глобальная конфигурация
cafe_config = load_config()
CAFE_NAME = cafe_config["name"]
CAFE_PHONE = cafe_config["phone"]
ADMIN_ID = int(cafe_config["admin_chat_id"])
MENU = dict(cafe_config["menu"])

# ТВОИ Environment Variables из Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")  # ← Уже добавлено в Render!
WEBAPP_PORT = int(os.getenv('PORT', 10000))

# ========================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
storage = RedisStorage.from_url(REDIS_URL)  # ← Работает с твоим REDIS_URL!
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_confirmation = State()

# ========================================
def get_moscow_time() -> datetime:
    return datetime.now(MSK_TZ)

def is_cafe_open() -> bool:
    return WORK_START <= get_moscow_time().hour < WORK_END

def get_work_status() -> str:
    msk_hour = get_moscow_time().hour
    if is_cafe_open():
        return f"🟢 <b>Открыто</b> (ещё {WORK_END-msk_hour} ч.)"
    return f"🔴 <b>Закрыто</b>\n🕐 Открываемся: {WORK_START}:00 (МСК)"

def create_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text=drink)] for drink in MENU.keys()]
    buttons.append([
        KeyboardButton(text="📞 Позвонить"), 
        KeyboardButton(text="⏰ Часы работы")
    ])
    return ReplyKeyboardMarkup(
        keyboard=buttons, 
        resize_keyboard=True
    )

def create_info_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Позвонить"), KeyboardButton(text="⏰ Часы работы")]
        ],
        resize_keyboard=True
    )

def create_quantity_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            ["1️⃣", "2️⃣", "3️⃣"],
            ["4️⃣", "5️⃣", "🔙 Отмена"]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def create_confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            ["✅ Подтвердить", "📝 Меню"]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_closed_message() -> str:
    menu_text = "• " + " | ".join([f"<b>{drink}</b> {price}₽" for drink, price in MENU.items()])
    return (
        f"🔒 <b>{CAFE_NAME} сейчас закрыто!</b>\n\n"
        f"⏰ {get_work_status()}\n\n"
        f"☕ <b>Наше меню:</b>\n"
        f"{menu_text}\n\n"
        f"📞 <b>Связаться:</b>\n<code>{CAFE_PHONE}</code>\n\n"
        f"✨ <i>До скорой встречи!</i>"
    )

async def get_redis_client() -> redis.Redis:
    """Глобальный Redis клиент"""
    return redis.from_url(REDIS_URL)

# ========================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    msk_time = get_moscow_time().strftime("%H:%M")
    logger.info(f"👤 /start от {user_id} | MSK: {msk_time}")
    
    if is_cafe_open():
        await message.answer(
            f"<b>{CAFE_NAME}</b>\n\n"
            f"🕐 <i>Московское время: {msk_time}</i>\n"
            f"🏪 {get_work_status()}\n\n"
            f"☕ <b>Выберите напиток:</b>",
            reply_markup=create_menu_keyboard()
        )
    else:
        await message.answer(get_closed_message(), reply_markup=create_info_keyboard())

@router.message(F.text.in_(set(MENU.keys())))
async def drink_selected(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"🥤 {message.text} от {user_id}")
    
    if not is_cafe_open():
        await message.answer(get_closed_message(), reply_markup=create_info_keyboard())
        return
    
    # Rate limiting через Redis
    r_client = await get_redis_client()
    last_order = await r_client.get(f"rate_limit:{user_id}")
    if last_order and time.time() - float(last_order) < 300:
        await message.answer(
            "⏳ Подождите 5 минут перед новым заказом", 
            reply_markup=create_menu_keyboard()
        )
        await r_client.close()
        return
    
    await r_client.setex(f"rate_limit:{user_id}", 300, time.time())
    await r_client.close()
    
    drink = message.text
    price = MENU[drink]
    
    await state.set_state(OrderStates.waiting_for_quantity)
    await state.set_data({"drink": drink, "price": price})
    
    await message.answer(
        f"🥤 <b>{drink}</b>\n"
        f"💰 <b>{price} ₽</b>\n\n"
        f"📝 <b>Сколько порций?</b>",
        reply_markup=create_quantity_keyboard()
    )

@router.message(StateFilter(OrderStates.waiting_for_quantity))
async def process_quantity(message: Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer(
            "❌ Заказ отменён", 
            reply_markup=create_menu_keyboard() if is_cafe_open() else create_info_keyboard()
        )
        return
    
    try:
        quantity = int(message.text[0])  # 1️⃣ → 1
        if 1 <= quantity <= 5:
            data = await state.get_data()
            drink, price = data["drink"], data["price"]
            total = price * quantity
            
            await state.set_state(OrderStates.waiting_for_confirmation)
            await state.update_data(quantity=quantity, total=total)
            
            await message.answer(
                f"🥤 <b>{drink}</b> × {quantity}\n"
                f"💰 Итого: <b>{total} ₽</b>\n\n"
                f"✅ Правильно?",
                reply_markup=create_confirm_keyboard()
            )
        else:
            await message.answer("❌ Выберите от 1 до 5", reply_markup=create_quantity_keyboard())
    except ValueError:
        await message.answer("❌ Нажмите на кнопку", reply_markup=create_quantity_keyboard())

@router.message(StateFilter(OrderStates.waiting_for_confirmation))
async def process_confirmation(message: Message, state: FSMContext):
    if message.text == "✅ Подтвердить":
        data = await state.get_data()
        drink = data["drink"]
        quantity = data["quantity"]
        total = data["total"]
        
        # Сохраняем заказ в Redis
        r_client = await get_redis_client()
        order_id = f"order:{int(time.time())}:{message.from_user.id}"
        order_data = {
            "user_id": message.from_user.id,
            "username": message.from_user.username or "N/A",
            "drink": drink,
            "quantity": quantity,
            "total": total,
            "timestamp": datetime.now().isoformat()
        }
        await r_client.hset(order_id, mapping=order_data)
        await r_client.expire(order_id, 86400)  # 24 часа
        
        # Статистика заказов
        await r_client.incr("stats:total_orders")
        await r_client.incr(f"stats:drink:{drink}")
        await r_client.close()
        
        # Уведомление админу
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Новый заказ #{order_id.split(':')[-1]}</b>\n\n"
            f"👤 <code>{message.from_user.id}</code>\n"
            f"🥤 {drink} × {quantity}\n"
            f"💰 {total}₽\n"
            f"📅 {get_moscow_time().strftime('%H:%M')}"
        )
        
        await message.answer(
            f"🎉 <b>Заказ #{order_id.split(':')[-1]} принят!</b>\n\n"
            f"🥤 {drink} × {quantity}\n"
            f"💰 {total}₽\n\n"
            f"📞 {CAFE_PHONE}\n⏳ Готовим!",
            reply_markup=create_menu_keyboard()
        )
        await state.clear()
        
    elif message.text == "📝 Меню":
        await state.clear()
        await message.answer("☕ Меню:", reply_markup=create_menu_keyboard())
    
    else:
        await message.answer("❌ Нажмите кнопку", reply_markup=create_confirm_keyboard())

@router.message(F.text == "📞 Позвонить")
async def call_phone(message: Message):
    await message.answer(f"📞 Звоните: <code>{CAFE_PHONE}</code>")

@router.message(F.text == "⏰ Часы работы")
async def show_hours(message: Message):
    await message.answer(f"🏪 {get_work_status()}\n📞 {CAFE_PHONE}")

@router.message(Command("stats"))
async def stats_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    r_client = await get_redis_client()
    total_orders = await r_client.get("stats:total_orders") or 0
    drink_stats = {}
    
    for drink in MENU.keys():
        count = await r_client.get(f"stats:drink:{drink}")
        drink_stats[drink] = int(count) if count else 0
    
    await r_client.close()
    
    stats_text = f"📊 <b>Статистика заказов</b>\n\n"
    stats_text += f"Всего заказов: <b>{total_orders}</b>\n\n"
    for drink, count in sorted(drink_stats.items(), key=lambda x: x[1], reverse=True):
        stats_text += f"{drink}: {count}\n"
    
    await message.answer(stats_text)

# ========================================
async def main() -> None:
    """Основная функция запуска"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден в Environment Variables!")
        return
    if not REDIS_URL:
        logger.error("❌ REDIS_URL не найден в Environment Variables!")
        return
        
    logger.info("🚀 Запуск бота...")
    logger.info(f"☕ Кафе: {CAFE_NAME}")
    logger.info(f"⏰ Рабочие часы: {WORK_START}:00-{WORK_END}:00 MSK")
    logger.info(f"📡 Redis: {REDIS_URL[:30]}...")
    
    # Тест Redis подключения
    try:
        r_test = await get_redis_client()
        await r_test.ping()
        await r_test.close()
        logger.info("✅ Redis подключён!")
    except Exception as e:
        logger.error(f"❌ Redis ошибка: {e}")
        return
    
    try:
        async with bot:
            await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await storage.close()
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
