from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import random

# Токен вашего бота
BOT_TOKEN = '7532462167:AAFrEoclnACi8qzPTRvZedM7r06BMYE0ep8'
SUPPORT_CHAT_ID = '<your_support_chat_id>'  # Замените на ID вашего чата для техподдержки

# Генерация шестизначного кода
def generate_confirmation_code():
    return ''.join(random.choices('0123456789', k=6))


# Обработчик команды /start
async def start(update, context):
    # Для обработчика start используем reply_markup с кнопками
    keyboard = [
        [InlineKeyboardButton("Get My VPN Config", callback_data='vpn_config'),
         InlineKeyboardButton("Поддержка", callback_data='support')]  # Кнопки на одной строке
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Если update это callback_query, то используем update.callback_query.message для отправки сообщения
    if update.callback_query:
        await update.callback_query.message.reply_text('Добро пожаловать! Выберите действие:', reply_markup=reply_markup)
    else:
        await update.message.reply_text('Добро пожаловать! Выберите действие:', reply_markup=reply_markup)


# Обработчик кнопки "Поддержка"
async def support(update, context):
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back_to_main_menu')]  # Кнопка назад
    ]
    user_id = update.callback_query.from_user.id  # Используем from_user из callback_query
    await update.callback_query.message.reply_text("Доброго времени суток! Чем именно мы можем вам помочь?", reply_markup=InlineKeyboardMarkup(keyboard))
    return


# Обработчик сообщения от пользователя в поддержке
async def handle_support_message(update, context):
    message = update.message.text
    user_id = update.message.from_user.id

    # Пересылаем сообщение в чат техподдержки
    await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=f"Сообщение от пользователя {user_id}: {message}")

    # Ответ пользователю
    await update.message.reply_text(
        "Благодарим за ваше сообщение. Наша команда техподдержки немедленно займется вашей проблемой.")


# Обработчик кнопок
async def button(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'support':
        await support(update, context)
    elif query.data == 'vpn_config':
        # Временно для первой кнопки, можно добавить функционал позже
        await query.edit_message_text(text="Функция получения VPN конфигурации будет доступна позже.")
    elif query.data == 'back_to_main_menu':
        await start(update, context)


# Основная функция запуска бота
def main():
    # Используем новый Application вместо Updater
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()
