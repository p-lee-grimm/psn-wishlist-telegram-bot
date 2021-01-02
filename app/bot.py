""" Script for launching the bot """
from telebot import TeleBot

bot = TeleBot(token=open('creds/telegram.token').read())


@bot.message_handler(commands=['start'])
def start_message(message):
    """ Greeting message """
    bot.send_message(message.chat.id, 'Привет, я бот для твоего вишлиста в Sony PlayStation Network. Ты можешь кидать '
                                      'мне ссылки на игры, которые ты хочешь когда-нибудь купить, а я пришлю тебе '
                                      'сообщение, если на какие-то из них будут скидки.')


bot.polling()
