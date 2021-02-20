""" Script for launching the bot """
from telebot import TeleBot, types
from app.models import Game, Wish, Price, PSN_URL, session_scope
from PIL import Image
from io import BytesIO
from requests import get
from urllib.parse import quote

import logging

logging.basicConfig(
    filename='top_bot.log',
    filemode='a',
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)d[%(name)s.%(levelname)s]: '
           '[%(filename)s:%(lineno)s - %(funcName)20s() ] '
           '%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('toplevel')

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


@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    """ Greeting message """
    bot.send_message(message.chat.id, f'Привет, я бот для твоего вишлиста в [Sony PlayStation Store]({PSN_URL}). Ты '
                                      'можешь кидать мне ссылки на игры, которые ты хочешь когда-нибудь купить, '
                                      'а я пришлю тебе сообщение, если на какие-то из них будут скидки.'
                                      '\nСписок доступных команд:'
                                      '\n\n/help — увидеть это сообщение'
                                      f'\n\n/add — {add_game.__doc__}'
                                      f'\n\n/del — {del_game.__doc__}'
                                      f'\n\n/list — {get_wishlist.__doc__}', parse_mode='MARKDOWN'
                     )


@bot.message_handler(commands=['add'])
def add_game(message):
    """ добавить игру в вишлист, пример:
`/add https://store.playstation.com/ru-ru/concept/10000237`
или
`/add 10000237`
добавить в вишлист Assassin's Creed Valhalla """
    try:
        with session_scope() as session:
            wish, is_created = Wish.get_or_create(user_id=message.chat.id,
                                                  game_id=message.text.split(' ', maxsplit=1)[1],
                                                  session=session)
            game = Game.get(id=wish.game_id, session=session)
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
        with session_scope() as session:
            game, game_is_new = Game.get_or_create(game_id, session=session)
            was_deleted = Wish.delete(user_id=message.chat.id, game_id=game_id, session=session)
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
    with session_scope() as session:
        wishlist = Wish.get_all(user_id=message.chat.id, session=session)
        games = [Game.get(id=wish.game_id, session=session) for wish in wishlist]
        if games:
            response = '\n'.join([
                f'{i}) {game}' for i, game in enumerate(sorted(games, key=lambda x: x.name), start=1)
            ])
        else:
            response = 'Твой вишлист пуст :('
        bot.send_message(
            chat_id=message.chat.id,
            text=response,
            parse_mode='MARKDOWN'
        )


@bot.inline_handler(func=lambda query: len(query.query) > 2)
def search_game_from_store(inline_query):
    """
    inline-метод, который позволяет искать игры в PSN
    :param inline_query: текст
    """

    def has_sale_price(game_data: dict):
        """
        Возвращает True, если на игру действует скидка
        :param game_data:
        :return:
        """
        logger.info('')
        try:
            return game_data['default_sku']['rewards'][0] is not None
        except Exception:
            return False

    logger.info('inline: start')
    psn_url = f'https://store.playstation.com/store/api/chihiro/00_09_000/tumbler/ru/ru/999/' \
              f'{quote(inline_query.query)}?size=5&start=0&gameContentType=bundles&platform=ps4'
    logger.info(psn_url)
    search_data = get(psn_url).json()
    try:
        games = [
            {
                'name': game['name'],
                'url': f'''https://store.playstation.com/ru-ru/product/{game['id']}''',
                'price': game['default_sku']['display_price'],
                'sale_price': game['default_sku']['rewards'][0]['bonus_price'] // 100 if has_sale_price(game) else None,
                'valid_until': game['default_sku']['rewards'][0]['end_date'] if has_sale_price(game) else None,
                'img_url': game['images'][0]['url']
            } for game in search_data['links']
        ]
        bot.answer_inline_query(
            inline_query_id=inline_query.id,
            results=[
                types.InlineQueryResultPhoto(
                    id=i,
                    title=game['name'],
                    photo_url=game['img_url'],
                    thumb_url=game['img_url'],
                    caption=f'''[{game['name']}]({game['url']}): ''' +
                            (f'''~~{game['price']}~~ {game['sale_price']} till {game['valid_until']}''' \
                                 if game['sale_price'] else f'''{game['price']}'''),
                    parse_mode='MARKDOWN',
                    input_message_content=types.InputMediaPhoto(caption=str(game),
                                                                parse_mode='MARKDOWN',
                                                                media=get_image_bytes(game['img_url'])),
                ) for i, game in enumerate(games)
            ],
            switch_pm_text='Добавить игр?',
            switch_pm_parameter='start'
        )
    except Exception as e:
        print(e)


@bot.inline_handler(func=lambda query: query == ' ')
def watch_wishlist_inline(chosen_inline_result):
    """
    inline-метод, позволяющий публиковать в чате игры из своего вишлиста
    :param chosen_inline_result: пустая строка
    """
    print('общий инлайнер')
    try:
        with session_scope() as session:
            wishes = Wish.get_all(user_id=chosen_inline_result.from_user.id, session=session)
            games = [Game.get(id=wish.game_id, session=session) for wish in wishes]

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
                switch_pm_parameter='start'
            )
    except Exception as e:
        print(e)


if __name__ == '__main__':
    try:
        bot.polling()
    except Exception as e:
        bot.send_message(chat_id='91717534', text='Шеф, всё упало!')
        print(e)
