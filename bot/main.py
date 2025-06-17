import telebot as tb

import mysql.connector
from mysql.connector import Error

from dotenv import load_dotenv

import hashlib
import os


load_dotenv()

bot = telebot.TeleBot(os.getenv('TOKEN'))

sessions = {}

db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}


phrases = {
    'welcome': 'Добро пожаловать в To-Do бота! Выберите действие:',

    'signin': 'Войти',
    'signin_success': 'Вы успешно вошли!',
    'signin_unsuccess': 'Неверный логин или пароль!',
    'signin_error': 'Произошла ошибка при входе!',

    'signup': 'Зарегистрироваться',
    'signup_username': 'Придумайте логин:',
    'signup_password': 'Придумайте пароль:',
    'signup_success': 'Вы успешно зарегистрировались!',
    'signup_login_exists': 'Такой логин уже существует!',
    'signup_error': 'Ошибка при регистрации!',

    'enter_username': 'Введите ваш логин:',
    'enter_password': 'Введите ваш пароль',

    'auth_please': 'Пожалуйста, войдите в систему',

    'menu': 'Главное меню:',
    'items:': '📋 Ваши заметки:\n\n',
    'get_items': '📝 Мои заметки',
    'get_items_no_one': 'У вас пока нет заметок',
    'get_items_error': 'Ошибка при получении заметок',

    'create_item': '➕ Добавить заметку',
    'create_item_text': 'Введите текст заметки:',
    'create_item_success': '✅ Заметка успешно добавлена!',
    'create_item_unsuccess': '❌ Ошибка при добавлении заметки!',

    'edit_item': '🖊 Редактировать заметку',
    'edit_item_number': 'Введите номер заметки:',
    'edit_item_text': 'Введите новый текст заметки:',
    'edit_item_success': '✅ Заметка успешно обновлена!',
    'edit_item_unsuccess': '❌ Ошибка при обновлении заметки!',
    'edit_item_no_number': '❌ Некорректный ID заметки! Введите число',
    'edit_item_no_such': '❌ Заметка с таким ID не найдена или вам не принадлежит!',
    'edit_item_error': '❌ Ошибка при поиске заметки!',

    'delete_item': '➖ Удалить заметку',
    'delete_item_number': 'Введите номер заметки:',
    'delete_item_success': '✅ Заметка успешно удалена!',
    'delete_item_unsuccess': '❌ Ошибка при удалении заметки!',
    'delete_item_no_number': '❌ Некорректный ID заметки! Введите число',

    'signout': '🔐 Выйти',
    'signout_success': 'Вы вышли из системы'
}


def get_db_connection():
    try:
        return mysql.connector.connect(**db_config)
    except Error as error:
        raise error


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@bot.message_handler(commands=['start'])
def start_handler(message):
    markup = tb.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(phrases['signin'], phrases['signup'])

    bot.send_message(message.chat.id, phrases['welcome'], reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == phrases['signin'])
def login_handler(message):
    message = bot.send_message(message.chat.id, phrases['enter_username'])

    bot.register_next_step_handler(message, process_username_step)


def process_username_step(message):
    username = message.text
    message = bot.send_message(message.chat.id, phrases['enter_password'])

    bot.register_next_step_handler(message, process_password_step, username)


def process_password_step(message, username):
    password = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(f'SELECT id, passhash FROM accounts WHERE username = "{username}"')
        user = cursor.fetchone()
        
        if user and user['passhash'] == hash_password(password):
            sessions[message.chat.id] = user['id']

            bot.send_message(message.chat.id, phrases['signin_success'])
            show_main_menu(message.chat.id)
        else:
            bot.send_message(message.chat.id, phrases['signin_unsuccess'])
        
    except Error as error:
        bot.send_message(message.chat.id, phrases['signin_error'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == phrases['signup'])
def register_handler(message):
    message = bot.send_message(message.chat.id, phrases['signup_username'])

    bot.register_next_step_handler(message, process_reg_username_step)


def process_reg_username_step(message):
    username = message.text
    message = bot.send_message(message.chat.id, phrases['signup_password'])

    bot.register_next_step_handler(message, process_reg_password_step, username)


def process_reg_password_step(message, username):
    password = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute(f'INSERT INTO accounts (username, passhash) VALUES ("{username}", "{hash_password(password)}")')

        user_id = cursor.lastrowid
        connection.commit()

        sessions[message.chat.id] = user_id

        bot.send_message(message.chat.id, phrases['signup_success'])
        show_main_menu(message.chat.id)

    except Error as error:
        if error.errno == 1062:
            bot.send_message(message.chat.id, phrases['signup_login_exists'])
        else:
            bot.send_message(message.chat.id, phrases['signup_error'])
            print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def show_main_menu(chat_id):
    markup = tb.types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.add(phrases['get_items'])
    markup.add(phrases['create_item'], phrases['edit_item'], phrases['delete_item'])
    markup.add(phrases['signout'])

    bot.send_message(chat_id, phrases['menu'], reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == phrases['get_items'])
def show_items(message):
    user_id = sessions.get(message.chat.id)

    if not user_id:
        bot.send_message(message.chat.id, phrases['auth_please'])
        return
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(f'SELECT id, text FROM items WHERE user_id = "{user_id}"')
        items = cursor.fetchall()
        
        if not items:
            bot.send_message(message.chat.id, phrases['get_items_no_one'])
            return
        
        response = phrases['items:']
        for item in items:
            response += f"{item['id']}.\t{item['text']}\n\n"
        
        bot.send_message(message.chat.id, response)

    except Error as error:
        bot.send_message(message.chat.id, phrases['get_items_error'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == phrases['create_item'])
def add_item_start(message):
    user_id = sessions.get(message.chat.id)

    if not user_id:
        bot.send_message(message.chat.id, phrases['auth_please'])
        return
    
    message = bot.send_message(message.chat.id, phrases['create_item_text'])

    bot.register_next_step_handler(message, add_item_finish, user_id)


def add_item_finish(message, user_id):
    text = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(f'INSERT INTO items (user_id, text) VALUES ("{user_id}", "{text}")')
        connection.commit()

        bot.send_message(message.chat.id, phrases['create_item_success'])

    except Error as error:
        bot.send_message(message.chat.id, phrases['create_item_unsuccess'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == phrases['edit_item'])
def edit_handler(message):
    user_id = sessions.get(message.chat.id)

    if not user_id:
        bot.send_message(message.chat.id, phrases['auth_please'])
        return
    
    message = bot.send_message(message.chat.id, phrases['edit_item_number'])

    bot.register_next_step_handler(message, process_edit_item_id, user_id)


def process_edit_item_id(message, user_id):
    try:
        item_id = int(message.text)
        
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(f'SELECT id FROM items WHERE id = "{item_id}" AND user_id = "{user_id}"')
        item = cursor.fetchone()
        
        if not item:
            bot.send_message(message.chat.id, phrases['edit_item_no_such'])
            return
        
        message = bot.send_message(message.chat.id, phrases['edit_item_text'])

        bot.register_next_step_handler(message, process_edit_item_text, user_id, item_id)
        
    except ValueError:
        bot.send_message(message.chat.id, phrases['edit_item_no_number'])

    except Error as error:
        bot.send_message(message.chat.id, phrases['edit_item_error'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def process_edit_item_text(message, user_id, item_id):
    new_text = message.text
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute(f'UPDATE items SET text = "{new_text}" WHERE id = "{item_id}" AND user_id = "{user_id}"')
        connection.commit()
        
        bot.send_message(message.chat.id, phrases['edit_item_success'])

    except Error as error:
        bot.send_message(message.chat.id, phrases['edit_item_unsuccess'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == phrases['delete_item'])
def delete_item_start(message):
    user_id = sessions.get(message.chat.id)

    if not user_id:
        bot.send_message(message.chat.id, phrases['auth_please'])
        return
    
    message = bot.send_message(message.chat.id, phrases['delete_item_number'])

    bot.register_next_step_handler(message, delete_item_finish, user_id)


def delete_item_finish(message, user_id):   
    try:
        item_id = int(message.text)

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(f'DELETE FROM items WHERE id = "{item_id}" AND user_id = "{user_id}"')
        connection.commit()

        bot.send_message(message.chat.id, phrases['delete_item_success'])

    except ValueError:
        bot.send_message(message.chat.id, phrases['delete_item_no_number'])

    except Error as error:
        bot.send_message(message.chat.id, phrases['delete_item_unsuccess'])
        print(error)

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


@bot.message_handler(func=lambda m: m.text == phrases['signout'])
def logout_handler(message):
    if message.chat.id in sessions:
        del sessions[message.chat.id]
    
    bot.send_message(message.chat.id, phrases['signout_success'])

    start_handler(message)


if __name__ == '__main__':
    bot.polling(none_stop=True)
