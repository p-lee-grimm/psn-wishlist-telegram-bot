""" Script for launching the bot """
from telebot import TeleBot, types
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


def get_image_bytes(img_url: str) -> BytesIO:
    """
    Get image by url and make a BytesIO object with it
    :param img_url:
    :returns BytesIO object
    """
    image_content = get(img_url).content
    image = Image.open(BytesIO(image_content))
    image_content = BytesIO()
    image.seek(0)
    image.save(image_content, format='JPEG')
    image_content.seek(0)
    return image_content


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
            bot.send_photo(chat_id=message.chat.id,
                           photo=get_image_bytes(game.poster_url),
                           parse_mode='MARKDOWN',
                           caption=response)
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
    wishlist = Wish.get_all(user_id=message.chat.id)
    games = [Game.get(id=wish.game_id) for wish in wishlist]
    if games:
        response = '\n'.join([f'{i}) {game}' for i, game in enumerate(sorted(games, key=lambda x: x.name), start=1)])
    else:
        response = 'Твой вишлист пуст :('
    bot.send_message(
        chat_id=message.chat.id,
        text=response,
        parse_mode='MARKDOWN'
    )


@bot.inline_handler(func=lambda query: True)
def watch_wishlist_inline(chosen_inline_result):
    """
    Inline
    :param chosen_inline_result:
    """
    try:
        wishes = Wish.get_all(user_id=chosen_inline_result.from_user.id)
        games = [Game.get(id=wish.game_id) for wish in wishes]

        bot.answer_inline_query(
            inline_query_id=chosen_inline_result.id,
            results=[
                types.InlineQueryResultPhoto(
                    id=game.id,
                    title=game.name,
                    photo_url=game.poster_url,
                    thumb_url=game.poster_url,
                    caption=str(game),
                    parse_mode='MARKDOWN',
                    input_message_content=types.InputMediaPhoto(caption=str(game),
                                                                parse_mode='MARKDOWN',
                                                                media=get_image_bytes(game.poster_url)),
                ) for i, game in enumerate(sorted(games, key=lambda x: x.name))],
            switch_pm_text='Добавить игр?',
            switch_pm_parameter=''
        )
    except Exception as e:
        print(e)


if __name__ == '__main__':
    bot.polling()
