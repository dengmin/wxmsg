#!/usr/bin/env python3
import shelve
import secrets
import os
from flask import Flask, request, session, render_template
from flask_socketio import SocketIO, emit, join_room
from threading import Lock
from bot import EmotionBot
from logger import logger

app = Flask(__name__)
app.secret_key = os.environ.get('KEY', 'YOUR_SECRET_KEY')
socketio = SocketIO(app)


@app.route('/')
def login():
    if 'sessionID' not in session:
        session['sessionID'] = str(secrets.randbits(256))
    return render_template('index.html')

bots = {}
bot_status_lock = Lock()


def get_logout_callback_by_session_id(sessionID):
    def logout_callback():
        with bot_status_lock:
            with shelve.open('bot_status') as bot_status:
                bot_status[sessionID] = False
        if sessionID in bots:
            logger.info('%s logged out!', bots[sessionID].self.name)
            del bots[sessionID]
        os.remove(sessionID)
        socketio.emit('logout', room=sessionID)
    return logout_callback


@socketio.on('login')
def login():

    def success_ack(bot, sessionID, nickname):
        socketio.emit('success', (dict(bot.core.s.cookies.items()), bot.core.loginInfo['url'], nickname), room=sessionID)

    def background_thread(sid, sessionID):

        def qr_callback(uuid, status, qrcode):
            logger.info('%s %s', uuid, status)
            if status != '408':
                socketio.emit('qr', (uuid, status), room=sessionID)

        def login_callback():
            if hasattr(bots.get(sessionID, None), 'logout'):
                bots[sessionID].logout()

        try:
            bot = EmotionBot(qr_callback=qr_callback, cache_path=sessionID, logout_callback=get_logout_callback_by_session_id(sessionID), login_callback=login_callback)
            bots[sessionID] = bot
            with bot_status_lock:
                with shelve.open('bot_status') as bot_status:
                    bot_status[sessionID] = bot.alive
            logger.info('%s logged in, cache at %s', bot.self.name, sessionID)
            success_ack(bot, sessionID, bot.self.name)
            bot.self_msg()
        except EmotionBot.TimeoutException as e:
            logger.warning('uuid=%s, status=%s, timeout', e.uuid, e.status)
            socketio.emit('qr', (e.uuid, 'timeout'), room=sessionID)

    if 'sessionID' not in session:
        return
    join_room(room=session['sessionID'], sid=request.sid)
    bot = bots.get(session['sessionID'], None)
    if hasattr(bot, 'alive') and bot.alive and hasattr(bot, 'self') and hasattr(bot.self, 'name') and bot.self.name:
        success_ack(bot, request.sid, bot.self.name)
    else:
        socketio.start_background_task(background_thread, sid=request.sid, sessionID=session['sessionID'])



class SessionDeadException(Exception):
    pass


def qr_callback(uuid, status, qrcode):
    if status != 200:
        raise SessionDeadException


with shelve.open('bot_status') as bot_status:
    for sessionID, alive in bot_status.items():
        if alive:
            logger.info('try to log back in %s', sessionID)
            try:
                bot = EmotionBot(timeout_max=0, cache_path=sessionID, qr_callback=qr_callback, logout_callback=get_logout_callback_by_session_id(sessionID))
            except (EmotionBot.TimeoutException, SessionDeadException):
                logger.info('%s log back in failed', sessionID)
                del bot_status[sessionID]
                continue
            bots[sessionID] = bot  # TODO 线程安全问题，用户有可能在此前已经logout
            bot_status[sessionID] = bot.alive
            logger.info('%s logged back in, cache at %s', bot.self.name, sessionID)

if __name__ == '__main__':
    socketio.run(app)
