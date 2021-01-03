""" Script for launching the bot """
from telebot import TeleBot
from app.models import User, Game, Wish, Session
from json import dumps

bot = TeleBot(token=open('creds/telegram.token').read())


@bot.message_handler(commands=['start'])
def start_message(message):
    """ Greeting message """
    bot.send_message(message.chat.id, 'Привет, я бот для твоего вишлиста в Sony PlayStation Network. Ты можешь кидать '
                                      'мне ссылки на игры, которые ты хочешь когда-нибудь купить, а я пришлю тебе '
                                      'сообщение, если на какие-то из них будут скидки. Чтобы увидеть, что я умею, '
                                      'напиши /help')


@bot.message_handler(commands=['help'])
def help_message(message):
    """ List of commands """
    bot.send_message(message.chat.id, '''Список доступных команд: /help — увидеть это сообщение /add — добавить игру 
    в вишлист, пример: `/add https://store.playstation.com/ru-ru/concept/10000237` или `/add 10000237` значит 
    добавить в вишлист Assassin's Creed Valhalla 
    ''')


@bot.message_handler(commands=['add'])
def add_game(message):
    """ Add a game to a user's wishlist"""
    try:
        wish, is_created = Wish.get_or_create(user_id=message.chat.id, game_id=message.text.split(' ', maxsplit=1)[1])
        game_name = Game.get(id=wish.game_id).name
        if is_created:
            response = f'Игра успешно добавлена в твой вишлист: {game_name}.'
        else:
            response = f'Эта игра уже есть в твоём вишлисте: {game_name}.'
    except ValueError as ve:
        response = str(ve)
    bot.send_message(message.chat.id, response, parse_mode='MARKDOWN')


bot.polling(none_stop=True)
