import random
import string
import secrets
import binascii

from typing import Awaitable
from flask import Blueprint, request, jsonify
from .utils import r

lobby_manager = Blueprint("lobby_manager", __name__)


def generate_code(length=6):
    """Generate a random alphanumeric game code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode("utf-8")


@lobby_manager.route("/create-game", methods=["POST"])
def create_game():
    game_codes = r.hgetall("codes")
    assert not isinstance(game_codes, Awaitable)

    code = generate_code()
    # Check if game code exists
    while code in game_codes:
        code = generate_code()

    game_id = r.incr("game_count")
    admin_token = generate_token(prefix=f"admin-{game_id}-")

    r.hset("codes", code, str(game_id))
    r.hset(f"game:{game_id}", "code", code)
    r.hset(f"admin_tokens", str(game_id), admin_token)
    r.set(f"game:{game_id}:state", 0)

    return jsonify({"code": code, "token": admin_token}), 201


@lobby_manager.route("/join-game", methods=["POST"])
def join_game():
    game_codes = r.hgetall("codes")
    assert not isinstance(game_codes, Awaitable)

    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 404

    code = data.get("code")
    username = data.get("playerName")

    # Check if game exists in database
    game_id = game_codes.get(code)

    if game_id is None:
        return jsonify({"error": "Game not found"}), 404

    # Check if username is empty
    if not username:
        return jsonify({"error": "Username cannot be empty"}), 400

    # Check if player name exists
    player_ids = r.zrange(f"game:{game_id}:users", 0, -1)
    assert not isinstance(player_ids, Awaitable)

    usernames = [r.hget(f"user:{player_id}", "username") for player_id in player_ids]

    if username in usernames:
        return jsonify({"error": "Player name already exists"}), 400

    player_id = r.incr("player_count")
    player_token = generate_token(prefix=f"player-{player_id}-")

    r.hset(f"user:{player_id}", "username", username)
    r.hset(f"user:{player_id}", "game_id", game_id)
    r.hset(f"player_tokens", str(player_id), player_token)
    r.zadd(f"game:{game_id}:users", {str(player_id): 0})

    return jsonify({"message": "Joined successfully", "token": player_token}), 200
