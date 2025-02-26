import asyncio
import json
import numbers
import random
import string

from alicebot import MessageEvent

from plugins.Lumina.tables import express_table


def fromOneBot(event):
    return event.adapter.name == 'cqhttp'


def isPM(event: MessageEvent) -> bool:
    return event.message_type == 'private'


def isGroup(event: MessageEvent) -> bool:
    return event.message_type == 'group'


def isAtTo(event: MessageEvent, target: str) -> bool:
    return any(msg.type == 'at' and str(msg['qq']) == str(target) for msg in event.message)


def isAtMe(event: MessageEvent) -> bool:
    return isAtTo(event, str(event.self_id))


def isAtAll(event: MessageEvent) -> bool:
    return isAtTo(event, 'all')


def gather_method_with(cls, prefix):
    return {
        name[len(prefix):]: getattr(cls, name)
        for name in dir(cls)
        if name.startswith(prefix) and callable(getattr(cls, name))
    }


# Run a method with self and kwargs and async
async def execute_method(func, kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(**kwargs)
    else:
        return func(**kwargs)


def convert_message(message) -> str:
    """将AliceBot消息对象转换为处理后的字符串"""
    result = []

    for segment in message:
        # 处理纯文本部分
        if segment.type == 'text':
            result.append(segment.data.get('text', ''))

        # 处理QQ表情
        elif segment.type == 'face':
            face_id = segment.data.get('id')
            if face_id is not None:
                face_id = int(face_id)
                # 获取表情文字描述，找不到时显示[表情ID]
                desc = express_table.get(face_id, f"表情{face_id}")
                result.append(f"[{desc}]")

    # 拼接所有有效部分并去除首尾空白
    return ''.join(result).strip()


def generate_random_string(length=15):
    # 定义字符集：小写字母 + 数字
    characters = string.ascii_lowercase + string.digits
    # 生成随机字符串
    return ''.join(random.choices(characters, k=length))


def message2string(message):
    if message["role"] == "system":
        return "system prompt"
    elif message["role"] == "user":
        data = json.loads(message["content"].replace("'", '"'))
        content = data['messages'][0:6] + "..." if len(data['messages']) > 8 else data['messages']
        return f"{data['sender_name']}({data['sender_id']})send: {content}"
    elif message["role"] == "assistant":
        data = message
        content = data['content'][0:6] + "..." if len(data['content']) > 8 else data['content']
        return f"Lumina repley: {content}"
