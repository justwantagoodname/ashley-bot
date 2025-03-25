import asyncio
from enum import verify
import time
from alicebot import MessageEvent, Event
from PIL import Image
import base64
import httpx
from io import BytesIO

async def convertToBase64(image_path, mode='local'):
    """
    Convert PIL images to Base64 encoded strings

    :param pil_image: PIL image
    :return: Re-sized Base64 string
    """

    if mode == 'local':
        image_path = image_path.replace('/root', '/home/null/Projects/napcat.nix/data')
        # print(image_path)
        pil_image = Image.open(image_path)
    elif mode == 'url':
        pil_image = Image.open(BytesIO(httpx.get(image_path, verify=False).content))

    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")  # You can change the format if needed
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str

def formatTime(unixtime: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unixtime))

def fromOneBot(event: Event) -> bool:
    return event.adapter.name == 'cqhttp'

def isMessageEvent(event: Event) -> bool:
    return event.post_type == 'message'

def isNoticeEvent(event: Event) -> bool:
    return event.post_type == 'notice'

def isPokeNotify(event: Event) -> bool:
    return isNoticeEvent(event) and event.sub_type == 'poke'

def isPokeMe(event: Event) -> bool:
    return isPokeNotify(event) and event.target_id == event.self_id

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

def hasImage(event: MessageEvent) -> bool:
    return any(msg.type == 'image' for msg in event.message)

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