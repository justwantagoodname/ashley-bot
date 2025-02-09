from alicebot import Bot
from plugins.Lumina import Lumina, LuminaAppPlugin, LuminaManagePlugin
from config import Config

bot = Bot(hot_reload=False)

@bot.bot_run_hook
async def initAshley(bot: Bot):
    bot.lumina = Lumina(config=Config())


bot.load_plugins(LuminaAppPlugin, LuminaManagePlugin)

if __name__ == '__main__':
    bot.run()
