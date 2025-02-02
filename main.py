from alicebot import Bot
from plugins.Ashley import Ashley, AshleyAppPlugin, AshleyManagePlugin
from plugins.Ashley.config import AshleyConfig

bot = Bot(hot_reload=False)

@bot.bot_run_hook
async def initAshley(bot: Bot):
    bot.ashley = Ashley(config=AshleyConfig())

bot.load_plugins(AshleyAppPlugin, AshleyManagePlugin)

if __name__ == '__main__':
    bot.run()