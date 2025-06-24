import os
from dotenv import load_dotenv
import logging
import re
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from mcrcon import MCRcon

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
RCON_HOST = os.getenv('RCON_HOST')
RCON_PORT = int(os.getenv('RCON_PORT'))
RCON_PASSWORD = os.getenv('RCON_PASSWORD')

# Параметры MySQL
DB_CONFIG = {
    "host": os.getenv('DB_HOST'),       
    "port": int(os.getenv('DB_PORT')),             
    "database": os.getenv('DB_NAME'),  
    "user": os.getenv('DB_USER'),   
    "password": os.getenv('DB_PASSWORD')     
}

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Регулярное выражение для ника
NICKNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,16}$")

# Инициализация БД
def init_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                minecraft_nick VARCHAR(16) NOT NULL,
                added_at DATETIME NOT NULL,
                role VARCHAR(10) NOT NULL DEFAULT 'player'
            )
        """)
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка MySQL: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Проверка пользователя в БД
def is_user_in_db(user_id: int) -> tuple[bool, str]:
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            return True, result[0]
        return False, ""
    except Error as e:
        logger.error(f"Ошибка MySQL: {e}")
        return False, ""
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Добавление пользователя в БД
def add_user_to_db(user_id: int, minecraft_nick: str, role: str = "player"):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, minecraft_nick, added_at, role)
            VALUES (%s, %s, %s, %s)
        """, (user_id, minecraft_nick, datetime.now(), role))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка MySQL: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_in_db, role = is_user_in_db(user_id)
    if is_in_db and role == "player":
        await update.message.reply_text(
            "❌ Вы уже добавили игрока. Один пользователь может добавить только одного игрока!"
        )
    else:
        await update.message.reply_text(
            "Привет! Отправь мне ник игрока (3-16 символов, латиница, цифры или _), "
            "и я добавлю его в вайтлист и группу default. У вас есть право добавить только одного игрока!"
        )

# Обработка ника
async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nickname = update.message.text.strip()

    is_in_db, role = is_user_in_db(user_id)
    if is_in_db and role == "player":
        await update.message.reply_text("❌ Вы уже использовали свой лимит (1 игрок).")
        return

    if not NICKNAME_PATTERN.match(nickname):
        await update.message.reply_text(
            "❌ Неверный формат ника! Допустимо:\n"
            "- Только A-Z, a-z, 0-9 и _\n"
            "- Длина: 3-16 символов."
        )
        return

    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, RCON_PORT) as mcr:
            # Добавляем в вайтлист
            whitelist_response = mcr.command(f"whitelist add {nickname}")
            
            # Добавляем в группу default
            lp_response = mcr.command(f"lp user {nickname} group add default")
            
            # Сохраняем в БД (если не админ)
            if role != "admin":
                add_user_to_db(user_id, nickname)
            
            await update.message.reply_text(
                f"✅ Игрок {nickname} добавлен!\n"
                f"Вайтлист: {whitelist_response}\n"
                f"Группа: {lp_response}"
            )
    except Exception as e:
        logger.error(f"Ошибка RCON: {e}")
        await update.message.reply_text("❌ Ошибка при отправке команды на сервер.")

# Запуск бота
def main():
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))
    application.run_polling()

if __name__ == "__main__":
    main()