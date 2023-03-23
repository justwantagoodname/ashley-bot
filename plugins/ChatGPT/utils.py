from plugins.ChatGPT.config import config


def fromMirai(event):
    return event.adapter.name == 'mirai'


def isBotCalled(event) -> bool:
    for msg in event.message:
        if msg.type == 'AtAll':
            return True
        if msg.type == 'At' and msg['target'] == 2801155976:
            return True
    return False


def isWorkingGroup(event) -> bool:
    return event.sender.group.id in config['Group']
