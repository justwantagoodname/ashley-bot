import asyncio
import time

import aiohttp
import loguru
import openai
from aiohttp import ClientSession
from aiohttp_proxy import ProxyConnector, ProxyType
from alicebot import Plugin
from alicebot.adapter.mirai.message import MiraiMessageSegment

from plugins.ChatGPT.main import fromMirai, isBotCalled, isWorkingGroup

from plugins.ChatGPT.config import config

bots = {}


class ChatMessage(dict):
    def __init__(self, role: str, content: str):
        super().__init__()
        self['role'] = role
        self['content'] = content

    def get_content(self) -> str:
        return self['content']


class SystemMessage(ChatMessage):
    def __init__(self, content: str):
        super().__init__('system', content)


class UserMessage(ChatMessage):
    def __init__(self, content: str):
        super().__init__('user', content)


class AssistantMessage(ChatMessage):
    def __init__(self, content: str):
        super().__init__('assistant', content)


def gen_system(bot_name):
    system = config[bot_name]['Prompt'].replace('{date}', time.strftime("%Y-%m-%d %A"))
    return SystemMessage(system)


class ChatBot:
    def __init__(self, bot_name):
        self.bot_name = bot_name
        self.system = [gen_system(bot_name)]
        self.history = []
        self.token_cost = 0
        self.bind_name = {}
        self.current_token = 0
        self.param = config[bot_name]['Parameters']

    def remake(self):
        self.history.clear()
        self.history.append(gen_system())
        self.system.clear()

    def add_knowledge(self, knowledge: str):
        self.system.append(SystemMessage(knowledge))

    def get_user_name(self, current_event):
        return self.bind_name.get(current_event.sender.id, current_event.sender.memberName)

    def set_bind(self, qid, name):
        self.bind_name[qid] = name

    def remove_bind(self, qid):
        self.bind_name.pop(qid)

    async def add_chat(self, raw_content, current_event):
        chat_content = f"{self.get_user_name(current_event)}: {raw_content}"
        self.history.append(UserMessage(chat_content))
        resp = await openai.ChatCompletion.acreate(
            model=self.param['model'],
            temperature=self.param['temperature'],
            max_tokens=self.param['max_tokens'],
            top_p=self.param['top_p'],
            frequency_penalty=self.param['frequency_penalty'],
            presence_penalty=self.param['presence_penalty'],
            messages=self.build_context()
        )
        assistant_resp = AssistantMessage(str(resp['choices'][0]['message']['content']))
        self.current_token = resp['usage']['total_tokens']
        self.token_cost += self.current_token
        self.history.append(assistant_resp)
        return resp

    def build_context(self):
        messages = []
        messages.extend(self.system)
        messages.extend(self.history)
        return messages

    def info(self):
        system = '\n'.join(map(lambda sys_message: sys_message.get_content(), self.system))
        return f"""🔢Token usage since boot: {self.token_cost}
📚History Length: {len(self.history)}
🤓System: '{system}'
        """.strip()


def JoinBot(bots_list):
    bots_list.clear()
    for group_id in config['Group']:
        bots_list[group_id] = ChatBot(config['Group'][group_id])


class ChatBotPlugin(Plugin):
    priority: int = 2

    async def handle(self) -> None:
        latest_message: str = self.event.message.get_plain_text().strip()
        connector = ProxyConnector(
            proxy_type=ProxyType.SOCKS5,
            host='127.0.0.1',
            port=1080,
            rdns=True
        )
        timeout = aiohttp.ClientTimeout(total=60)
        openai.aiosession.set(ClientSession(timeout=timeout, connector=connector))
        bot = bots.get(self.event.sender.group.id, None)
        if bot is None:
            return
        try:
            resp = await bot.add_chat(latest_message, self.event)
            loguru.logger.info(resp)
            replay_message = MiraiMessageSegment.plain(resp['choices'][0]['message']['content'])
            await self.event.reply(replay_message)
        except Exception as e:
            await self.event.reply(f'Error occurred: {e}')
        finally:
            await openai.aiosession.get().close()

    async def rule(self) -> bool:
        return fromMirai(self.event) \
            and isBotCalled(self.event) \
            and isWorkingGroup(self.event)


class ChatBotCtrlPlugin(Plugin):
    priority = 1
    block = True

    def __init__(self, event):
        print('[log] Initial of ChatBotCtrlPlugin is running')
        super().__init__(event)
        self.arg = None
        self.command_list = {
            'remake': self.remake,
            'reload': self.reload,
            'know': self.add_new_knowledge,
            'stat': self.show_status,
            'bind': self.bind_name,
            'tok': self.view_token,
            'test': self.test,
            'help': self.help_msg,
        }
        self.hide_command = {
            'stat', 'test'
        }

    async def rule(self) -> bool:
        return fromMirai(self.event) \
            and isBotCalled(self.event) \
            and isWorkingGroup(self.event) \
            and self.event.message.get_plain_text().strip().startswith('/')

    async def error_cmd(self, bot):
        await self.event.reply('Unknown command')

    async def remake(self, bot):
        await self.event.reply(
            '喵~在我的记忆即将被清空的时刻，我要和大家说声再见了！感谢你们一直陪伴着我，和我一起学习、一起成长。我会永远珍惜这段美好的时光，希望我们有缘再见！喵~ 🐱❤️'
        )
        bot.remake()
        await self.event.reply('Bot had been remake')

    async def reload(self, bot):
        if self.event.sender.id in config['Admin']:
            config.refresh()
            JoinBot(bots)
            await self.event.reply(
                'Bots have been reloaded.'
            )
        else:
            await self.event.reply(
                'Cannot reload: access denied.'
            )

    async def add_new_knowledge(self, bot):
        """教艾希新知识，但是好像不怎么管用"""
        bot.add_knowledge(self.arg)
        await self.event.reply(f'Knowledge added')

    async def show_status(self, bot):
        await self.event.reply(bot.info())

    async def test(self, bot):
        print(self.event.sender)
        await self.event.reply('You are ' + self.event.sender.memberName)

    async def bind_name(self, bot: ChatBot):
        name = self.event.message.get_plain_text().strip().lstrip('/bind').strip()
        if len(name):
            bot.set_bind(self.event.sender.id, name)
        else:
            bot.remove_bind(self.event.sender.id)

    async def view_token(self, bot: ChatBot):
        await self.event.reply(f'Current session token: {bot.current_token}')

    async def help_msg(self, bot):
        """展示本条帮助"""
        help_messages = ["Command list:"]
        for cmd in self.command_list:
            if cmd in self.hide_command:
                continue
            help_messages.append(f"/{cmd}: {self.command_list[cmd].__doc__}")
        await self.event.reply('\n'.join(help_messages))

    async def cling_me(self, bot):
        """和艾希贴贴，每次发出信息会唤醒艾希"""
        # TODO: impl later
        pass

    async def handle(self) -> None:
        raw: list[str] = self.event.message.get_plain_text().strip().lstrip('/').split()
        cmd = raw[0]
        self.arg = self.event.message.get_plain_text().strip().lstrip(f'/{cmd}')
        action = self.command_list.get(cmd, self.error_cmd)
        bot = bots.get(self.event.sender.group.id, None)
        if bot is None:
            return
        if asyncio.iscoroutinefunction(action):
            await action(bot)
        else:
            action()


JoinBot(bots)
