""" Script for launching the bot """
from telebot import TeleBot
from app.models import Game, Wish
from PIL import Image
from io import BytesIO
from requests import get

import logging

logging.basicConfig(filename='bot.log', filemode='a', level=logging.DEBUG,
                    format='%(asctime)s.%(msecs)d[%(name)s.%(levelname)s]: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('bot_logger')

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
    bot.send_message(message.chat.id, f'''Список доступных команд: 
    
/help — увидеть это сообщение 

/add — {add_game.__doc__}

/del — {del_game.__doc__}

/list — {get_wishlist.__doc__}
''', parse_mode='MARKDOWN')


@bot.message_handler(commands=['add'])
def add_game(message):
    """ добавить игру в вишлист, пример:
`/add https://store.playstation.com/ru-ru/concept/10000237`
или
`/add 10000237`
добавить в вишлист Assassin's Creed Valhalla """
    try:
        wish, is_created = Wish.get_or_create(user_id=message.chat.id, game_id=message.text.split(' ', maxsplit=1)[1])
        game = Game.get(id=wish.game_id)
        if is_created:
            response = f'Игра успешно добавлена в твой вишлист: {game}.'
        else:
            response = f'Эта игра уже есть в твоём вишлисте: {game}.'
        if game.poster_url:
            image_content = get(game.poster_url).content
            image = Image.open(BytesIO(image_content))
            image_content = BytesIO()
            image.seek(0)
            image.save(image_content, format='JPEG')
            image_content.seek(0)
            bot.send_photo(chat_id=message.chat.id, photo=image_content, parse_mode='MARKDOWN', caption=response)
            return
    except ValueError as ve:
        response = str(ve)
    bot.send_message(message.chat.id, response, parse_mode='MARKDOWN')


@bot.message_handler(commands=['del'])
def del_game(message):
    """ удалить игру из вишлиста, пример:
`/del https://store.playstation.com/ru-ru/product/EP3862-CUSA10484_00-DEADCELLS0000000`
или
`/del EP3862-CUSA10484_00-DEADCELLS0000000`
удалить из вишлиста Dead Cells """
    game_id = message.text.split(' ', maxsplit=1)[1]
    try:
        game, game_is_new = Game.get_or_create(game_id)
        was_deleted = Wish.delete(user_id=message.chat.id, game_id=game_id)
        if was_deleted:
            response = f'Игра была успешно удалена: {game}'
        elif game_is_new or game and not was_deleted:
            response = f'Игра отсутствует в вашем вишлисте: {game}'
        else:
            response = f'Игра с таким идентификатором не найдена: {game.name}'
    except ValueError as ve:
        response = str(ve)

    bot.send_message(message.chat.id, response, parse_mode='MARKDOWN')


@bot.message_handler(commands=['list'])
def get_wishlist(message):
    """просто получить вишлист"""
    logger.info(f'list: {message.chat.username}: {message.text}')
    wishlist = Wish.get_all(user_id=message.chat.id)
    logger.debug(f'list: {wishlist}')
    games = [Game.get(id=wish.game_id) for wish in wishlist]
    logger.debug(f'list: games_len — {len(games)}')
    bot.send_message(
        chat_id=message.chat.id,
        text='\n'.join([f'{i}) {game}' for i, game in enumerate(sorted(games, key=lambda x: x.name), start=1)]),
        parse_mode='MARKDOWN'
    )


if __name__ == '__main__':
    bot.polling()
