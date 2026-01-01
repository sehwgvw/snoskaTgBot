import asyncio
import io
import uuid
import sys
import logging
import random
import os
import tempfile
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from telethon import TelegramClient

from config import (
    BOT_TOKEN, ADMIN_ID, API_ID, API_HASH, FILES,
    load_json, save_json, cfg, rm
)
from tasks import send_web, send_mail, send_session

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)

# --- СОСТОЯНИЯ ---
class Form(StatesGroup):
    auth = State()      # Ввод ключа
    target = State()    # Ввод цели
    photo = State()     # Загрузка фото
    # Настройки
    set_web = State()
    set_sess = State()
    set_mail = State()
    # Подписки
    buy_subscription = State()
    payment_method = State()
    confirm_payment = State()
    # Админ
    add_admin = State()
    remove_admin = State()
    create_mirror = State()
    edit_prices = State()
    edit_texts = State()
    edit_payments = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# --- УТИЛИТЫ ---
def check_access(uid):
    if uid == ADMIN_ID: return True
    if uid in cfg.get_admins(): return True
    return cfg.check_subscription(uid)

def get_bar(curr, total):
    if total <= 0: return ""
    pct = int((curr / total) * 100)
    fill = int(pct // 10)
    bar = '💖' * fill + '🤍' * (10 - fill)
    return f"[{bar}] {pct}%"

async def safe_edit(msg, text, kb=None):
    try: await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest: pass
    except: await msg.answer(text, reply_markup=kb, parse_mode="HTML")

def kb_main(uid):
    btns = [
        [InlineKeyboardButton(text="🌸 Наказать Бяку", callback_data="atk")],
        [InlineKeyboardButton(text="💎 Ресурсы", callback_data="res"), 
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📅 Подписка", callback_data="subscription"),
         InlineKeyboardButton(text="🪞 Зеркала", callback_data="mirrors")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")]
    ]
    if uid == ADMIN_ID or uid in cfg.get_admins():
        btns.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def generate_invoice_id():
    return f"INV-{uuid.uuid4().hex[:8].upper()}"

async def generate_qr_file(text):
    """Генерирует QR-код и сохраняет во временный файл"""
    try:
        import qrcode
        from PIL import Image
        
        qr = qrcode.make(text)
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            qr.save(tmp.name)
            return tmp.name
    except ImportError:
        logging.warning("Pillow или qrcode не установлены. QR-коды отключены.")
        return None
    except Exception as e:
        logging.error(f"Ошибка генерации QR: {e}")
        return None

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---
@router.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    uid = m.from_user.id
    
    if check_access(uid):
        s = cfg.get_settings()
        welcome_text = cfg.get_text("start", name=m.from_user.first_name)
        
        if s['photo_id']:
            await m.answer_photo(s['photo_id'], caption=welcome_text, reply_markup=kb_main(uid), parse_mode="HTML")
        else:
            await m.answer(welcome_text, reply_markup=kb_main(uid), parse_mode="HTML")
    else:
        await m.answer(cfg.get_text("no_subscription"), parse_mode="HTML")
        await show_subscription_menu(m)

@router.message(Form.auth)
async def auth_check(m: Message, state: FSMContext):
    keys = load_json(FILES['keys'], [])
    if m.text.strip() in keys:
        keys.remove(m.text.strip())
        save_json(FILES['keys'], keys)
        
        users = load_json(FILES['users'], [])
        users.append(m.from_user.id)
        save_json(FILES['users'], users)
        
        await m.answer("✅ Ключ принят! Привет, Хозяин!")
        await start(m, state)
    else:
        await m.answer("❌ Неверный ключ.")

# --- ПОДПИСКИ ---
@router.callback_query(F.data == "subscription")
async def subscription_info(c: CallbackQuery):
    uid = c.from_user.id
    info = cfg.get_subscription_info(uid)
    text = cfg.get_text("subscription_info", **info)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    
    await safe_edit(c.message, text, kb)

@router.callback_query(F.data == "buy_subscription")
async def buy_subscription_menu(c: CallbackQuery):
    prices = cfg.get_prices()
    kb_buttons = []
    
    for sub_id, sub_info in prices.get("subscriptions", {}).items():
        rub_price = sub_info.get("price", 0)
        label = sub_info.get("label", sub_id)
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"{label} - {rub_price}₽", 
                callback_data=f"sub_{sub_id}"
            )
        ])
    
    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="home")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    await safe_edit(c.message, cfg.get_text("buy_subscription"), kb)

@router.callback_query(F.data.startswith("sub_"))
async def select_payment_method(c: CallbackQuery, state: FSMContext):
    sub_id = c.data.split("_")[1]
    prices = cfg.get_prices()
    sub_info = prices.get("subscriptions", {}).get(sub_id)
    
    if not sub_info:
        await c.answer("❌ Подписка не найдена")
        return
    
    await state.update_data(sub_id=sub_id, sub_info=sub_info)
    
    payment_methods = prices.get("payment_methods", {})
    kb_buttons = []
    
    for method_id, method_info in payment_methods.items():
        if method_info.get("enabled", False):
            kb_buttons.append([
                InlineKeyboardButton(
                    text=method_info.get("name", method_id),
                    callback_data=f"pay_{method_id}"
                )
            ])
    
    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    await safe_edit(c.message, cfg.get_text("payment_methods"), kb)

@router.callback_query(F.data.startswith("pay_"))
async def show_payment_details(c: CallbackQuery, state: FSMContext):
    method_id = c.data.split("_")[1]
    data = await state.get_data()
    sub_info = data.get('sub_info', {})
    
    rub_price = sub_info.get("price", 0)
    crypto_price = sub_info.get("crypto_price", 0)
    crypto_currency = sub_info.get("crypto_currency", "TON")
    days = sub_info.get("days", 1)
    label = sub_info.get("label", "")
    
    payment_details = cfg.get_payment_details()
    method_details = payment_details.get(method_id, {})
    
    invoice_id = generate_invoice_id()
    await state.update_data(invoice_id=invoice_id, payment_method=method_id)
    
    text = f"💳 <b>Оплата подписки</b>\n\n"
    text += f"📅 Подписка: {label}\n"
    text += f"📆 Срок: {days} дней\n"
    text += f"🆔 Номер счета: {invoice_id}\n\n"
    
    if method_id == "crypto":
        wallet = method_details.get("wallet", "")
        usdt_wallet = method_details.get("usdt_wallet", "")
        currency = method_details.get("currency", "TON")
        
        text += f"<b>CryptoBot ({crypto_currency}):</b>\n"
        text += f"Кошелек TON: <code>{wallet}</code>\n"
        if usdt_wallet:
            text += f"Кошелек USDT-TRC20: <code>{usdt_wallet}</code>\n"
        text += f"Сумма: {crypto_price} {crypto_currency}\n"
        text += f"(≈ {rub_price}₽)\n\n"
        text += "После оплаты нажмите 'Подтвердить оплату'"
        
        # Генерируем QR код для TON
        qr_text_ton = f"ton://transfer/{wallet}?amount={crypto_price * 1000000000}"
        qr_file = await generate_qr_file(qr_text_ton)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data="confirm_payment")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")]
        ])
        
        if qr_file:
            try:
                await c.message.answer_photo(
                    photo=FSInputFile(qr_file),
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                # Удаляем временный файл после отправки
                os.unlink(qr_file)
            except Exception as e:
                logging.error(f"Ошибка отправки QR: {e}")
                text += f"\n\n⚠️ Не удалось отправить QR-код. Переведите на кошелек вручную."
                await safe_edit(c.message, text, kb)
        else:
            text += f"\n\n⚠️ Не удалось сгенерировать QR-код. Переведите на кошелек вручную."
            await safe_edit(c.message, text, kb)
        
    elif method_id == "card_rf":
        card = method_details.get("number", "")
        bank = method_details.get("bank", "")
        text += f"<b>Карта РФ (рубли):</b>\n"
        text += f"Банк: {bank}\n"
        text += f"Номер карты: <code>{card}</code>\n"
        text += f"Сумма: {rub_price}₽\n"
        text += f"Комментарий: {invoice_id}\n\n"
        text += "После оплаты нажмите 'Подтвердить оплату'"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data="confirm_payment")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")]
        ])
        
        await safe_edit(c.message, text, kb)
        
    elif method_id == "sbp":
        phone = method_details.get("phone", "")
        bank = method_details.get("bank", "")
        text += f"<b>СБП (рубли):</b>\n"
        text += f"Банк: {bank}\n"
        text += f"Телефон: <code>{phone}</code>\n"
        text += f"Сумма: {rub_price}₽\n"
        text += f"Комментарий: {invoice_id}\n\n"
        text += "После оплаты нажмите 'Подтвердить оплату'"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data="confirm_payment")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")]
        ])
        
        await safe_edit(c.message, text, kb)
    
    await c.answer()

@router.callback_query(F.data == "confirm_payment")
async def confirm_payment(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = c.from_user.id
    sub_id = data.get('sub_id')
    sub_info = data.get('sub_info', {})
    invoice_id = data.get('invoice_id')
    payment_method = data.get('payment_method')
    
    days = sub_info.get("days", 1)
    
    # Добавляем подписку
    cfg.set_subscription(user_id, days)
    
    # Определяем сумму оплаты
    if payment_method == "crypto":
        amount = sub_info.get("crypto_price", 0)
        currency = sub_info.get("crypto_currency", "TON")
    else:
        amount = sub_info.get("price", 0)
        currency = "RUB"
    
    # Сохраняем информацию о платеже
    payments = load_json(FILES['payments'], {})
    if "transactions" not in payments:
        payments["transactions"] = []
    
    payments["transactions"].append({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "amount": amount,
        "currency": currency,
        "payment_method": payment_method,
        "days": days,
        "date": datetime.now().isoformat(),
        "status": "completed"
    })
    
    save_json(FILES['payments'], payments)
    
    # Уведомляем админов
    admins = cfg.get_admins()
    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Новый платеж!</b>\n\n"
                f"👤 Пользователь: {c.from_user.full_name} (ID: {user_id})\n"
                f"💳 Способ: {payment_method}\n"
                f"💰 Сумма: {amount} {currency}\n"
                f"📅 Подписка: {sub_info.get('label', '')}\n"
                f"🆔 Счет: {invoice_id}",
                parse_mode="HTML"
            )
        except:
            pass
    
    await c.message.answer(
        f"✅ <b>Подписка активирована!</b>\n\n"
        f"Срок действия: {days} дней\n"
        f"Теперь вы можете использовать все функции бота.",
        parse_mode="HTML"
    )
    
    await start(c.message, state)
    await c.answer()

# --- ЗЕРКАЛА ---
@router.callback_query(F.data == "mirrors")
async def show_mirrors(c: CallbackQuery):
    mirrors = cfg.get_mirrors()
    
    if not mirrors:
        text = "🪞 <b>Зеркала</b>\n\nНа данный момент нет доступных зеркал."
    else:
        text = "🪞 <b>Доступные зеркала:</b>\n\n"
        for i, mirror in enumerate(mirrors, 1):
            text += f"{i}. @{mirror.get('username', 'Unknown')}\n"
            text += f"   Статус: {mirror.get('status', 'active')}\n"
            text += f"   Создано: {mirror.get('created', '')}\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data="check_mirrors")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    
    await safe_edit(c.message, text, kb)

# --- НАСТРОЙКИ ---
@router.callback_query(F.data == "settings")
async def sett_menu(c: CallbackQuery):
    s = cfg.get_settings()
    txt = (f"⚙️ <b>Параметры Атаки:</b>\n"
           f"Нажми на кнопку, чтобы изменить значение.\n\n"
           f"🌐 Web-жалобы: {s['web_count']}\n"
           f"🏠 Сессии: {s['session_count']}\n"
           f"📧 Письма: {s['mail_count']}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изм. Web", callback_data="input_web")],
        [InlineKeyboardButton(text="✏️ Изм. Сессии", callback_data="input_sess")],
        [InlineKeyboardButton(text="✏️ Изм. Почты", callback_data="input_mail")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    await safe_edit(c.message, txt, kb)

# --- РЕСУРСЫ ---
@router.callback_query(F.data == "res")
async def res_menu(c: CallbackQuery):
    rm.reload()
    txt = (f"💎 <b>Ресурсы:</b>\n"
           f"🌐 Прокси: {len(rm.proxies)}\n"
           f"🏠 Сессии: {len(rm.sessions)}\n"
           f"📧 Почты: {len(rm.mails)}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Проверить Прокси", callback_data="val_prox")],
        [InlineKeyboardButton(text="✅ Проверить Сессии", callback_data="val_sess")],
        [InlineKeyboardButton(text="✅ Проверить Почты", callback_data="val_mail")],
        [InlineKeyboardButton(text="📧 Информация о почтах", callback_data="mail_info")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    await safe_edit(c.message, txt, kb)

# --- АДМИН-ПАНЕЛЬ ---
@router.callback_query(F.data == "admin")
async def admin_panel(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление админами", callback_data="manage_admins")],
        [InlineKeyboardButton(text="💰 Управление ценами", callback_data="manage_prices")],
        [InlineKeyboardButton(text="💳 Реквизиты оплаты", callback_data="manage_payments")],
        [InlineKeyboardButton(text="📝 Текста бота", callback_data="manage_texts")],
        [InlineKeyboardButton(text="🪞 Создать зеркало", callback_data="create_mirror")],
        [InlineKeyboardButton(text="🔑 Создать ключ доступа", callback_data="mk_key")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    
    await safe_edit(c.message, cfg.get_text("admin_panel"), kb)

@router.callback_query(F.data == "mk_key")
async def make_key(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    k = str(uuid.uuid4())[:8].upper()
    keys = load_json(FILES['keys'], [])
    keys.append(k)
    save_json(FILES['keys'], keys)
    
    await c.message.answer(f"🔑 <b>Создан ключ доступа</b>\n\nКлюч: <code>{k}</code>\n\n<i>Ключ можно использовать один раз для доступа к боту.</i>", parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "manage_admins")
async def manage_admins(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ Только главный админ может управлять админами!")
        return
    
    admins = cfg.get_admins()
    text = "👥 <b>Управление админами</b>\n\n"
    text += f"Всего админов: {len(admins)}\n\n"
    
    for i, admin_id in enumerate(admins, 1):
        try:
            user = await bot.get_chat(admin_id)
            name = user.full_name
            role = "👑 Главный" if admin_id == ADMIN_ID else "👨‍💼 Админ"
            text += f"{i}. {name} (ID: {admin_id}) - {role}\n"
        except:
            text += f"{i}. ID: {admin_id}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin_btn"),
         InlineKeyboardButton(text="➖ Удалить админа", callback_data="remove_admin_btn")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin")]
    ])
    
    await safe_edit(c.message, text, kb)

@router.callback_query(F.data == "add_admin_btn")
async def add_admin_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ Доступ запрещен!")
        return
    
    await c.message.answer("Введите ID пользователя для добавления в админы:")
    await state.set_state(Form.add_admin)
    await c.answer()

@router.message(Form.add_admin)
async def add_admin_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    
    try:
        admin_id = int(m.text.strip())
        if cfg.add_admin(admin_id):
            await m.answer(f"✅ Пользователь {admin_id} добавлен в админы!")
        else:
            await m.answer(f"⚠️ Пользователь {admin_id} уже является админом.")
    except ValueError:
        await m.answer("❌ Неверный формат ID. Введите числовой ID.")
    
    await state.clear()

@router.callback_query(F.data == "remove_admin_btn")
async def remove_admin_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ Доступ запрещен!")
        return
    
    await c.message.answer("Введите ID админа для удаления:")
    await state.set_state(Form.remove_admin)
    await c.answer()

@router.message(Form.remove_admin)
async def remove_admin_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    
    try:
        admin_id = int(m.text.strip())
        if cfg.remove_admin(admin_id):
            await m.answer(f"✅ Админ {admin_id} удален!")
        else:
            await m.answer(f"❌ Нельзя удалить главного админа или админ не найден.")
    except ValueError:
        await m.answer("❌ Неверный формат ID.")
    
    await state.clear()

@router.callback_query(F.data == "create_mirror")
async def create_mirror_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    await c.message.answer(
        "🪞 <b>Создание зеркала</b>\n\n"
        "Отправьте данные в формате:\n"
        "<code>@username_bot ТОКЕН_БОТА</code>\n\n"
        "Пример:\n"
        "<code>@my_mirror_bot 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ</code>",
        parse_mode="HTML"
    )
    await state.set_state(Form.create_mirror)
    await c.answer()

@router.message(Form.create_mirror)
async def create_mirror_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID and m.from_user.id not in cfg.get_admins():
        return
    
    try:
        parts = m.text.strip().split()
        if len(parts) < 2:
            await m.answer("❌ Неверный формат. Пример: @username_bot ТОКЕН")
            return
        
        username = parts[0].replace("@", "")
        token = parts[1]
        
        mirror_data = {
            "username": username,
            "token": token,
            "created_by": m.from_user.id,
            "created": datetime.now().isoformat(),
            "status": "active"
        }
        
        cfg.add_mirror(mirror_data)
        
        await m.answer(
            f"✅ Зеркало создано!\n\n"
            f"Username: @{username}\n"
            f"Статус: активен\n\n"
            f"<i>Скопируйте этот код в нового бота:</i>\n"
            f"<code>python main.py --token {token}</code>",
            parse_mode="HTML"
        )
        
        # Уведомляем главного админа
        if m.from_user.id != ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🪞 <b>Создано новое зеркало</b>\n\n"
                    f"👤 Создал: {m.from_user.full_name}\n"
                    f"🤖 Бот: @{username}\n"
                    f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode="HTML"
                )
            except:
                pass
        
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "manage_prices")
async def manage_prices(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    prices = cfg.get_prices()
    text = "💰 <b>Управление ценами</b>\n\n"
    
    text += "<b>Подписки:</b>\n"
    for sub_id, sub_info in prices.get("subscriptions", {}).items():
        rub_price = sub_info.get("price", 0)
        crypto_price = sub_info.get("crypto_price", 0)
        crypto_currency = sub_info.get("crypto_currency", "TON")
        label = sub_info.get("label", sub_id)
        days = sub_info.get("days", 1)
        text += f"• {label}: {rub_price}₽ / {crypto_price} {crypto_currency} ({days} дней) [ID: {sub_id}]\n"
    
    text += f"\n<b>Зеркало:</b> {prices.get('mirror', {}).get('price', 0)}₽\n\n"
    
    text += "<b>Способы оплаты:</b>\n"
    for method_id, method_info in prices.get("payment_methods", {}).items():
        name = method_info.get("name", method_id)
        enabled = "✅ Вкл" if method_info.get("enabled", False) else "❌ Выкл"
        fee = method_info.get("fee", 0)
        text += f"• {name}: {enabled} (комиссия: {fee}₽)\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать цены", callback_data="edit_prices")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin")]
    ])
    
    await safe_edit(c.message, text, kb)

@router.callback_query(F.data == "edit_prices")
async def edit_prices_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    await c.message.answer(
        "✏️ <b>Редактирование цен</b>\n\n"
        "Отправьте новые цены в формате JSON.\n"
        "Пример:\n"
        "<code>{\"subscriptions\": {\"day\": {\"price\": 150, \"crypto_price\": 6, \"crypto_currency\": \"TON\", \"days\": 1, \"label\": \"1 день\"}}}</code>\n\n"
        "Будьте осторожны! Неправильный формат сломает систему.",
        parse_mode="HTML"
    )
    await state.set_state(Form.edit_prices)
    await c.answer()

@router.message(Form.edit_prices)
async def edit_prices_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID and m.from_user.id not in cfg.get_admins():
        return
    
    try:
        new_prices = json.loads(m.text.strip())
        cfg.update_prices(new_prices)
        await m.answer("✅ Цены успешно обновлены!")
    except json.JSONDecodeError:
        await m.answer("❌ Неверный формат JSON!")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "manage_payments")
async def manage_payments(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    payments = cfg.get_payment_details()
    text = "💳 <b>Реквизиты оплаты</b>\n\n"
    
    for method, details in payments.items():
        if method == "transactions":
            continue
        text += f"<b>{method.upper()}:</b>\n"
        for key, value in details.items():
            text += f"  {key}: {value}\n"
        text += "\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать реквизиты", callback_data="edit_payments")],
        [InlineKeyboardButton(text="📋 История платежей", callback_data="payment_history")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin")]
    ])
    
    await safe_edit(c.message, text, kb)

@router.callback_query(F.data == "edit_payments")
async def edit_payments_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    await c.message.answer(
        "✏️ <b>Редактирование реквизитов</b>\n\n"
        "Отправьте новые реквизиты в формате JSON.\n"
        "Пример для CryptoBot:\n"
        "<code>{\"crypto\": {\"wallet\": \"NEW_WALLET\", \"currency\": \"TON\", \"usdt_wallet\": \"NEW_USDT_WALLET\"}}</code>\n\n"
        "Будьте осторожны! Неправильный формат сломает платежи.",
        parse_mode="HTML"
    )
    await state.set_state(Form.edit_payments)
    await c.answer()

@router.message(Form.edit_payments)
async def edit_payments_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID and m.from_user.id not in cfg.get_admins():
        return
    
    try:
        new_details = json.loads(m.text.strip())
        cfg.update_payment_details(new_details)
        await m.answer("✅ Реквизиты успешно обновлены!")
    except json.JSONDecodeError:
        await m.answer("❌ Неверный формат JSON!")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "manage_texts")
async def manage_texts(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    texts = load_json(FILES['texts'], {})
    text = "📝 <b>Текста бота</b>\n\n"
    
    for key, value in list(texts.items())[:10]:  # Показываем первые 10
        preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
        text += f"• <b>{key}:</b> {preview}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текста", callback_data="edit_texts")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin")]
    ])
    
    await safe_edit(c.message, text, kb)

@router.callback_query(F.data == "edit_texts")
async def edit_texts_prompt(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    await c.message.answer(
        "✏️ <b>Редактирование текстов</b>\n\n"
        "Отправьте текста в формате:\n"
        "<code>КЛЮЧ: ТЕКСТ</code>\n\n"
        "Пример:\n"
        "<code>start: Новый текст приветствия</code>\n\n"
        "Доступные ключи: start, menu, subscription_info, no_subscription, buy_subscription, payment_methods, mirror_info, admin_panel",
        parse_mode="HTML"
    )
    await state.set_state(Form.edit_texts)
    await c.answer()

@router.message(Form.edit_texts)
async def edit_texts_execute(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID and m.from_user.id not in cfg.get_admins():
        return
    
    try:
        parts = m.text.strip().split(":", 1)
        if len(parts) != 2:
            await m.answer("❌ Неверный формат. Используйте: КЛЮЧ: ТЕКСТ")
            return
        
        key = parts[0].strip()
        value = parts[1].strip()
        
        cfg.update_text(key, value)
        await m.answer(f"✅ Текст '{key}' успешно обновлен!")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and c.from_user.id not in cfg.get_admins():
        await c.answer("❌ Нет доступа!")
        return
    
    rm.reload()
    admins = cfg.get_admins()
    payments = load_json(FILES['payments'], {})
    transactions = payments.get("transactions", [])
    
    total_income_rub = sum(t.get("amount", 0) for t in transactions if t.get("currency") == "RUB")
    total_income_crypto = sum(t.get("amount", 0) for t in transactions if t.get("currency") != "RUB")
    crypto_currency = transactions[0].get("crypto_currency", "TON") if transactions else "TON"
    
    active_users = len(load_json(FILES['users'], []))
    
    text = "📊 <b>Статистика системы</b>\n\n"
    text += f"👥 Всего пользователей: {active_users}\n"
    text += f"👑 Админов: {len(admins)}\n"
    text += f"💰 Общий доход (рубли): {total_income_rub}₽\n"
    text += f"💰 Общий доход (крипта): {total_income_crypto} {crypto_currency}\n"
    text += f"💳 Всего платежей: {len(transactions)}\n"
    text += f"🌐 Прокси: {len(rm.proxies)}\n"
    text += f"🏠 Сессий: {len(rm.sessions)}\n"
    text += f"📧 Почтовых аккаунтов: {len(rm.mails)}\n"
    text += f"🪞 Зеркал: {len(cfg.get_mirrors())}\n"
    text += f"🔑 Ключей доступа: {len(load_json(FILES['keys'], []))}\n"
    
    # Последние 5 платежей
    if transactions:
        text += "\n<b>Последние платежи:</b>\n"
        for t in transactions[-5:]:
            amount = t.get("amount", 0)
            currency = t.get("currency", "RUB")
            user_id = t.get("user_id", "Unknown")
            method = t.get("payment_method", "unknown")
            date = t.get("date", "").split("T")[0]
            text += f"• {user_id}: {amount} {currency} ({method}) - {date}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin")]
    ])
    
    await safe_edit(c.message, text, kb)

# --- ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ---
@router.callback_query(F.data.startswith("input_"))
async def input_ask(c: CallbackQuery, state: FSMContext):
    t = c.data.split("_")[1]
    if t == 'web': await state.set_state(Form.set_web)
    elif t == 'sess': await state.set_state(Form.set_sess)
    elif t == 'mail': await state.set_state(Form.set_mail)
    
    await c.message.answer("⌨️ Введи новое число, Хозяин:")
    await c.answer()

@router.message(Form.set_web)
async def set_w(m: Message, state: FSMContext):
    if m.text.isdigit():
        cfg.update_setting('web_count', m.text)
        await m.answer("✅ Web-жалобы обновлены!")
    await settings_menu(CallbackQuery(id='0', from_user=m.from_user, message=m, chat_instance='0'))

@router.message(Form.set_sess)
async def set_s(m: Message, state: FSMContext):
    if m.text.isdigit():
        cfg.update_setting('session_count', m.text)
        await m.answer("✅ Кол-во сессий обновлено!")
    await settings_menu(CallbackQuery(id='0', from_user=m.from_user, message=m, chat_instance='0'))

@router.message(Form.set_mail)
async def set_m(m: Message, state: FSMContext):
    if m.text.isdigit():
        cfg.update_setting('mail_count', m.text)
        await m.answer("✅ Кол-во писем обновлено!")
    await settings_menu(CallbackQuery(id='0', from_user=m.from_user, message=m, chat_instance='0'))

async def settings_menu(c: CallbackQuery):
    s = cfg.get_settings()
    txt = (f"⚙️ <b>Параметры Атаки:</b>\n"
           f"Нажми на кнопку, чтобы изменить значение.\n\n"
           f"🌐 Web-жалобы: {s['web_count']}\n"
           f"🏠 Сессии: {s['session_count']}\n"
           f"📧 Письма: {s['mail_count']}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изм. Web", callback_data="input_web")],
        [InlineKeyboardButton(text="✏️ Изм. Сессии", callback_data="input_sess")],
        [InlineKeyboardButton(text="✏️ Изм. Почты", callback_data="input_mail")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="home")]
    ])
    await safe_edit(c.message, txt, kb)

@router.callback_query(F.data.startswith("val_"))
async def validate(c: CallbackQuery):
    t = c.data.split("_")[1]
    msg = await c.message.answer("⏳ Начинаю проверку...")
    
    count = 0
    if t == 'prox': count = await rm.check_proxies()
    elif t == 'sess': count = await rm.check_sessions()
    elif t == 'mail': count = await rm.check_mails()
    
    await msg.edit_text(f"✅ Проверка завершена!\nЖивых: {count}")
    await res_menu(c)

@router.callback_query(F.data == "mail_info")
async def mail_info(c: CallbackQuery):
    info = rm.get_supported_emails_info()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к ресурсам", callback_data="res")]
    ])
    await safe_edit(c.message, info, kb)

# --- ФАЙЛЫ ---
@router.message(F.document)
async def doc_handler(m: Message):
    if not check_access(m.from_user.id): return
    n = m.document.file_name
    if n.endswith('.session'): 
        await bot.download(m.document, f"sessions/{n}")
        await m.answer("✅ Сессия загружена!")
    elif n in ['прокси.txt', 'proxies.txt']: 
        await bot.download(m.document, 'прокси.txt')
        await m.answer("✅ Прокси загружены!")
    elif n in ['mails.txt', 'emails.txt', 'почты.txt']: 
        await bot.download(m.document, 'mails.txt')
        await m.answer("✅ Почты загружены!")
    else:
        await m.answer("❌ Неподдерживаемый файл.")

@router.message(F.photo)
async def photo_handler(m: Message):
    if m.from_user.id == ADMIN_ID:
        cfg.update_setting('photo_id', m.photo[-1].file_id)
        await m.answer("📸 Логотип установлен!")

# --- АТАКА ---
@router.callback_query(F.data == "atk")
async def atk_1(c: CallbackQuery, state: FSMContext):
    if not check_access(c.from_user.id):
        await c.answer("❌ Нет доступа! Купите подписку.")
        return
    
    await c.message.answer("🎯 Введи цель (Username или ID):")
    await state.set_state(Form.target)
    await c.answer()

@router.message(Form.target)
async def atk_2(m: Message, state: FSMContext):
    if not check_access(m.from_user.id):
        return
    
    await state.update_data(target=m.text.replace("@", "").strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Прикрепить фото", callback_data="y_ph"), InlineKeyboardButton(text="⏩ Без фото", callback_data="n_ph")]])
    await m.answer("Нужен скриншот?", reply_markup=kb)

@router.callback_query(F.data == "y_ph")
async def atk_3_y(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Кидай фото!")
    await state.set_state(Form.photo)
    await c.answer()

@router.message(Form.photo, F.photo)
async def atk_4(m: Message, state: FSMContext):
    f = await bot.get_file(m.photo[-1].file_id)
    b = io.BytesIO()
    await bot.download_file(f.file_path, b)
    await state.update_data(photo=b.getvalue())
    await ask_mode(m)

@router.callback_query(F.data == "n_ph")
async def atk_3_n(c: CallbackQuery, state: FSMContext):
    await state.update_data(photo=None)
    await ask_mode(c.message)
    await c.answer()

async def ask_mode(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 С Прокси", callback_data="run_p"), InlineKeyboardButton(text="🚀 Напрямую", callback_data="run_d")]
    ])
    await m.answer("Выбери режим:", reply_markup=kb)

@router.callback_query(F.data.startswith("run_"))
async def run_atk(c: CallbackQuery, state: FSMContext):
    if not check_access(c.from_user.id):
        await c.answer("❌ Нет доступа! Купите подписку.")
        return
    
    data = await state.get_data()
    target = data['target']
    photo = data.get('photo')
    use_proxy = c.data == "run_p"
    
    rm.reload()
    s = cfg.get_settings()
    
    msg = await c.message.answer("🌸 Подготовка... Ищу цель...")
    
    # OSINT функция
    async def get_osint(target):
        sessions = rm.sessions
        if not sessions: return None, None
        try:
            c = TelegramClient(f"sessions/{sessions[0]}", API_ID, API_HASH)
            await c.connect()
            e = await c.get_entity(target)
            uid, uname = e.id, e.username or target
            await c.disconnect()
            return uid, uname
        except: return None, None
    
    uid, uname = await get_osint(target)
    if not uid: uid, uname = target, target
    
    tasks = []
    
    p_list = rm.proxies if use_proxy else [None] * 50
    if use_proxy and not p_list: 
        await msg.edit_text("❌ Нет прокси!")
        return
    
    web_limit = s['web_count']
    sess_limit = s['session_count']
    mail_limit = s['mail_count']
    
    for i in range(web_limit):
        p = random.choice(p_list) if use_proxy else None
        t = rm.get_text(uname, uid)
        tasks.append(send_web(p, uname, t))
        
    for sess in rm.sessions[:sess_limit]:
        t = rm.get_text(uname, uid)
        tasks.append(send_session(sess, uname, t))
        
    for mail in rm.mails[:mail_limit]:
        t = rm.get_text(uname, uid)
        tasks.append(send_mail(mail, uname, t, photo))
        
    total = len(tasks)
    if total == 0: 
        await msg.edit_text("❌ Нет ресурсов!")
        return
    
    await msg.edit_text(f"🚀 АТАКА: {uname}\nВсего жалоб: {total}")
    
    done, ok = 0, 0
    for i in range(0, total, 20):
        chunk = tasks[i:i+20]
        res = await asyncio.gather(*chunk)
        done += len(chunk)
        ok += res.count(True)
        
        try: await msg.edit_text(f"💣 АТАКА...\nЦель: {uname}\n{get_bar(done, total)}\nУспешно: {ok}")
        except: pass
        await asyncio.sleep(0.2)
        
    await msg.answer(f"🏁 <b>ГОТОВО!</b>\nЦель: {uname}\nУспешно: {ok}", parse_mode="HTML")
    await state.clear()
    await c.answer()

@router.callback_query(F.data == "home")
async def go_home(c: CallbackQuery):
    await c.message.delete()
    uid = c.from_user.id
    s = cfg.get_settings()
    
    if check_access(uid):
        welcome_text = cfg.get_text("menu")
        if s['photo_id']:
            await c.message.answer_photo(s['photo_id'], caption=welcome_text, reply_markup=kb_main(uid), parse_mode="HTML")
        else:
            await c.message.answer(welcome_text, reply_markup=kb_main(uid), parse_mode="HTML")
    else:
        await c.message.answer(cfg.get_text("no_subscription"), parse_mode="HTML")
        await show_subscription_menu(c.message)
    
    await c.answer()

async def show_subscription_menu(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔑 Ввести ключ", callback_data="enter_key")]
    ])
    await m.answer("Выберите действие:", reply_markup=kb)

@router.callback_query(F.data == "enter_key")
async def enter_key(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ключ доступа:")
    await state.set_state(Form.auth)
    await c.answer()

async def main():
    dp.include_router(router)
    rm.reload()
    print(f"🤖 Бот запущен! Админ ID: {ADMIN_ID}")
    print(f"⚠️ Для QR-кодов установите: pip install pillow qrcode")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())