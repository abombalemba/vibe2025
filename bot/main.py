import telebot
from telebot import types
import mysql.connector
from mysql.connector import Error
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

bot = telebot.TeleBot(os.getenv('TOKEN'))

sessions = {}

db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}


def get_db_connection():
    try:
        return mysql.connector.connect(**db_config)
    except Error as error:
        print(error)
        return None


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@bot.message_handler(commands=['start'])
def start_handler(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('Войти', 'Зарегистрироваться')
    bot.send_message(
        message.chat.id,
        'Добро пожаловать в To-Do бота! Выберите действие:',
        reply_markup=markup
    )


@bot.message_handler(func=lambda m: m.text == 'Войти')
def login_handler(message):
    msg = bot.send_message(message.chat.id, 'Введите ваш логин:')
    bot.register_next_step_handler(msg, process_username_step)


def process_username_step(message):
    username = message.text
    msg = bot.send_message(message.chat.id, 'Введите ваш пароль:')
    bot.register_next_step_handler(msg, process_password_step, username)


def process_password_step(message, username):
    password = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f'SELECT id, passhash FROM accounts WHERE username = "{username}"')
        user = cursor.fetchone()
        
        if user and user['passhash'] == hash_password(password):
            sessions[message.chat.id] = user['id']
            bot.send_message(message.chat.id, 'Вы успешно вошли!')
            show_main_menu(message.chat.id)
        else:
            bot.send_message(message.chat.id, 'Неверный логин или пароль')
        
    except Error as error:
        bot.send_message(message.chat.id, 'Произошла ошибка при входе')
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == 'Зарегистрироваться')
def register_handler(message):
    msg = bot.send_message(message.chat.id, 'Придумайте логин:')
    bot.register_next_step_handler(msg, process_reg_username_step)


def process_reg_username_step(message):
    username = message.text
    msg = bot.send_message(message.chat.id, 'Придумайте пароль:')
    bot.register_next_step_handler(msg, process_reg_password_step, username)


def process_reg_password_step(message, username):
    password = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute(f'INSERT INTO accounts (username, passhash) VALUES ("{username}", "{hash_password(password)}")')

        user_id = cursor.lastrowid
        connection.commit()

        sessions[message.chat.id] = user_id
        bot.send_message(message.chat.id, 'Регистрация успешна!')
        show_main_menu(message.chat.id)

    except Error as error:
        if error.errno == 1062:
            bot.send_message(message.chat.id, 'Такой логин уже существует')
        else:
            bot.send_message(message.chat.id, 'Ошибка при регистрации')
            print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.add('📝 Мои заметки')
    markup.add('➕ Добавить заметку', '🖊 Редактировать заметку', '➖ Удалить заметку')
    markup.add('🔐 Выйти')

    bot.send_message(chat_id, 'Главное меню:', reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == '📝 Мои заметки')
def show_notes(message):
    user_id = sessions.get(message.chat.id)
    if not user_id:
        bot.send_message(message.chat.id, 'Пожалуйста, войдите в систему')
        return
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f'SELECT id, text FROM items WHERE user_id = "{user_id}"')
        notes = cursor.fetchall()
        
        if not notes:
            bot.send_message(message.chat.id, 'У вас пока нет заметок')
            return
        
        response = "📋 Ваши заметки:\n\n"
        for note in notes:
            response += f"{note['id']}.\t{note['text']}\n\n"
        
        bot.send_message(message.chat.id, response)

    except Error as error:
        bot.send_message(message.chat.id, 'Ошибка при получении заметок')
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == '➕ Добавить заметку')
def add_note_start(message):
    user_id = sessions.get(message.chat.id)
    if not user_id:
        bot.send_message(message.chat.id, 'Пожалуйста, войдите в систему')
        return
    
    msg = bot.send_message(message.chat.id, 'Введите текст заметки:')
    bot.register_next_step_handler(msg, add_note_finish, user_id)


def add_note_finish(message, user_id):
    text = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(f'INSERT INTO items (user_id, text) VALUES ("{user_id}", "{text}")')
        connection.commit()
        bot.send_message(message.chat.id, '✅ Заметка успешно добавлена!')

    except Error as error:
        bot.send_message(message.chat.id, '❌ Ошибка при добавлении заметки')
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == '🔐 Выйти')
def logout_handler(message):
    if message.chat.id in sessions:
        del sessions[message.chat.id]
    bot.send_message(message.chat.id, 'Вы вышли из системы')
    start_handler(message)


if __name__ == '__main__':
    bot.polling(none_stop=True)
