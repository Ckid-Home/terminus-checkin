"""Terminus Checkin
"""
import logging
import sys
from asyncio import sleep
from typing import Any
from telethon import TelegramClient, events
from telethon.tl.custom.message import Message
from telethon.errors.rpcerrorlist import PhoneNumberInvalidError, FloodWaitError
import ddddocr


BOT_USERNAME = 'EmbyPublicBot'


class Checkin():
    '''Terminus Checkin'''
    CHECKIN_MESSAGE = '/checkin'
    CANCEL_MESSAGE = '/cancel'

    @staticmethod
    def add_event_handler(client: TelegramClient, checkin: object):
        '''Add instace checkin event handler to client'''
        for attr in dir(checkin):
            if attr.startswith('_checkin_') and callable(getattr(checkin, attr)):
                client.add_event_handler(getattr(checkin, attr))

    @staticmethod
    def parse_image(img: bytes) -> str:
        '''Parse checkin image'''
        ocr = ddddocr.DdddOcr(show_ad=False)
        res = ocr.classification(img)
        return res

    @staticmethod
    def get_logger(name: str):
        '''Return a logger'''
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        return logger

    def __init__(self, name: str, app_id: int, app_hash: str,
                 proxy: tuple | dict | None = None):
        self._timeout = 15
        self._retry_interval = 15
        self._max_retry = 3
        self._retry_count = 0
        self.logger = self.get_logger('Checkin')
        client = TelegramClient(f'sessions/{name}', app_id,
                                app_hash, proxy=proxy)  # type: ignore
        # client.add_event_handler(self.test)
        self.add_event_handler(client, self)
        self.client = client

    def start(self):
        '''Run checkin'''
        self.client.loop.run_until_complete(self._start())

    async def _start(self):
        self.logger.info('Checkin start')
        try:
            async with self.client:
                self.logger.info('Telegram authed')
                await self._checkin()
        except KeyboardInterrupt:
            print('\n')
            self.logger.warning('Stop by user')
        except EOFError:
            print('\n')
            self.logger.warning('Stop by system')
        except Exception as error:
            self.logger.error(error)
        finally:
            self.logger.info('Checkin end')

    async def _retry(self):
        if self._retry_count < self._max_retry:
            self.logger.info('Wait %ss to retry', self._retry_interval)
            await sleep(self._retry_interval)
            self._retry_count -= 1
            self.logger.info('The %s retry start', self._retry_count)
            await self._checkin()
        else:
            self.logger.error('Max retry occured!')

    async def _checkin(self):
        '''Start checkin by cancel any existed session'''
        await self._cancel()
        # wait for events
        await sleep(self._timeout)

    async def _cancel(self):
        '''Send cancel message'''
        self.logger.info('Send cancel message')
        await self.client.send_message(BOT_USERNAME, self.CANCEL_MESSAGE)

    @events.register(events.NewMessage(chats=BOT_USERNAME, pattern='.*(会话已取消|无需清理)'))
    async def _checkin_start(self, event: events.NewMessage.Event):
        self.logger.info('Recive session clear message')
        self.logger.info('Send checkin message')
        await event.message.respond(self.CHECKIN_MESSAGE)

    @events.register(events.NewMessage(chats=BOT_USERNAME, pattern='.*输入签到验证码'))
    async def _checkin_verify(self, event: events.NewMessage.Event):
        '''Handle checkin verify'''
        self.logger.info('Recive captcha message')
        message: Message = event.message
        image = await message.download_media(file=bytes)
        if image:
            self.logger.info('Captcha image found')
            text = await self._async_parse_image(image)
            self.logger.info('Captcha recongized')
            self.logger.info('Send captcha verify message')
            await message.respond(text)
        else:
            self.logger.error('Captcha image not found!')
            await self._retry()

    async def _async_parse_image(self, img: bytes) -> str:
        self.logger.debug('Image parsing')
        res = await self.client.loop.run_in_executor(None, self.parse_image, img)
        self.logger.debug('Image recongize as %s', res)
        return res

    @events.register(events.NewMessage(chats=BOT_USERNAME, pattern='.*签到验证码输入错误或超时'))
    async def _checkin_failed(self, event: events.NewMessage.Event):
        '''Handle checkin failed'''
        self.logger.info('Checkin failed')
        await self._retry()

    @events.register(events.NewMessage(chats=BOT_USERNAME, pattern='.*你今天已经签到过了'))
    async def _checkin_already(self, event: events.NewMessage.Event):
        '''Handle checkin already'''
        self.logger.info('Checkin already')

    @events.register(events.NewMessage(chats=BOT_USERNAME, pattern='.*签到成功'))
    async def _checkin_succeed(self, event: events.NewMessage.Event):
        '''Handle checkin succeed'''
        self.logger.info('Checkin succeed')


if __name__ == '__main__':
    args: list[Any] = sys.argv[1:]
    argc = len(args)
    if argc == 3:
        args.append(None)
    elif argc == 4:
        pass
    else:
        print(f'Arguments number must be 3 or 4, but got {argc}')
        print('Usage: python checkin.py name api_id api_hash [proxy]')
        sys.exit(1)

    name, api_id, api_hash, proxy = args

    api_id = int(api_id, 10)

    if proxy:
        # proxy string must split with colon
        # socks5:127.0.0.1:80
        # socks5:127.0.0.1:80:username:password:rdns
        proxy = proxy.split(':')
        proxyc = len(proxy)
        if proxyc < 3 or proxyc > 5:
            print('Proxy string incomplete')
            sys.exit(1)
        proxy[2] = int(proxy[2])
        if len(proxy) == 5:
            proxy[4] = not bool(proxy[4].lower() == 'false')
        proxy = tuple(proxy)

    Checkin(name, api_id, api_hash, proxy=proxy).start()
