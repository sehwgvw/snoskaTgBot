import os
import json
import random
import re
import aiohttp
import asyncio
import aiosmtplib
from telethon import TelegramClient
from datetime import datetime, timedelta

# --- КОНСТАНТЫ ---
BOT_TOKEN = "7811232534:AAHnmI0H3GTNQ5bc1OWgwiRVBSIajP8Wv1M" 
ADMIN_ID = 7544069555
API_ID = 27720808
API_HASH = "f404d028ebe5d98725cd21ea5537d015"

FILES = {
    'settings': 'settings.json',
    'users': 'users.json',
    'keys': 'keys.json',
    'proxies': 'прокси.txt',
    'mails': 'mails.txt',
    'subscriptions': 'subscriptions.json',
    'payments': 'payments.json',
    'mirrors': 'mirrors.json',
    'admins': 'admins.json',
    'prices': 'prices.json',
    'texts': 'bot_texts.json'
}

# --- МЕНЕДЖЕР ДАННЫХ ---
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

class ConfigManager:
    def __init__(self):
        self._check_files()
        
    def _check_files(self):
        for d in ['sessions', 'texts', 'invoices']: os.makedirs(d, exist_ok=True)
        # Дефолтный текст
        if not os.listdir('texts'):
            with open('texts/report.txt', 'w', encoding='utf-8') as f:
                f.write("Reporting user @{username} (ID: {id}) for severe violations.")
        
        # Дефолтные текста бота
        if not os.path.exists(FILES['texts']):
            default_texts = {
                "start": "👋 Привет, {name}! Я бот для защиты от нарушителей.\n\n💎 <b>Доступные функции:</b>\n• Отправка жалоб на нарушителей\n• Работа через прокси\n• Поддержка множества почт\n\n🔐 Для доступа нужна подписка или ключ.",
                "menu": "🎮 <b>Главное меню</b>\n\nВыбери действие:",
                "subscription_info": "📅 <b>Информация о подписке</b>\n\nСтатус: {status}\nДействует до: {expiry}\nОсталось дней: {days_left}",
                "no_subscription": "❌ <b>Нет активной подписки!</b>\n\nДля доступа к функциям бота необходимо приобрести подписку.",
                "buy_subscription": "💳 <b>Приобретение подписки</b>\n\nВыберите срок подписки:",
                "payment_methods": "💳 <b>Способы оплаты</b>\n\nВыберите удобный способ оплаты:",
                "mirror_info": "🪞 <b>Платные зеркала</b>\n\nЕсли основной бот заблокирован, вы можете использовать одно из наших зеркал.",
                "admin_panel": "👑 <b>Админ-панель</b>\n\nВыберите действие:"
            }
            save_json(FILES['texts'], default_texts)
        
        # Дефолтные цены
        if not os.path.exists(FILES['prices']):
            default_prices = {
                "subscriptions": {
                    "day": {"price": 100, "days": 1, "label": "1 день", "crypto_price": 4, "crypto_currency": "TON"},
                    "week": {"price": 500, "days": 7, "label": "1 неделя", "crypto_price": 20, "crypto_currency": "TON"},
                    "month": {"price": 1500, "days": 30, "label": "1 месяц", "crypto_price": 60, "crypto_currency": "TON"},
                    "3months": {"price": 4000, "days": 90, "label": "3 месяца", "crypto_price": 160, "crypto_currency": "TON"},
                    "year": {"price": 12000, "days": 365, "label": "1 год", "crypto_price": 480, "crypto_currency": "TON"}
                },
                "mirror": {"price": 5000, "label": "Платный доступ к зеркалу"},
                "payment_methods": {
                    "crypto": {"name": "CryptoBot (TON/USDT)", "fee": 0, "enabled": True},
                    "card_rf": {"name": "Карта РФ (рубли)", "fee": 50, "enabled": True},
                    "sbp": {"name": "СБП (рубли)", "fee": 0, "enabled": True}
                }
            }
            save_json(FILES['prices'], default_prices)
        
        # Дефолтные реквизиты
        if not os.path.exists('payments.json'):
            default_payments = {
                "crypto": {"wallet": "U1234567890", "currency": "TON", "usdt_wallet": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"},
                "card_rf": {"number": "2202 1234 5678 9010", "bank": "Тинькофф"},
                "sbp": {"phone": "+79991234567", "bank": "Сбербанк"}
            }
            save_json(FILES['payments'], default_payments)
        
        # Дефолтные админы
        if not os.path.exists(FILES['admins']):
            save_json(FILES['admins'], [ADMIN_ID])
        
        # Дефолтные зеркала
        if not os.path.exists(FILES['mirrors']):
            save_json(FILES['mirrors'], [])

    def get_settings(self):
        defaults = {'web_count': 50, 'session_count': 1, 'mail_count': 1, 'photo_id': None}
        data = load_json(FILES['settings'], defaults)
        for k, v in defaults.items():
            if k not in data: data[k] = v
        return data

    def update_setting(self, key, value):
        s = self.get_settings()
        s[key] = int(value) if str(value).isdigit() else value
        save_json(FILES['settings'], s)
    
    def get_text(self, key, **kwargs):
        texts = load_json(FILES['texts'], {})
        text = texts.get(key, key)
        for k, v in kwargs.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text
    
    def update_text(self, key, value):
        texts = load_json(FILES['texts'], {})
        texts[key] = value
        save_json(FILES['texts'], texts)
    
    def get_prices(self):
        return load_json(FILES['prices'], {})
    
    def update_prices(self, new_prices):
        save_json(FILES['prices'], new_prices)
    
    def get_payment_details(self):
        return load_json(FILES['payments'], {})
    
    def update_payment_details(self, details):
        save_json(FILES['payments'], details)
    
    def get_mirrors(self):
        return load_json(FILES['mirrors'], [])
    
    def add_mirror(self, mirror_data):
        mirrors = self.get_mirrors()
        mirrors.append(mirror_data)
        save_json(FILES['mirrors'], mirrors)
    
    def get_admins(self):
        return load_json(FILES['admins'], [ADMIN_ID])
    
    def add_admin(self, admin_id):
        admins = self.get_admins()
        if admin_id not in admins:
            admins.append(admin_id)
            save_json(FILES['admins'], admins)
            return True
        return False
    
    def remove_admin(self, admin_id):
        admins = self.get_admins()
        if admin_id in admins and admin_id != ADMIN_ID:
            admins.remove(admin_id)
            save_json(FILES['admins'], admins)
            return True
        return False
    
    def get_subscription(self, user_id):
        subscriptions = load_json(FILES['subscriptions'], {})
        return subscriptions.get(str(user_id))
    
    def set_subscription(self, user_id, days):
        subscriptions = load_json(FILES['subscriptions'], {})
        expiry = datetime.now() + timedelta(days=days)
        subscriptions[str(user_id)] = {
            "expiry": expiry.isoformat(),
            "activated": datetime.now().isoformat(),
            "days": days
        }
        save_json(FILES['subscriptions'], subscriptions)
    
    def check_subscription(self, user_id):
        if user_id == ADMIN_ID:
            return True
        if user_id in cfg.get_admins():
            return True
        
        sub = self.get_subscription(user_id)
        if not sub:
            return False
        
        expiry = datetime.fromisoformat(sub['expiry'])
        return datetime.now() < expiry
    
    def get_subscription_info(self, user_id):
        if user_id == ADMIN_ID:
            return {"status": "👑 Администратор", "expiry": "Бессрочно", "days_left": "∞"}
        
        if user_id in cfg.get_admins():
            return {"status": "👨‍💼 Админ", "expiry": "Бессрочно", "days_left": "∞"}
        
        sub = self.get_subscription(user_id)
        if not sub:
            return {"status": "❌ Неактивна", "expiry": "-", "days_left": "0"}
        
        expiry = datetime.fromisoformat(sub['expiry'])
        now = datetime.now()
        
        if now > expiry:
            return {"status": "❌ Просрочена", "expiry": expiry.strftime("%d.%m.%Y %H:%M"), "days_left": "0"}
        
        days_left = (expiry - now).days
        return {
            "status": "✅ Активна",
            "expiry": expiry.strftime("%d.%m.%Y %H:%M"),
            "days_left": str(days_left)
        }

# --- МЕНЕДЖЕР РЕСУРСОВ ---
class ResourceManager:
    def __init__(self):
        self.proxies = []
        self.mails = []
        self.sessions = []
        # Конфигурация SMTP серверов для разных почт
        self.smtp_configs = {
            # Gmail и Google Apps
            'gmail.com': {'host': 'smtp.gmail.com', 'port': 587, 'tls': True, 'ssl': False},
            'googlemail.com': {'host': 'smtp.gmail.com', 'port': 587, 'tls': True, 'ssl': False},
            
            # Яндекс
            'yandex.ru': {'host': 'smtp.yandex.ru', 'port': 465, 'tls': False, 'ssl': True},
            'ya.ru': {'host': 'smtp.yandex.ru', 'port': 465, 'tls': False, 'ssl': True},
            'yandex.com': {'host': 'smtp.yandex.com', 'port': 465, 'tls': False, 'ssl': True},
            'yandex.ua': {'host': 'smtp.yandex.ua', 'port': 465, 'tls': False, 'ssl': True},
            'yandex.kz': {'host': 'smtp.yandex.kz', 'port': 465, 'tls': False, 'ssl': True},
            'yandex.by': {'host': 'smtp.yandex.by', 'port': 465, 'tls': False, 'ssl': True},
            
            # Mail.ru
            'mail.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            'list.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            'inbox.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            'bk.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            
            # Microsoft (Outlook/Hotmail)
            'outlook.com': {'host': 'smtp-mail.outlook.com', 'port': 587, 'tls': True, 'ssl': False},
            'hotmail.com': {'host': 'smtp-mail.outlook.com', 'port': 587, 'tls': True, 'ssl': False},
            'live.com': {'host': 'smtp-mail.outlook.com', 'port': 587, 'tls': True, 'ssl': False},
            'msn.com': {'host': 'smtp-mail.outlook.com', 'port': 587, 'tls': True, 'ssl': False},
            
            # Rambler
            'rambler.ru': {'host': 'smtp.rambler.ru', 'port': 465, 'tls': False, 'ssl': True},
            'lenta.ru': {'host': 'smtp.rambler.ru', 'port': 465, 'tls': False, 'ssl': True},
            'autorambler.ru': {'host': 'smtp.rambler.ru', 'port': 465, 'tls': False, 'ssl': True},
            'myrambler.ru': {'host': 'smtp.rambler.ru', 'port': 465, 'tls': False, 'ssl': True},
            
            # Mail.tm и временные почты
            'mail.tm': {'host': 'smtp.mail.tm', 'port': 587, 'tls': True, 'ssl': False},
            'vargosmail.com': {'host': 'smtp.vargosmail.com', 'port': 587, 'tls': True, 'ssl': False},
            'tacoblastmail.com': {'host': 'smtp.tacoblastmail.com', 'port': 587, 'tls': True, 'ssl': False},
            'tempmail.com': {'host': 'smtp.tempmail.com', 'port': 587, 'tls': True, 'ssl': False},
            '10minutemail.com': {'host': 'smtp.10minutemail.com', 'port': 587, 'tls': True, 'ssl': False},
            'guerrillamail.com': {'host': 'smtp.guerrillamail.com', 'port': 587, 'tls': True, 'ssl': False},
            'mailinator.com': {'host': 'smtp.mailinator.com', 'port': 587, 'tls': True, 'ssl': False},
            'yopmail.com': {'host': 'smtp.yopmail.com', 'port': 587, 'tls': True, 'ssl': False},
            'sharklasers.com': {'host': 'smtp.sharklasers.com', 'port': 587, 'tls': True, 'ssl': False},
            
            # Другие популярные
            'yahoo.com': {'host': 'smtp.mail.yahoo.com', 'port': 587, 'tls': True, 'ssl': False},
            'ymail.com': {'host': 'smtp.mail.yahoo.com', 'port': 587, 'tls': True, 'ssl': False},
            'aol.com': {'host': 'smtp.aol.com', 'port': 587, 'tls': True, 'ssl': False},
            'protonmail.com': {'host': 'mail.protonmail.com', 'port': 587, 'tls': True, 'ssl': False},
            'zoho.com': {'host': 'smtp.zoho.com', 'port': 587, 'tls': True, 'ssl': False},
            'icloud.com': {'host': 'smtp.mail.me.com', 'port': 587, 'tls': True, 'ssl': False},
            'me.com': {'host': 'smtp.mail.me.com', 'port': 587, 'tls': True, 'ssl': False},
            'qq.com': {'host': 'smtp.qq.com', 'port': 587, 'tls': True, 'ssl': False},
            '163.com': {'host': 'smtp.163.com', 'port': 465, 'tls': False, 'ssl': True},
            '126.com': {'host': 'smtp.126.com', 'port': 465, 'tls': False, 'ssl': True},
            'sina.com': {'host': 'smtp.sina.com', 'port': 465, 'tls': False, 'ssl': True},
            
            # Российские
            'r0.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            'corp.mail.ru': {'host': 'smtp.mail.ru', 'port': 465, 'tls': False, 'ssl': True},
            'pochta.ru': {'host': 'smtp.pochta.ru', 'port': 587, 'tls': True, 'ssl': False},
        }

    def reload(self):
        if os.path.exists(FILES['proxies']):
            with open(FILES['proxies'], 'r', encoding='utf-8', errors='ignore') as f:
                self.proxies = [l.strip() for l in f if ':' in l]
        
        if os.path.exists(FILES['mails']):
            with open(FILES['mails'], 'r', encoding='utf-8', errors='ignore') as f:
                self.mails = [l.strip() for l in f if ':' in l]
                
        self.sessions = [f for f in os.listdir('sessions') if f.endswith('.session')]

    def get_text(self, uname, uid):
        try:
            files = [f for f in os.listdir('texts') if f.endswith('.txt')]
            if not files: return f"Report @{uname}"
            
            path = os.path.join('texts', random.choice(files))
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().replace("{username}", str(uname)).replace("{id}", str(uid))
        except: return f"Report @{uname}"

    def get_smtp_config(self, email):
        """Получает конфигурацию SMTP для email"""
        domain = email.split('@')[1].lower()
        
        if domain in self.smtp_configs:
            return self.smtp_configs[domain]
        
        for key, config in self.smtp_configs.items():
            if domain.endswith('.' + key):
                return config
        
        return {'host': f'smtp.{domain}', 'port': 587, 'tls': True, 'ssl': False}

    # --- ВАЛИДАЦИЯ ---
    async def check_proxies(self):
        valid = []
        async def check(p):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get("https://telegram.org", proxy=f"http://{p}", timeout=10) as r:
                        if r.status == 200: valid.append(p)
            except: pass
        
        all_proxies = self.proxies
        for i in range(0, len(all_proxies), 20):
            chunk = all_proxies[i:i+20]
            await asyncio.gather(*[check(p) for p in chunk])
            await asyncio.sleep(0.1)
        
        if valid:
            with open(FILES['proxies'], 'w', encoding='utf-8') as f:
                f.write("\n".join(valid))
        self.reload()
        return len(valid)

    async def check_mails(self):
        valid = []
        total = len(self.mails)
        
        for idx, m in enumerate(self.mails, 1):
            try:
                if ':' not in m:
                    continue
                    
                log, pwd = m.split(':', 1)
                if '@' not in log:
                    continue
                    
                email = log.strip()
                config = self.get_smtp_config(email)
                
                print(f"[{idx}/{total}] Проверка {email} через {config['host']}:{config['port']}")
                
                try:
                    if config['ssl']:
                        async with aiosmtplib.SMTP(hostname=config['host'], port=config['port'], use_tls=True) as smtp:
                            await smtp.login(email, pwd)
                            valid.append(m)
                            print(f"  ✓ Успешно: {email}")
                    else:
                        async with aiosmtplib.SMTP(hostname=config['host'], port=config['port']) as smtp:
                            await smtp.starttls()
                            await smtp.login(email, pwd)
                            valid.append(m)
                            print(f"  ✓ Успешно: {email}")
                            
                except Exception as e:
                    print(f"  ✗ Ошибка {email}: {str(e)[:50]}")
                    continue
                    
            except Exception as e:
                print(f"  ✗ Общая ошибка для {m}: {str(e)[:50]}")
                continue
        
        if valid:
            with open(FILES['mails'], 'w', encoding='utf-8') as f:
                f.write("\n".join(valid))
        self.reload()
        return len(valid)

    async def check_sessions(self):
        valid = []
        for s in self.sessions:
            try:
                c = TelegramClient(f"sessions/{s}", API_ID, API_HASH)
                await c.connect()
                if await c.is_user_authorized(): valid.append(s)
                await c.disconnect()
            except: pass
        return len(valid)
    
    def get_supported_emails_info(self):
        """Возвращает информацию о поддерживаемых почтах"""
        supported = list(self.smtp_configs.keys())
        supported.sort()
        
        categories = {
            "Основные": ['gmail.com', 'mail.ru', 'yandex.ru', 'outlook.com', 'yahoo.com'],
            "Российские": ['mail.ru', 'yandex.ru', 'rambler.ru', 'list.ru', 'bk.ru', 'inbox.ru'],
            "Временные": ['mail.tm', 'vargosmail.com', 'tacoblastmail.com', 'tempmail.com', '10minutemail.com'],
            "Международные": ['hotmail.com', 'aol.com', 'protonmail.com', 'icloud.com', 'zoho.com'],
            "Китайские": ['qq.com', '163.com', '126.com', 'sina.com']
        }
        
        info = "📧 <b>Поддерживаемые почтовые сервисы:</b>\n\n"
        
        for category, emails in categories.items():
            info += f"<b>{category}:</b>\n"
            for email in emails:
                if email in self.smtp_configs:
                    config = self.smtp_configs[email]
                    port_type = "SSL" if config['ssl'] else "TLS"
                    info += f"  • {email} ({config['host']}:{config['port']}, {port_type})\n"
            info += "\n"
        
        info += f"\n<b>Всего поддерживается:</b> {len(self.smtp_configs)} сервисов\n"
        info += "<i>Также поддерживаются другие почты через стандартный SMTP</i>"
        
        return info

cfg = ConfigManager()
rm = ResourceManager()