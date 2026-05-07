import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import db


class Indexer(commands.Cog):
    def __init__(self, bot: commands.Bot, database: aiosqlite.Connection):
        self.bot = bot
        self.db = database

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.attachments:
            return
        for attachment in message.attachments:
            await db.insert_file(
                self.db,
                guild_id=str(message.guild.id),
                channel_id=str(message.channel.id),
                message_id=str(message.id),
                author_id=str(message.author.id),
                filename=attachment.filename,
                url=attachment.url,
                timestamp=int(message.created_at.timestamp()),
            )

    @app_commands.guild_only()
    @app_commands.command(name="index", description="[管理员] 爬取频道历史消息建立文件索引")
    @app_commands.describe(channel="要索引的频道，不填则索引所有频道")
    @app_commands.default_permissions(administrator=True)
    async def index(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await interaction.response.defer(ephemeral=False)

        channels: list[discord.TextChannel] = (
            [channel] if channel
            else [c for c in interaction.guild.text_channels
                  if c.permissions_for(interaction.guild.me).read_message_history]
        )

        status_msg = await interaction.followup.send(
            f"开始索引 {len(channels)} 个频道，请稍候……"
        )

        total_new = 0
        for ch in channels:
            count = 0
            try:
                async for message in ch.history(limit=None, oldest_first=True):
                    for attachment in message.attachments:
                        added = await db.insert_file(
                            self.db,
                            guild_id=str(interaction.guild.id),
                            channel_id=str(ch.id),
                            message_id=str(message.id),
                            author_id=str(message.author.id),
                            filename=attachment.filename,
                            url=attachment.url,
                            timestamp=int(message.created_at.timestamp()),
                        )
                        if added:
                            count += 1
            except discord.Forbidden:
                pass
            total_new += count

        await status_msg.edit(content=f"索引完成。新增文件记录：**{total_new}** 条。")


async def setup(bot: commands.Bot, database: aiosqlite.Connection):
    await bot.add_cog(Indexer(bot, database))
