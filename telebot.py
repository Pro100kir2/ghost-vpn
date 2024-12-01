import random
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
import logging

# Словарь для хранения кодов и времени их действия
user_codes = {}

# Токен вашего бота
BOT_TOKEN = '7532462167:AAFrEoclnACi8qzPTRvZedM7r06BMYE0ep8'
SUPPORT_CHAT_ID = '-4657717234'  # Замените на ID вашего чата для техподдержки

# Инициализация логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Генерация шестизначного случайного кода
def generate_confirmation_code():
    return random.randint(100000, 999999)

# Отправка сообщения пользователю через Telegram API
async def send_code_to_user(username, code):
    try:
        # Отправляем код пользователю
        await bot.send_message(chat_id=username, text=f"Ваш код подтверждения: {code}")
        return True
    except Exception as e:
        print(f"Ошибка отправки кода: {e}")
        return False

# Команда start: приветствие пользователя
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Привет! Пожалуйста, введите свой Telegram username для получения кода подтверждения.')

# Обработка ввода username
async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()

    # Убедитесь, что username начинается с @, если нет, добавляем его
    if not username.startswith('@'):
        username = '@' + username

    # Генерация шестизначного кода и установка таймера (10 минут)
    code = generate_confirmation_code()
    expiration_time = datetime.now() + timedelta(minutes=10)

    # Сохраняем информацию о коде
    user_codes[update.message.from_user.id] = {
        'username': username,
        'code': code,
        'expiration': expiration_time,
        'attempts': 0
    }

    # Отправляем код на Telegram username
    await update.message.reply_text(f"Ваш код подтверждения: {code}. Этот код действителен в течение 10 минут.")

    # Отправка кода пользователю через Telegram API
    await send_telegram_message(context, username, f"Ваш код подтверждения: {code}. Этот код действителен в течение 10 минут.")

# Обработка ввода кода подтверждения
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_codes:
        await update.message.reply_text(
            "Вы не запросили код подтверждения. Пожалуйста, введите свой username для его получения.")
        return

    # Получаем введенный код
    user_input_code = update.message.text.strip()

    # Проверка на истечение времени действия
    code_info = user_codes[user_id]
    if datetime.now() > code_info['expiration']:
        del user_codes[user_id]
        await update.message.reply_text("Ваш код истек. Пожалуйста, запросите новый.")
        return

    # Проверка на количество попыток
    if code_info['attempts'] >= 3:
        await update.message.reply_text("Вы исчерпали количество попыток. Пожалуйста, запросите новый код.")
        return

    # Проверка кода
    if int(user_input_code) == code_info['code']:
        await update.message.reply_text("Код подтверждения верен! Вы успешно прошли проверку.")
        del user_codes[user_id]  # Удалить информацию о коде после успешной проверки
    else:
        # Увеличиваем количество попыток
        code_info['attempts'] += 1
        await update.message.reply_text(f"Неверный код! Попыток осталось: {3 - code_info['attempts']}")

# Главная функция для запуска бота
def main():
    # Укажите ваш токен бота
    bot_token = BOT_TOKEN
    application = Application.builder().token(bot_token).build()

    # Команды и обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))
    application.add_handler(MessageHandler(filters.TEXT, handle_code))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
