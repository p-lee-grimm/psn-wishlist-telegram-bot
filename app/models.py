""" File with basic DB models for the bot"""

from sqlalchemy import create_engine, Column, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

db = create_engine('sqlite:///psnbot.sqlite', echo=True)
Base = declarative_base()


class User(Base):
    """ A user of the bot """
    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True)


class Game(Base):
    """ A game from PSN """
    id = Column(String, primary_key=True)
    name = Column(String, unique=False, nullable=False)


class Wish(Base):
    """ A record that describes a game that a user wants to purchase """
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('User.id'))
    game_id = Column(String, ForeignKey('Game.id'))
