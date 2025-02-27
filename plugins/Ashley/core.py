from math import exp
from termios import CQUIT
from alicebot import MessageEvent, Plugin
from alicebot.adapter.cqhttp.message import CQHTTPMessageSegment
from langchain_core.messages import HumanMessage, AIMessage
from plugins.Ashley.ai import AshleyAIGraph
from plugins.Ashley.config import AshleyConfig
from plugins.Ashley.utils import execute_method, fromOneBot, gather_method_with, isAtAll, isAtMe, isGroup, isPM
import re
import psutil

# Ashley Core
class Ashley:
    def __init__(self, config: AshleyConfig=None, **kwargs):
        self.permissions = gather_method_with(self, 'permissions_')
        self.manage_cmd = gather_method_with(self, 'manage_')
        self.config = config

        self.wheel = set(self.config.get('wheel', default=[]))
        self.group_whitelist = set(self.config.get('group_whitelist', default=[]))

        self.group_chat_session = dict() # group_id to uuid

        self.ai = AshleyAIGraph(
            config=self.config,
            model=self.config.Ashley['Parameters']['model'],
            prompt=self.config.Ashley['Prompt'],
            base_url=self.config.Ashley['Parameters']['base_url'],
            express_data=self.config.Express 
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
            text += f"!{cmd} " + (f"{func.__doc__.strip()}\n" if func.__doc__ else f"{func.__name__}\n")
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

    async def manage_ps(self, **kwargs):
        """显示宿主机负载 参数： all 显示详细信息"""
        args = kwargs['args']
        load = [round(load, 2) for load in psutil.getloadavg()]
        temp = {key: item[0].current for key, item in psutil.sensors_temperatures().items()}
        if 'all' in args:
            display = \
f'''Load: {load}
CPU: {psutil.cpu_percent()}% {psutil.cpu_count()}x @ {round(psutil.cpu_freq().current, 2)}MHz
Memory: {psutil.virtual_memory().percent}% Avail: {round(psutil.virtual_memory().available / 1024 / 1024, 2)}MiB Used: {round(psutil.virtual_memory().used / 1024 / 1024, 2)}MiB
Swap: {psutil.swap_memory().percent}% Used: {psutil.swap_memory().used}
Misc: BAT: {round(psutil.sensors_battery().percent, 2)}% Temp: {temp}'''
        else:
            display = f'''Load: {load}'''
        event: MessageEvent = kwargs['event']
        await event.reply(display)

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

    async def manage_info(self, event: MessageEvent=None, args: list[str]=None, **kwargs):
        """显示当前配置 参数: all model prompt"""
        info = {
            'model': self.config.Ashley['Parameters']['model'],
            'prompt': self.config.Ashley['Prompt'],
            'token': await self.ai.get_token_usage(event=event),
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

    async def manage_inspect(self, event: MessageEvent=None, **kwargs):
        """显示 langgraph image"""
        url = self.ai.render_image()
        msg = CQHTTPMessageSegment.image(url)
        await event.reply(msg)

    async def group_should_answer(self, **kwargs) -> bool:
        """判断群聊消息是否应该回复"""
        event = kwargs['event']
        # TODO: support more complex rules
        return isAtMe(event) or isAtAll(event)

    async def do_group_chat(self, event: MessageEvent=None):
        """实际对话信息，调用 langgraph"""
        await self.ai.chat(event=event)

class AshleyAppPlugin(Plugin):
    priority = 1

    async def handle(self):
        await self.bot.ashley.do_group_chat(event=self.event)

    async def rule(self) -> bool:
        if not fromOneBot(self.event):
            return False
        
        if isPM(self.event):
            return False # TODO
        
        if isGroup(self.event) and await self.bot.ashley.has_pemission('group_chat', event=self.event):
            return await self.bot.ashley.group_should_answer(event=self.event)

class AshleyManagePlugin(Plugin):
    priority = 0
    block = True

    def parse_command(self, command_str: str) -> str:
        ''' 
            Parse a command from string
            command like /command arg1 arg2 arg3 where seprarated by space
            arg can be quoted with "" from raw string
        '''
        command_str = command_str.strip()
        match = re.match(r"!(\S+)", command_str)  # Match command name after '/'
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
        return await self.bot.ashley.do_manage_cmd(cmd=cmd, args=args, event=self.event)
    
    def is_command(self) -> bool:
        return self.event.message.get_plain_text().strip().startswith('!')
    
    async def rule(self) -> bool:
        if not fromOneBot(self.event):
            return False
        
        if isPM(self.event):
            return await self.bot.ashley.has_pemission('manage', event=self.event)
        
        if isGroup(self.event) and self.is_command():
            return isAtMe(self.event) and await self.bot.ashley.has_pemission('manage', event=self.event)
        
        return False