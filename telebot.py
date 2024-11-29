import random
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta

# Токен вашего бота
BOT_TOKEN = '7532462167:AAFrEoclnACi8qzPTRvZedM7r06BMYE0ep8'
SUPPORT_CHAT_ID = '-4657717234'  # Замените на ID вашего чата для техподдержки

# Хранение кода подтверждения и ограничений
user_codes = {}  # Словарь для хранения данных пользователей (username, code, timestamp, attempts)

# Генерация шестизначного кода
def generate_confirmation_code():
    return ''.join(random.choices('0123456789', k=6))

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Запрос на ввод Telegram username
    await update.message.reply_text("Введите ваш Telegram username, чтобы получить код подтверждения:")

# Обработчик ввода username
async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()

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

    # Отправляем код пользователю
    await update.message.reply_text(f"Ваш код подтверждения: {code}. Этот код действителен в течение 10 минут.")

# Обработчик ввода кода
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()

    # Проверка, есть ли код для этого пользователя
    if user_id not in user_codes:
        await update.message.reply_text("Вы не запросили код подтверждения. Пожалуйста, начните с команды /start.")
        return

    user_data = user_codes[user_id]

    # Проверка на истечение времени действия кода
    if datetime.now() > user_data['expiration']:
        del user_codes[user_id]
        await update.message.reply_text("Ваш код подтверждения истек. Пожалуйста, введите username заново.")
        return

    # Проверка на количество попыток
    if user_data['attempts'] >= 3:
        del user_codes[user_id]
        await update.message.reply_text("Вы превысили количество попыток ввода. Пожалуйста, запросите новый код.")
        return

    # Проверка на правильность введенного кода
    if entered_code == user_data['code']:
        del user_codes[user_id]  # Удаляем код после успешного ввода
        await update.message.reply_text("Код подтверждения правильный! Вы успешно прошли проверку.")
    else:
        user_data['attempts'] += 1
        attempts_left = 3 - user_data['attempts']
        await update.message.reply_text(f"Неправильный код. Осталось попыток: {attempts_left}.")

# Обработчик сообщений от пользователя для техподдержки
async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Не указан"
    message = update.message.text

    # Пересылаем сообщение в чат техподдержки
    support_message = f"Username: {username}\nMessage: {message}"
    await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=support_message)

    # Ответ пользователю
    await update.message.reply_text("Благодарим за ваше сообщение. Наша команда техподдержки немедленно займется вашей проблемой.")

# Основной обработчик кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'support':
        await support(update, context)
    elif query.data == 'vpn_config':
        await query.edit_message_text(text="Функция получения VPN конфигурации будет доступна позже.")
    elif query.data == 'back_to_main_menu':
        await start(update, context)

# Обработчик команды поддержки
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back_to_main_menu')]  # Кнопка назад
    ]
    await update.callback_query.message.reply_text("Доброго времени суток! Чем именно мы можем вам помочь?", reply_markup=InlineKeyboardMarkup(keyboard))

# Основная функция запуска бота
def main():
    # Используем новый Application вместо Updater
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))  # Обработчик для ввода username
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))  # Обработчик для ввода кода
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))  # Обработчик поддержки

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
