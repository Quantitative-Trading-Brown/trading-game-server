import random
import string
import secrets
import binascii

from flask import Blueprint, request, jsonify
from .model import GameStatus, Game, Player
from .model import redis_client

login = Blueprint('login', __name__)

def generate_code(length=1):
    """Generate a random alphanumeric game code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode('utf-8')

@login.route('/create-game', methods=['POST'])
def create_game():
    game_codes = redis_client.hgetall("codes")

    code = generate_code()
    # Check if game code exists
    while code in game_codes:
        code = generate_code()

    game_id = redis_client.incr("game_count")
    admin_token = generate_token(prefix=f"admin-{game_id}-")

    redis_client.hset("codes", code, game_id)
    redis_client.hset(f"game:{game_id}", "code", code)
    redis_client.hset(f"admin_tokens", game_id, admin_token)
    redis_client.set(f"game:{game_id}:state", 0)

    return jsonify({"code": code, "token": admin_token}), 201

@login.route('/join-game', methods=['POST'])
def join_game():
    game_codes = redis_client.hgetall("codes")

    data = request.json
    code = data.get('code')
    username = data.get('playerName')

    # Check if game exists in database
    game_id = game_codes.get(code)

    if game_id is None:
        return jsonify({"error": "Game not found"}), 404

    # Check if username is empty
    if not username:
        return jsonify({"error": "Username cannot be empty"}), 400

    # Check if player name exists
    usernames = [redis_client.hget(f"user:{player_id}", "username") for player_id 
               in redis_client.zrange(f"game:{game_id}:users", 0, -1)]

    if username in usernames:
        return jsonify({"error": "Player name already exists"}), 400


    player_id = redis_client.incr("player_count")
    player_token = generate_token(prefix=f"player-{player_id}-")

    redis_client.hset(f"user:{player_id}", "username", username)
    redis_client.hset(f"user:{player_id}", "game_id", game_id)
    redis_client.hset(f"player_tokens", player_id, player_token)
    redis_client.zadd(f"game:{game_id}:users", {str(player_id): 0})
    
    return jsonify({"message": "Joined successfully", 
                    "token": player_token}), 200
