import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from mcrcon import MCRcon

# Конфигурация
TELEGRAM_TOKEN = "ONET"
RCON_HOST = "KAKTIMOG"
RCON_PORT = 11111
RCON_PASSWORD = "GFDGFD"

# Настройка логгирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Привет! Отправь мне ник игрока, и я добавлю его на сервер!")

def handle_nickname(update: Update, context: CallbackContext) -> None:
    nickname = update.message.text.strip()
    
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, RCON_PORT) as mcr:
            response = mcr.command(f"whitelist add {nickname}")  # Пример команды
            update.message.reply_text(f"Игрок {nickname} добавлен! Ответ сервера: {response}")
    except Exception as e:
        logger.error(f"Ошибка RCON: {e}")
        update.message.reply_text("Произошла ошибка при отправке команды на сервер.")

def main() -> None:
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_nickname))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()