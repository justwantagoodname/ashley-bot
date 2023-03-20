from alicebot import Bot

from plugins.ChatGPT.main import DrawBotPlugin
from plugins.ChatGPT.chatbot import ChatBotPlugin, ChatBotCtrlPlugin


bot = Bot()

bot.load_plugins(DrawBotPlugin, ChatBotCtrlPlugin, ChatBotPlugin)

if __name__ == '__main__':
    bot.run()
