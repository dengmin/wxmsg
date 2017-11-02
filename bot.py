# coding: utf-8
import threading
import shelve
from wxpy import *
from threading import Lock
from logger import logger

settings_lock = Lock()

sendmsg2 = '''萤火虫舞蹈工作室新店开业啦，开业活动优惠到底
⭕活动期间新生报名可享受原价380元，现价99元的超级优惠活动（活动仅限前100个名额）
⭕报名99特价月卡者，只要开卡当月坚持上完8个课时，没有落下课程者，可赠送一张月卡
⭕五人同行，一人免单
⭕活动月卡可抵用年卡免费299元
📣📣📣📣活动时间
2017年11月1号到2017年11月20号
只有100个名额哦，这么优惠还不赶紧来嗨[悠闲][悠闲]
报名咨询电话，陆老师:‭136 7719 5024 ‬五堰校区'''

class BotSetting:
    suffix_reply = True
    at_reply = False

class EmotionBot(Bot):
    class TimeoutException(Exception):
        def __init__(self, uuid, status):
            self.uuid = uuid
            self.status = status

    def __init__(self, name=None, need_login=True, timeout_max=15, qr_callback=None, *args, **kwargs):
        self.name = name
        self.timeout_count = 0  # QR code timeout count
        self.setting = None
        if need_login:
            self.login(timeout_max=timeout_max, qr_callback=qr_callback, *args, **kwargs)

    def login(self, timeout_max=15, qr_callback=None, *args, **kwargs):
        def _qr_callback(uuid, status, qrcode):
            if status == '408':
                self.timeout_count += 1
                if self.timeout_count > timeout_max:
                    raise self.TimeoutException(uuid, status)
            elif status == '400':  # exit thread when time out at QR code waiting for scan
                raise self.TimeoutException(uuid, status)
            if callable(qr_callback):
                qr_callback(uuid, status, qrcode)

        super().__init__(qr_callback=_qr_callback, *args, **kwargs)

    def self_msg(self):
        try:
            fs = self.friends()
            for x in fs:
                x.send_msg(sendmsg2)
        except:
            pass


class SyncEmotionBot(EmotionBot):
    def __init__(self, need_login=True, *args, **kwargs):
        super().__init__(need_login=False, *args, **kwargs)
        self.uuid_lock = threading.Event()
        self.login_lock = threading.Event()
        self.timeout_count = 0  # QR code timeout count
        self.thread = None

        if need_login:
            self.login(*args, **kwargs)

    def login(self, qr_callback=None, *args, **kwargs):
        def _qr_callback(uuid, status, qrcode):
            if status == '0':
                self.uuid = uuid
                self.uuid_lock.set()
            if callable(qr_callback):
                qr_callback(uuid, status, qrcode)

        kwargs.update(qr_callback=_qr_callback)
        self.thread = threading.Thread(target=self._login_thread, args=args, kwargs=kwargs)
        self.thread.start()
        self.uuid_lock.wait()  # lock release when QR code uuid got
        return self.uuid

    def _login_thread(self, *args, **kwargs):
        try:
            super().login(*args, **kwargs)
        except self.TimeoutException as e:
            logger.warning('uuid=%s, status=%s, timeout', e.uuid, e.status)
            return
        self.login_lock.set()

    def is_logged(self, timeout=None):
        return self.login_lock.wait(timeout)

