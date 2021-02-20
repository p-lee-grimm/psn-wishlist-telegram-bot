""" File with basic DB models for the bot"""
from json import loads
from re import fullmatch
from sqlalchemy.exc import IntegrityError
from bs4 import BeautifulSoup as Soup
from requests import get
from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, UniqueConstraint, or_
from sqlalchemy.ext.declarative import declarative_base, AbstractConcreteBase
from sqlalchemy.orm import sessionmaker
from urllib3.util import parse_url
from uuid import uuid4
from contextlib import contextmanager
from datetime import date, datetime as dt

import logging

db = create_engine('sqlite:///psnbot.sqlite', echo=False)
Base = declarative_base(bind=db)
Session = sessionmaker(bind=db)

PSN_URL = 'store.playstation.com'


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class BaseModel(Base, AbstractConcreteBase):
    """ Base model with common methods """
    __abstract__ = True

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))

    @classmethod
    def logger(cls):
        """
        Log a message with a given level 
        """
        logging.basicConfig(
            filename='bot.log',
            filemode='a',
            level=logging.DEBUG,
            format='%(asctime)s.%(msecs)d[%(name)s.%(levelname)s]: '
                   '[%(filename)s:%(lineno)s - %(funcName)20s() ] '
                   '%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        return logging.getLogger(cls.__name__)

    @classmethod
    def get(cls, session: Session, **kwargs):
        """ Get a model object by given parameters """
        cls.logger().info(f'{kwargs}')
        return session.query(cls).filter_by(**kwargs).one_or_none()

    @classmethod
    def get_all(cls, session: Session, **kwargs):
        """ Get all the objects that fits given parameters """
        cls.logger().info(f'{kwargs}')
        return session.query(cls).filter_by(**kwargs).all()

    @classmethod
    def create(cls, session: Session, **kwargs) -> (Base, bool):
        """ Create a model object with given parameters
        :returns tuple with created object and True if the object was created else False
        """
        cls.logger().info(f'{kwargs}')
        instance = session.query(cls).filter_by(**kwargs).one_or_none()
        if not instance:
            instance = cls(**kwargs)
            session.add(instance)
            was_created = True
        else:
            was_created = False
        return instance, was_created

    @classmethod
    def get_or_create(cls, session: Session, **kwargs) -> (Base, bool):
        """
        Query the table using given parameters
        :param session: Session instance
        :param kwargs: specific for each model
        :return: tuple the object of given model with flag if the object was created
        """
        cls.logger().info(f'{cls.__name__}:get_or_create({kwargs})')
        instance = cls.get(session=session, **kwargs)
        if instance:
            return instance, False
        else:
            instance, is_created = cls.create(session=session, **kwargs)
            return instance, is_created

    @classmethod
    def delete(cls, session: Session, **kwargs):
        """
        Deletes an object from database
        :param session: Session instance
        :param kwargs: any possible parameters
        """
        cls.logger().debug(f'{cls}.delete({kwargs})')
        session.query(cls).filter(**kwargs).delete()


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

        Game.logger().info(f'{concept_id, product_id, game_url, store_locale}')
        if not (product_id or concept_id or game_url):
            raise ValueError('There is at least one of concept_id, product_ or game_url arguments needed.')

        if concept_id:
            game_url = f'''https://{PSN_URL}/{store_locale}/concept/{concept_id}'''
        elif product_id:
            game_url = f'''https://{PSN_URL}/{store_locale}/product/{product_id}'''

        game_page = Soup(
            markup=get(url=game_url).text.replace(u'\xa0', u''),
            features='html.parser'
        )

        data = game_page.select_one('div[class="pdp-upsells script"]')
        if data is None:
            data = game_page.select_one('div[class="pdp-cta"] script')
        data = loads(next(data.children))['cache']

        concept_id = concept_id or next(key for key in data if key.startswith('Concept:')).replace('Concept:', '')

        id_name = {
            f'''GameCTA:{
                v.get(
                    'activeCtaId', 
                    v.get('webctas', v['skus'])[0]['__ref'].replace('Sku', '').replace('GameCTA', '')
                )
            }''':
                v.get('edition', v)['name'] for k, v in data.items() \
            if k.startswith('Product')
        }

        id_data = {
            edition_name: {
                'original_price': data[id_]['local']['telemetryMeta']['skuDetail']['skuPriceDetail'][0][
                                      'originalPriceValue'] // 100,
                'sale_price': data[id_]['local']['telemetryMeta']['skuDetail']['skuPriceDetail'][0][
                                  'discountPriceValue'] // 100,
                'valid_until': dt.fromtimestamp(int(data[id_]['price']['endTime'] or 10 ** 14) // 1000),
                'currency': data[id_]['price']['currencyCode']
            } for id_, edition_name in id_name.items() if id_ in data
        }

        concept_info = data[f'Concept:{concept_id}']
        if 'media' not in concept_info:
            concept_info = loads(
                Soup(loads(game_page.select_one('#__NEXT_DATA__').next
                           )['props']['pageProps']['batarangs']['background-image']['text'],
                     'html.parser'
                     ).script.next
            )['cache'][f'Concept:{concept_id}']
        product_info = next(v for k, v in data.items() if k.startswith('Product'))

        game_info = {
            'name': concept_info.get('name', product_info['name']),
            'poster_url': next(x['url'] for x in concept_info['media'] if x['role'] == 'MASTER'),
            'editions': id_data,
            'concept_id': concept_id,
        }

        Game.logger().debug(
            f'''concept_id, poster_url: {concept_id, game_info['poster_url']}''')

        return game_info

    @staticmethod
    def get_or_create(session: Session, **kwargs) -> (BaseModel, bool):
        """
        Check the correctness of game_id and then check if the game exists in the store.
        :param session: Session instance
        :param kwargs: should include game_id param
        :returns Game object and True if it was successfully created else False
        """
        Game.logger().debug(f'({kwargs})')
        game_id = kwargs['game_id']
        if not fullmatch(r'\d+|[\d\w-]+', game_id):
            Game.logger().debug(msg=f'not full matched: {game_id}')
            game_url = parse_url(game_id)
            if game_url.host != PSN_URL or not fullmatch(
                    r'/[a-z\-]+/(concept/\d+|product/[\w\d-]+)',
                    game_url.path):
                raise ValueError(f'''Неверный url. Правильный url выглядит так:
                                 ```
                                 [http(s)://]{PSN_URL}/[локаль магазина вроде ru-ru]/(concept|product)/[идентификатор 
                                 игры] ```''')
            game_id = game_url.path.split('/')[-1]
        if game_id.isnumeric():
            id_type = 'concept_id'
        else:
            id_type = 'product_id'

        game = Game.get(**{id_type: game_id}, session=session)
        if game:
            Game.logger().debug(f'Game.get_or_create game already exists: {game_id, game.name}')
            return game, False
        try:
            game_info = Game.get_game_info(concept_id=game_id) if game_id.isnumeric() \
                else Game.get_game_info(product_id=game_id)
        except (StopIteration, ValueError):
            raise ValueError('Введён несуществующий идентификатор игры. Его можно найти после `/product/` или'
                             '`/concept/` в url на сайте PSN Store')
        Game.logger().debug(f'game_info received: {game_info}')
        game = Game.get(concept_id=game_info.get('concept_id'), session=session)
        if game is None:
            if game_info:
                game, game_was_created = Game.create(
                    product_id=game_info.get('product_id'),
                    concept_id=game_info.get('concept_id'),
                    name=game_info['name'],
                    poster_url=game_info.get('poster_url'),
                    session=session
                )

                Price.update_price(game_id=game.id, game_info=game_info, session=session)
                return game, game_was_created
            else:
                raise ValueError('Введён несуществующий идентификатор игры. Его можно найти после `/product/` или'
                                 f'`/concept/` в url на сайте PSN Store: {PSN_URL}')
        else:
            with session_scope() as sess:
                sess.query(Game).filter(
                    Game.concept_id == game.concept_id
                ).update(
                    {Game.name: min([game.name, game_info.get('name', '')], key=len)}
                )
                return game, False

    def __str__(self):
        return f'[{self.name}](https://store.playstation.com/ru-ru/concept/{self.concept_id}/)'


class Wish(BaseModel):
    """ A record that describes a game that a user wants to purchase """
    __tablename__ = 'wishes'
    user_id = Column(String, ForeignKey('users.id', onupdate="CASCADE", ondelete="CASCADE"))
    game_id = Column(String, ForeignKey('games.id', onupdate="CASCADE", ondelete="CASCADE"))
    gu = UniqueConstraint(game_id, user_id)

    @staticmethod
    def get_or_create(session: Session = None, **kwargs) -> (Base, bool):
        """
        Creates a record in a wishlist of a given user
        :param session: Session instance
        :param kwargs: should include at least user_id (url or concept ID or product ID of the game) and game_id
        :returns (Wish, flag if object was created)
        """
        user_id = kwargs['user_id']
        game_id = kwargs['game_id']
        session = session or Session()
        Game.logger().debug(f'Wish.get_or_create({user_id, game_id})')
        user, is_created = User.get_or_create(id=user_id, session=session)
        game, is_created = Game.get_or_create(game_id=game_id, session=session)
        if game:
            try:
                wish, is_created = Wish.create(user_id=user.id, game_id=game.id, session=session)
            except (IntegrityError,):
                is_created = False
                wish = None
            return wish, is_created
        else:
            return None, False

    @staticmethod
    def delete(session: Session, **kwargs) -> bool:
        """
        Deletes a record from a wishlist by given user_id and game_id
        :param session:
        :param kwargs: should include user_id and game_id
        :return: instance of the game and flag if it was successfully deleted
        """
        user_id = kwargs['user_id']
        game_id = kwargs['game_id']

        user, user_was_created = User.get_or_create(id=user_id, session=session)
        game, game_was_created = Game.get_or_create(game_id=game_id, session=session)
        if not (user_was_created or game_was_created):
            was_deleted = session.query(Wish).filter(Wish.user_id == user.id, Wish.game_id == game.id).delete()
        else:
            was_deleted = None, False
        return was_deleted


class Price(BaseModel):
    """ A record with a price of a game at specific day """
    __tablename__ = 'prices'
    game_id = Column(String, ForeignKey('games.id', onupdate="CASCADE", ondelete="CASCADE"))
    check_date = Column(Date, nullable=False)
    locale = Column(String, default='ru-ru', nullable=False)
    original_price = Column(Integer, nullable=False)
    sale_price = Column(Integer, nullable=True)
    valid_until = Column(Date, nullable=True)
    edition = Column(String, nullable=True)
    currency = Column(String, nullable=True, default='RUB')

    game_date_locale_edition = UniqueConstraint(game_id, check_date, locale, edition)

    @staticmethod
    def update_price(game_id: str, session: Session, locale: str = 'ru-ru', game_info: dict = None):
        """
        Get current price of a given game
        :param session: Session instance
        :param game_info: dict with game info if already uploaded, empty by default
        :param locale: locale of the shop, ru-ru as default
        :param game_id: game ID
        """
        Price.logger().info(f'{game_id, locale, game_info}')

        game = Game.get(session=session, id=game_id)
        game_info = game_info or Game.get_game_info(concept_id=game.concept_id, store_locale=locale)
        common_game_info = dict(
            game_id=game_id,
            check_date=date.today(),
            locale=locale,
        )
        print(game_info)
        for edition_name, edition_info in game_info['editions'].items():
            print(edition_info, common_game_info)
            price_record = Price(edition=edition_name, **edition_info, **common_game_info)
            session.merge(price_record)

    @staticmethod
    def update_prices():
        """
        Update all prices of the games that have non-actual prices
        """
        Game.logger().info('nothing special')
        with session_scope() as sess:
            for game_id, in sess.query(Game).outerjoin(Price).filter(
                    or_(
                        Price.check_date < date.today(),
                        Price.check_date == None
                    )
            ).distinct().values(Game.id):
                print(game_id)
                Price.update_price(game_id=game_id, session=sess)
        print('''That's all!''')


BaseModel.metadata.create_all(db)
