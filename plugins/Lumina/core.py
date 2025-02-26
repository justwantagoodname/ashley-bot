import re

import alicebot
from alicebot import Plugin
from alicebot.adapter.cqhttp import CQHTTPMessageSegment

from plugins.Lumina.ai import LuminaChatApi
from config import Config
from plugins.Lumina.utils import *


# Lumina Core
class Lumina:
    def __init__(self, config: Config = None, **kwargs):
        self.permissions = gather_method_with(self, 'permissions_')
        self.manage_cmd = gather_method_with(self, 'manage_')
        self.config = config

        self.wheel = set(self.config.get('wheel', default=[]))
        self.group_whitelist = set(self.config.get('group_whitelist', default=[]))

        self.group_chat_session = dict()  # group_id to uuid

        self.ai = LuminaChatApi(
            model=self.config.Lumina['Parameters']['model'],
            prompt=self.config.Lumina['Prompt'],
        )

    async def has_pemission(self, action, **kwargs) -> bool:
        return await execute_method(self.permissions[action], kwargs)

    async def do_manage_cmd(self, **kwargs):
        cmd = kwargs['cmd'] if kwargs['cmd'] in self.manage_cmd else 'help'
        return await execute_method(self.manage_cmd[cmd], kwargs)

    def permissions_manage(self, **kwargs) -> bool:
        event = kwargs['event']
        return event.user_id in self.wheel

    def permissions_group_chat(self, **kwargs) -> bool:
        event = kwargs['event']
        return event.group_id in self.group_whitelist

    async def manage_help(self, **kwargs):
        """显示本条帮助"""
        text = "Commands:\n"
        for cmd, func in self.manage_cmd.items():
            text += f"#{cmd} " + (f"{func.__doc__.strip()}\n" if func.__doc__ else f"{func.__name__}\n")
        event = kwargs['event']
        await event.reply(text)

    async def manage_ping(self, **kwargs):
        """Ping 命令测试用途"""
        event: MessageEvent = kwargs['event']
        await event.reply("Pong!")

    async def manage_echo(self, **kwargs):
        """回显命令参数"""
        event: MessageEvent = kwargs['event']
        await event.reply(' '.join(kwargs['args']))

    async def manage_enable(self, **kwargs):
        """在群聊中启用对话"""
        event: MessageEvent = kwargs['event']

        if isPM(event):
            await event.reply("请在群聊中使用")
            return

        if isGroup(event):
            self.group_whitelist.add(event.group_id)
            whitelist = self.config.group_whitelist
            whitelist.append(event.group_id)
            self.config.group_whitelist = whitelist
            await event.reply("已启用")
        else:
            await event.reply("请在群聊中使用")

    async def manage_disable(self, **kwargs):
        """在群聊中禁用对话"""
        event: MessageEvent = kwargs['event']

        if isPM(event):
            await event.reply("请在群聊中使用")
            return

        if isGroup(event):
            self.group_whitelist.remove(event.group_id)
            whitelist = self.config.group_whitelist
            whitelist.remove(event.group_id)
            self.config.group_whitelist = whitelist
            await event.reply("已禁用")
        else:
            await event.reply("请在群聊中使用")

    async def manage_list_grp(self, **kwargs):
        """列出已启用的群聊"""
        event: MessageEvent = kwargs['event']
        await event.reply(f"已启用的群聊：{self.group_whitelist}")

    async def manage_info(self, event: MessageEvent = None, args: list[str] = None, **kwargs):
        """显示当前配置 参数: all model prompt"""
        info = {
            'model': self.config.Lumina['Parameters']['model'],
            'prompt': self.config.Lumina['Prompt'],
        }

        # unique the args
        args = list(set(args))
        result = ''
        if all in args:
            result = '\n'.join([f'|{key}: {value}|' for key, value in info.items()])
        elif len(args) == 0:
            result = '\n'.join(info.keys())
        else:
            result = '\n'.join(map(lambda item: f'|{item}: {info[item]}|', args))
        await event.reply(result)

    async def manage_express(self, **kwargs):
        """表情相关指令 参数"""
        event: MessageEvent = kwargs['event']
        await event.reply("该功能未完成！")

    async def manage_messages(self, **kwargs):
        """消息队列有关指令 参数：count, last, list [n]，clear"""
        event: MessageEvent = kwargs['event']
        args: list = kwargs['args']

        help_str = """请输入以下指令：
                #message count :显示输入消息队列长度
                #message last ：显示上一条输入和回复
                #message list [n] ：显示全部队列，[n]为可选项，表示显示最近n次对话，默认显示之前10条
                #message clear ：清空记忆
                """

        if len(args) == 0:
            await event.reply(help_str)
        elif args[0] == "count":
            await event.reply(f"当前消息队列长度为 {len(self.ai.message)}")
        elif args[0] == "last":
            msg = message2string(self.ai.message[-1])
            if len(self.ai.message) >= 2:
                msg = "\n" + message2string(self.ai.message[-2])
            await event.reply(msg)
        elif args[0] == "list":
            msg = ""
            for m in self.ai.message:
                msg += message2string(m) + "\n"
            await event.reply(msg)
        elif args[0] == "clear":
            self.ai.message = [self.ai.message[0]]
            await event.reply("喵呜…这里是哪里nya？大，大家的味道突然记不清了喵…可以重新认识吗？(´･ω･`)")
        else:
            await event.reply(help_str)

    async def group_should_answer(self, **kwargs) -> bool:
        """判断群聊消息是否应该回复"""
        event = kwargs['event']
        # TODO: support more complex rules
        return isAtMe(event) or isAtAll(event)

    async def do_group_chat(self, event: MessageEvent = None):
        """实际对话信息，调用 langgraph"""
        await self.ai.chat(event=event)


class LuminaAppPlugin(Plugin):
    priority = 1

    async def handle(self):
        await self.bot.lumina.do_group_chat(event=self.event)

    async def rule(self) -> bool:
        if not fromOneBot(self.event):
            return False

        if self.event.type == 'notice':
            return False

        if isPM(self.event):
            return False  # TODO

        if isGroup(self.event) and await self.bot.lumina.has_pemission('group_chat', event=self.event):
            return await self.bot.lumina.group_should_answer(event=self.event)


class LuminaManagePlugin(Plugin):
    priority = 0
    block = True

    def parse_command(self, command_str: str):
        """
            从字符串解析命令
            命令类似于/命令arg1 arg2 arg3，其中用空格分隔
            arg可以通过“”从原始字符串中引用
        """
        command_str = command_str.strip()
        match = re.match(r"#(\S+)", command_str)  # Match command name after '/'
        if not match:
            return None, []

        command = match.group(1)
        args_str = command_str[len(match.group(0)):].strip()  # Remaining arguments

        # Regex to match quoted arguments or unquoted words
        args = re.findall(r'"([^"]*)"|(\S+)', args_str)
        args = [arg[0] if arg[0] else arg[1] for arg in args]  # Flatten tuples

        return command, args

    async def handle(self):
        cmd, args = self.parse_command(self.event.message.get_plain_text())
        return await self.bot.lumina.do_manage_cmd(cmd=cmd, args=args, event=self.event)

    def is_command(self) -> bool:
        return self.event.message.get_plain_text().strip().startswith('#')

    async def rule(self) -> bool:
        if not fromOneBot(self.event):
            return False

        if self.event.type == 'notice':
            return False

        if isPM(self.event):
            return await self.bot.lumina.has_pemission('manage', event=self.event)

        if isGroup(self.event) and self.is_command():
            return isAtMe(self.event) and await self.bot.lumina.has_pemission('manage', event=self.event)

        return False
