from flask import Blueprint, request, jsonify
from .model import GameStatus, Game
from .model import socketio, db, redis_client
import click

game = Blueprint('game', __name__)

@socketio.on("message", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients."""
    socketio.emit("message", "[admin] " + message, namespace="/admin")
    socketio.emit("message", "[admin] " + message, namespace="/player")
    print("Message broadcasted.")

@socketio.on("buy", namespace="/player")
def buy(price, amount):
    socketio.emit("update", price, namespace="/player")
    socketio.emit("update", price, namespace="/admin")

    message = str(redis_client.get(request.sid)) + f" bought {amount} at {price}"
    socketio.emit("message", message, namespace="/admin")

@socketio.on("sell", namespace="/player")
def sell(price, amount):
    message = str(redis_client.get(request.sid)) + f" sold {amount} at {price}"
    socketio.emit("message", message, namespace="/admin")

@socketio.on("cancel", namespace="/player")
def cancel(price):
    message = str(redis_client.get(request.sid)) + f" canceled orders at {price}"
    socketio.emit("message", message, namespace="/admin")

@socketio.on("cancel_all", namespace="/player")
def kill():
    message = str(redis_client.get(request.sid)) + " canceled everything"
    socketio.emit("message", message, namespace="/admin")
