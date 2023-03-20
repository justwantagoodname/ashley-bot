import aiohttp
import openai
from aiohttp import ClientSession
from aiohttp_proxy import ProxyConnector, ProxyType
from alicebot import Plugin
from alicebot.adapter.mirai.message import MiraiMessageSegment as Message
from alicebot.exceptions import GetEventTimeout

from plugins.ChatGPT.config import config


def fromMirai(event):
    return event.adapter.name == 'mirai'


def isBotCalled(event) -> bool:
    for msg in event.message:
        if msg.type == 'At' and msg['target'] == 2801155976:
            return True
    return False


def isWorkingGroup(event) -> bool:
    return event.sender.group.id in config['Group']


class DrawBotPlugin(Plugin):
    priority: int = 0
    block: bool = True

    async def handle(self) -> None:
        prompt: str = self.event.message.get_plain_text()
        prompt = prompt.strip().lstrip('/draw').strip()
        if prompt:
            await self.drawAI(prompt)
            return

        msg = [Message.at(self.event.sender.id), Message.plain(" Prompt: ")]
        await self.event.reply(msg)
        try:
            prompt = await self.event.adapter.get(
                lambda e: e.sender.group.id == self.event.sender.group.id and isBotCalled(
                    e) and e.sender.id == self.event.sender.id,
                timeout=60
            )
        except GetEventTimeout:
            return
        else:
            await self.drawAI(
                prompt.get_plain_text()
            )

    async def drawAI(self, prompt):
        connector = ProxyConnector(
            proxy_type=ProxyType.SOCKS5,
            host='127.0.0.1',
            port=1080,
            rdns=True
        )
        timeout = aiohttp.ClientTimeout(total=60)
        openai.aiosession.set(ClientSession(timeout=timeout, connector=connector))
        try:
            image_resp = await openai.Image.acreate(prompt=prompt, n=1, size="512x512")
            msg = Message.image(url=image_resp.data[0].url)
            await self.event.reply(msg)
        except Exception as e:
            await self.event.reply(f"Error occurred: {e}")
        finally:
            await openai.aiosession.get().close()

    async def rule(self) -> bool:
        return fromMirai(self.event) \
            and isBotCalled(self.event) \
            and isWorkingGroup(self.event) \
            and self.event.message.get_plain_text().strip().startswith('/draw')