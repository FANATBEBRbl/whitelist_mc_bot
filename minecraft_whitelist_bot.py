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

# Настройка логгирования перед всеми операциями
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_config():
    """Загрузка и валидация конфигурации"""
    try:
        # Загрузка переменных окружения
        if not load_dotenv('data.env'):
            logger.warning("Файл data.env не найден, используются переменные окружения системы")
        
        # Проверка обязательных переменных
        config = {
            'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
            'RCON_HOST': os.getenv('RCON_HOST', 'localhost'),
            'RCON_PORT': os.getenv('RCON_PORT'),
            'RCON_PASSWORD': os.getenv('RCON_PASSWORD'),
            'DB_HOST': os.getenv('DB_HOST'),
            'DB_PORT': os.getenv('DB_PORT'),
            'DB_NAME': os.getenv('DB_NAME'),
            'DB_USER': os.getenv('DB_USER'),
            'DB_PASSWORD': os.getenv('DB_PASSWORD')
        }

        # Проверка обязательных переменных
        required_vars = ['TELEGRAM_TOKEN', 'RCON_PASSWORD']
        for var in required_vars:
            if not config[var]:
                raise ValueError(f"Необходимая переменная окружения {var} не установлена")

        # Преобразование портов
        try:
            config['RCON_PORT'] = int(config['RCON_PORT']) if config['RCON_PORT'] else 25575
            config['DB_PORT'] = int(config['DB_PORT']) if config['DB_PORT'] else 3306
        except ValueError as e:
            raise ValueError("Порт должен быть целым числом") from e

        return config
    except Exception as e:
        logger.critical(f"Ошибка загрузки конфигурации: {e}")
        raise

class Database:
    """Класс для работы с базой данных"""
    def __init__(self, config):
        self.config = {
            'host': config['DB_HOST'],
            'port': config['DB_PORT'],
            'database': config['DB_NAME'],
            'user': config['DB_USER'],
            'password': config['DB_PASSWORD']
        }
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            invited_by BIGINT NOT NULL,
                            minecraft_nick VARCHAR(16) NOT NULL,
                            added_at DATETIME NOT NULL,
                            role VARCHAR(10) NOT NULL DEFAULT 'player',
                            
                        )
                    """)
                    conn.commit()
                    logger.info("Таблица users создана или уже существует")
        except Error as e:
            logger.error(f"Ошибка инициализации БД: {e}")
            raise

    def get_connection(self):
        """Получение соединения с БД"""
        try:
            return mysql.connector.connect(**self.config)
        except Error as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            raise

    def is_user_in_db(self, user_id: int) -> tuple[bool, str]:
        """Проверка наличия пользователя в БД"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT role FROM users WHERE invited_by = %s", (user_id,))
                    result = cursor.fetchone()
                    return (True, result[0]) if result else (False, "")
        except Error as e:
            logger.error(f"Ошибка проверки пользователя: {e}")
            return False, ""

    def add_user(self, user_id: int, minecraft_nick: str, role: str = "player"):
        """Добавление пользователя в БД"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO users (invited_by, minecraft_nick, added_at, role)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, minecraft_nick, datetime.now(), role))
                    conn.commit()
                    logger.info(f"Добавлен пользователь {user_id} с ником {minecraft_nick}")
        except Error as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            raise

class WhitelistBot:
    """Основной класс бота"""
    def __init__(self, config):
        self.config = config
        self.db = Database(config)
        self.nickname_pattern = re.compile(r"^[a-zA-Z0-9_]{3,16}$")
        self.application = Application.builder().token(config['TELEGRAM_TOKEN']).build()
        
        # Регистрация обработчиков
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_nickname))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user_id = update.effective_user.id
        is_in_db, role = self.db.is_user_in_db(user_id)
        
        if is_in_db and role == "player":
            await update.message.reply_text(
                "❌ Вы уже добавили игрока. Один пользователь может добавить только одного игрока!"
            )
        else:
            await update.message.reply_text(
                "Привет! Отправь мне ник игрока (3-16 символов, латиница, цифры или _), "
                "и я добавлю его в вайтлист и группу default. У вас есть право добавить только одного игрока!"
            )

    async def handle_nickname(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ника игрока"""
        user_id = update.effective_user.id
        nickname = update.message.text.strip()

        # Проверка формата ника
        if not self.nickname_pattern.match(nickname):
            await update.message.reply_text(
                "❌ Неверный формат ника! Допустимо:\n"
                "- Только A-Z, a-z, 0-9 и _\n"
                "- Длина: 3-16 символов."
            )
            return

        # Проверка лимита
        is_in_db, role = self.db.is_user_in_db(user_id)
        if is_in_db and role == "player":
            await update.message.reply_text("❌ Вы уже использовали свой лимит (1 игрок).")
            return

        # Выполнение RCON команд
        try:
            with MCRcon(
                self.config['RCON_HOST'],
                self.config['RCON_PASSWORD'],
                self.config['RCON_PORT']
            ) as mcr:
                # Добавление в вайтлист
                combined_response = mcr.command(
                    f"whitelist add {nickname} && "
                    f"lp user {nickname} group add default"
                )
            
                logger.info(f"Combined response: {combined_response}")
                
                # Сохранение в БД (если не админ)
                if role != "admin":
                    self.db.add_user(user_id, nickname)
                
                await update.message.reply_text(f"✅ Игрок {nickname} добавлен в вайтлист и группу default.")
        except Exception as e:
            logger.error(f"Ошибка RCON: {e}")
            await update.message.reply_text("❌ Ошибка при отправке команды на сервер.")

    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        self.application.run_polling()

def main():
    try:
        config = load_config()
        bot = WhitelistBot(config)
        bot.run()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    main()