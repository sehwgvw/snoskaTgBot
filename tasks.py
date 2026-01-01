import aiohttp
import asyncio
import random
import aiosmtplib
from telethon import TelegramClient, functions, types
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from config import API_ID, API_HASH, rm

# WEB
async def send_web(proxy, target, text):
    url = "https://telegram.org/support"
    data = {
        'message': text,
        'email': f"user{random.randint(1000,99999)}@gmail.com",
        'set_phone': f"+{random.randint(10000000000, 99999999999)}"
    }
    try:
        p_url = f"http://{proxy}" if proxy else None
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, data=data, proxy=p_url) as r:
                return r.status == 200
    except: 
        return False

# MAIL
async def send_mail(mail_line, target, text, photo):
    try:
        if ':' not in mail_line: 
            return False
            
        log, pwd = mail_line.split(':', 1)
        if '@' not in log: 
            return False
            
        email = log.strip()
        config = rm.get_smtp_config(email)
        
        msg = MIMEMultipart()
        msg['From'] = email
        msg['To'] = "abuse@telegram.org"
        msg['Subject'] = f"Срочная жалоба на пользователя: {target}"
        
        body = f"{text}\n\n"
        body += f"Цель: @{target}\n"
        body += f"Отправитель: {email}\n"
        body += "---\n"
        body += "Это автоматическое сообщение о нарушении правил Telegram."
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        if photo:
            img = MIMEImage(photo)
            img.add_header('Content-Disposition', 'attachment', filename="proof.jpg")
            img.add_header('Content-ID', '<proof_image>')
            msg.attach(img)
        
        try:
            if config['ssl']:
                async with aiosmtplib.SMTP(
                    hostname=config['host'], 
                    port=config['port'], 
                    use_tls=True,
                    timeout=20
                ) as smtp:
                    await smtp.login(email, pwd)
                    await smtp.send_message(msg)
                    return True
            else:
                async with aiosmtplib.SMTP(
                    hostname=config['host'], 
                    port=config['port'],
                    timeout=20
                ) as smtp:
                    await smtp.starttls()
                    await smtp.login(email, pwd)
                    await smtp.send_message(msg)
                    return True
                    
        except Exception as e:
            print(f"Ошибка отправки с {email}: {str(e)[:100]}")
            return False
            
    except Exception as e:
        print(f"Общая ошибка для {mail_line}: {str(e)[:100]}")
        return False

# SESSION
async def send_session(sess_file, target, text):
    try:
        c = TelegramClient(f"sessions/{sess_file}", API_ID, API_HASH)
        await c.connect()
        if not await c.is_user_authorized():
            await c.disconnect()
            return False
            
        try: 
            entity = await c.get_entity(target)
        except: 
            await c.disconnect()
            return False
        
        await c(functions.account.ReportPeerRequest(
            peer=entity,
            reason=types.InputReportReasonSpam(),
            message=text
        ))
        
        await c.disconnect()
        return True
        
    except Exception as e:
        print(f"Ошибка сессии {sess_file}: {str(e)[:100]}")
        return False