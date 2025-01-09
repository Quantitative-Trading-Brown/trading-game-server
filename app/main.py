import random
import string
import secrets
import binascii

from flask import Blueprint, request, jsonify
from .model import GameStatus, Game, Player, db

main = Blueprint('main', __name__)

def generate_code(length=6):
    """Generate a random alphanumeric game code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode('utf-8')

@main.route('/create-game', methods=['POST'])
def create_game():
    cur_games = Game.query.filter(
        Game.status.in_([GameStatus.LOBBY, 
                         GameStatus.ACTIVE])).all()

    code = generate_code()
    # Check if game code in SQL database
    while code in [g.code for g in cur_games]:
        code = generate_code()


    # Return the code and token
    new_game = Game(code=code, status=GameStatus.LOBBY)
    db.session.add(new_game)
    db.session.commit()

    new_game.token = generate_token(prefix=f"{new_game.gid}-")
    db.session.commit()

    return jsonify({"code": code, "token": new_game.token}), 201

@main.route('/join-game', methods=['POST'])
def join_game():
    cur_games = Game.query.filter(
        Game.status.in_([GameStatus.LOBBY, 
                         GameStatus.ACTIVE])).all()

    data = request.json
    code = data.get('code')
    username = data.get('playerName')

    # Check if game exists in database
    gids = [g.gid for g in cur_games if g.code == code]
    if not gids:
        return jsonify({"error": "Game not found"}), 404
    gid = gids[0]

    # Check if username is empty
    if not username:
        return jsonify({"error": "Username cannot be empty"}), 400

    # Check if player name exists
    player = Player.query.filter_by(username=username, game_id=gid).first()
    if player:
        return jsonify({"error": "Player name already exists"}), 400

    new_user = Player(username=username, game_id=gid)
    db.session.add(new_user)
    db.session.commit()

    new_user.token = generate_token(prefix=f"{new_user.pid}-")
    db.session.commit()
    
    return jsonify({"message": "Joined successfully", 
                    "token": new_user.token}), 200
