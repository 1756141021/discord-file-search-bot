import asyncio
import discord
from discord.ext import commands
import aiosqlite
import db
import config
from cogs import indexer, search


class FileSearchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.database: aiosqlite.Connection | None = None

    async def setup_hook(self):
        self.database = await aiosqlite.connect(config.DB_PATH)
        await db.init(self.database)
        await indexer.setup(self, self.database)
        await search.setup(self, self.database)
        await self.tree.sync()
        print("斜杠命令已同步。")

    async def on_ready(self):
        print(f"Bot 已上线：{self.user} ({self.user.id})")

    async def close(self):
        if self.database:
            await self.database.close()
        await super().close()


async def main():
    async with FileSearchBot() as bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
