""" File with basic DB models for the bot"""
from json import loads
from re import fullmatch
from sqlite3 import Error
from bs4 import BeautifulSoup as Soup
from requests import get
from sqlalchemy import create_engine, Column, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base, AbstractConcreteBase
from sqlalchemy.orm import sessionmaker
from urllib3.util import parse_url
from uuid import uuid4

import logging

db = create_engine('sqlite:///psnbot.sqlite', echo=True)
Base = declarative_base(bind=db)
Session = sessionmaker(bind=db)


class BaseModel(Base, AbstractConcreteBase):
    """ Base model with common methods """
    __abstract__ = True

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))

    @classmethod
    def get(cls, **kwargs):
        """ Get a model object by given parameters """
        logging.info(f'{cls.__name__}.get({kwargs})')
        session = Session()
        return session.query(cls).filter_by(**kwargs).one_or_none()

    @classmethod
    def create(cls, **kwargs: object) -> (Base, bool):
        """ Create a model object with given parameters
        """
        logging.info(f'{cls.__name__}.create({kwargs})')
        session = Session()
        try:
            instance = cls(**kwargs)
            session.add(instance)
            session.commit()
            return instance, True
        except Error:
            session.rollback()
            instance = session.query(cls).filter_by(**kwargs).one()
            return instance, False

    @classmethod
    def get_or_create(cls, **kwargs) -> (Base, bool):
        """
        Query the table using given parameters
        :param kwargs: any parameters supported for given model
        :return: tuple the object of given model with flag if the object was created
        """
        logging.info(f'{cls.__name__}:get_or_create({kwargs})')
        instance = cls.get(**kwargs)
        if instance:
            return instance, False
        else:
            instance, is_created = cls.create(**kwargs)
            return instance, is_created

    @classmethod
    def delete(cls, **kwargs) -> (Base, bool):
        """
        Deletes an object from database
        :param kwargs: any possible parameters
        :return: deleted object and True if it was successfully deleted else None and False
        """
        logging.info(f'{cls.__name__}.delete({kwargs})')
        session = Session()
        try:
            instance = cls.get(**kwargs)
            session.delete(instance)
            session.commit()
            return instance, True
        except Error:
            session.rollback()
            return None, False


class User(BaseModel):
    """ A user of the bot """
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=True)


class Game(BaseModel):
    """ A game from PSN """
    __tablename__ = 'games'
    name = Column(String, unique=False, nullable=False)
    concept_id = Column(String, unique=True, nullable=True)
    product_id = Column(String, unique=True, nullable=True)
    poster_url = Column(String, unique=False, nullable=True)

    @staticmethod
    def get_game_info(concept_id: str = None, product_id: str = None, game_url: str = None,
                      store_locale='ru-ru') -> dict:
        """
        Parse game info from PSN store.
        :param product_id: product ID (required if concept_id and game_url aren't provided)
        :param concept_id: concept ID (required if product_id and game_url aren't provided)
        :param game_url: url of the game in the PSN store (required if game_id isn't provided)
        :param store_locale: str, russian store is default
        :returns dict with information about a game from PSN store or None if the game does not exist
        """

        def get_poster_url(html_page: Soup) -> tuple[str, str, str]:
            """
            Get game poster's url, product and concept IDs.
            :param html_page: BeautifulSoup, parsed as BeautifulSoup page
            :return: tuple (concept_id, product_id and banner_url)
            """
            logging.info(f'Game.get_game_info.get_poster_url({html_page.select_one("title").text})')
            scripts = html_page.select('script[type="application/json"]')
            scripts = [loads(script.contents[0]) for script in scripts]
            game_concept_id = ''
            game_product_id = ''
            media = []
            for script in scripts:
                args = script.get('args', [])
                if 'conceptId' in args:
                    game_concept_id = args['conceptId']
                    game_product_id = script['cache'][next(k for k in script['cache'] if k.startswith('Product:'))][
                        'id']
                    media = script['cache'][f'Product:{game_product_id}']['media']
                elif 'productId' in args:
                    game_product_id = args['productId']
                    game_concept_id = script['cache'][next(k for k in script['cache'] if k.startswith('Concept:'))][
                        'id']
                    media = script['cache'][f'Concept:{game_concept_id}']['media']
                else:
                    continue
                break

            return game_concept_id, game_product_id, next(
                image for image in media if image['type'] == 'IMAGE' and image['role'] == 'MASTER'
            )['url']

        logging.info(f'Game.get_game_info({concept_id, product_id, game_url, store_locale})')
        if not (product_id or concept_id or game_url):
            raise ValueError('There is at least one of concept_id, product_ or game_url arguments needed.')

        if concept_id:
            game_url = f'''https://store.playstation.com/{store_locale}/concept/{concept_id}'''
        elif product_id:
            game_url = f'''https://store.playstation.com/{store_locale}/product/{product_id}'''

        game_page = Soup(
            markup=get(url=game_url).text.replace(u'\xa0', u''),
            features='html.parser'
        )
        try:
            concept_id, product_id, poster_url = get_poster_url(html_page=game_page)
            game_info = {
                'product_id': product_id,
                'concept_id': concept_id,
                'valid_until': game_page.select('span[class*="psw-body-2"]')[1].text,
                'discount_info': game_page.select('span[class*="psw-body-2"]')[0].text,
                'name': game_page.select_one('h1').text,
                'poster_url': poster_url,
                'sale_price': game_page.select_one('div[data-mfe-name="ctaWithPrice"] span[class*="psw-h3"]').text,
                'original_price': game_page.select_one('div[data-mfe-name="ctaWithPrice"] span[class*="psw-h4"]').text,
                'editions': [
                    {
                        'edition': edition_description.select_one('h3').text,
                        'sale_price': edition_description.select_one('span[class*="psw-h3"]').text,
                        'original_price': edition_description.select_one('span[class*="psw-h4"]').text
                    } for edition_description in game_page.select('article[class*="psw-cell"]')
                ]
            }
        except (IndexError, StopIteration):
            return {}
        return game_info

    @staticmethod
    def get_or_create(game_id: str) -> (Base, bool):
        """
        Check the correctness of game_id and then check if the game exists in the store.
        :param game_id: url of the game or game ID from PSN store
        """
        logging.info(f'Game.get_or_create({game_id})')

        if not fullmatch(r'\d+|[\d\w-]+', game_id):
            game_url = parse_url(game_id)
            if game_url.host != 'store.playstation.com' or not fullmatch(
                    r'/[a-z\-]+/(concept/\d+|product/[\w\d-]+)',
                    game_url.path):
                raise ValueError('''Неверный url. Правильный url выглядит так:
                                 ```
                                 [http(s)://]store.playstation.com/{\
                                 локаль магазина вроде ru-ru}/(concept|product)/{идентификатор игры}
                                 ```''')
            game_id = game_url.path.split('/')[-1]
        if game_id.isnumeric():
            id_type = 'concept_id'
        else:
            id_type = 'product_id'

        game = Game.get(**{id_type: game_id})
        if game:
            return game, False

        game_info = Game.get_game_info(concept_id=game_id) if game_id.isnumeric() \
            else Game.get_game_info(product_id=game_id)

        if game_info:
            game, is_created = Game.create(
                product_id=game_info.get('product_id'),
                concept_id=game_info.get('concept_id'),
                name=game_info['name'],
                poster_url=game_info.get('poster_url')
            )
            return game, is_created
        else:
            raise ValueError('Введён несуществующий идентификатор игры. Его можно найти после `/product/` или'
                             '`/concept/` в url на сайте PSN Store')


class Wish(BaseModel):
    """ A record that describes a game that a user wants to purchase """
    __tablename__ = 'wishes'
    user_id = Column(String, ForeignKey('users.id'))
    game_id = Column(String, ForeignKey('games.id'))

    @staticmethod
    def get_or_create(user_id: str, game_id: str) -> (Base, bool):
        """
        Creates a record in a wishlist of a given user
        :param user_id: user ID
        :param game_id: product ID or concept ID or game url
        :returns (Wish, flag if object was created)
        """
        logging.info(f'Wish.get_or_create({user_id, game_id})')
        user, is_created = User.get_or_create(id=user_id)
        game, is_created = Game.get_or_create(game_id=game_id)
        if game:
            wish, is_created = Wish.create(user_id=user.id, game_id=game.id)
            return wish, is_created
        else:
            return None, False

    @staticmethod
    def delete(user_id: str, game_id: str) -> (Game, bool):
        """
        Deletes a record from a wishlist by given user_id and game_id
        :param user_id: user ID
        :param game_id: url of the game or its concept ID or product ID
        :return: instance of the game and flag if it was successfully deleted
        """
        user, user_was_created = User.get_or_create(id=user_id)
        game, game_was_created = Game.get_or_create(game_id=game_id)
        if not (user_was_created and game_was_created):
            _, was_deleted = BaseModel.delete(cls=Wish, user_id=user.id, game_id=game.id)
        else:
            _, was_deleted = None, False
        return game, was_deleted


BaseModel.metadata.create_all(db)
