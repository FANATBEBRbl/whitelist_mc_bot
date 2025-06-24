import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from mcrcon import MCRcon

# Конфигурация
TELEGRAM_TOKEN = "ONET"
RCON_HOST = "KAKTIMOG"  # или IP сервера Minecraft
RCON_PORT = 11111
RCON_PASSWORD = "AHAHAHAHH"

# Настройка логгирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Отправь мне ник игрока, и я добавлю его на сервер!")

async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nickname = update.message.text.strip()
    
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, RCON_PORT) as mcr:
            response = mcr.command(f"whitelist add {nickname}")
            await update.message.reply_text(f"Игрок {nickname} добавлен! Ответ сервера: {response}")
    except Exception as e:
        logger.error(f"Ошибка RCON: {e}")
        await update.message.reply_text("Произошла ошибка при отправке команды на сервер.")

def main() -> None:
    # Создаём Application вместо Updater
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()