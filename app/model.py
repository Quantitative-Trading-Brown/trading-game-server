import enum

from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_redis import FlaskRedis

db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins=["https://simulator.qtab.site", "http://localhost:3000", "http://10.37.28.67:3000"])
redis_client = FlaskRedis(decode_responses=True)

class GameStatus(enum.Enum):
    LOBBY = 0
    ACTIVE = 1
    ENDED = 2

class Game(db.Model):
    gid = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10))
    status = db.Column(db.Enum(GameStatus))
    token = db.Column(db.String(100))

    trades = db.relationship('Trade', backref="game")
    players = db.relationship('Player', backref="game")

class Player(db.Model):
    pid = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(1000))
    game_id = db.Column(db.Integer, db.ForeignKey('game.gid'))
    token = db.Column(db.String(100))

class Trade(db.Model):
    tid = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.gid'))

    buyer_id = db.Column(db.Integer, db.ForeignKey('player.pid'))
    seller_id = db.Column(db.Integer, db.ForeignKey('player.pid'))

    buyer = db.relationship("Player", backref="buyer", uselist=False, foreign_keys=[buyer_id])
    seller = db.relationship("Player", backref="seller", uselist=False, foreign_keys=[seller_id])


    price = db.Column(db.Double)
    amount = db.Column(db.Double)
