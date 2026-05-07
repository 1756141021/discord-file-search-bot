import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import aiosqlite
import db

PAGE_SIZE = 10


def _build_embed(rows, ext: str, page: int, total_pages: int, total: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"文件搜索：.{ext}",
        color=0x5865F2,
        description=f"共找到 **{total}** 个文件  |  第 {page}/{total_pages} 页",
    )
    for filename, url, channel_id, author_id, timestamp in rows:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        embed.add_field(
            name=filename,
            value=f"[下载]({url})  |  <#{channel_id}>  |  <@{author_id}>  |  {dt}",
            inline=False,
        )
    return embed


class SearchView(discord.ui.View):
    def __init__(self, database: aiosqlite.Connection, guild_id: str,
                 ext: str, channel_id: str | None, author_id: str | None,
                 after: int | None, before: int | None,
                 total: int, page: int = 1):
        super().__init__(timeout=120)
        self.db = database
        self.guild_id = guild_id
        self.ext = ext
        self.channel_id = channel_id
        self.author_id = author_id
        self.after = after
        self.before = before
        self.total = total
        self.page = page
        self.total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages

    async def _goto(self, interaction: discord.Interaction, page: int):
        self.page = max(1, min(page, self.total_pages))
        self._update_buttons()
        _, rows = await db.search_files(
            self.db, self.guild_id, self.ext,
            self.channel_id, self.author_id, self.after, self.before,
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
        )
        embed = _build_embed(rows, self.ext, page, self.total_pages, self.total)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀ 上一页", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._goto(interaction, self.page - 1)

    @discord.ui.button(label="下一页 ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._goto(interaction, self.page + 1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)


class Search(commands.Cog):
    def __init__(self, bot: commands.Bot, database: aiosqlite.Connection):
        self.bot = bot
        self.db = database

    @app_commands.guild_only()
    @app_commands.command(name="search", description="按文件扩展名搜索附件")
    @app_commands.describe(
        ext="文件扩展名，如 pdf、zip、mp4（不需要加点）",
        channel="限定频道（可选）",
        from_user="限定上传者（可选）",
        after="起始日期，格式 YYYY-MM-DD（可选）",
        before="截止日期，格式 YYYY-MM-DD（可选）",
    )
    async def search(
        self,
        interaction: discord.Interaction,
        ext: str,
        channel: discord.TextChannel | None = None,
        from_user: discord.Member | None = None,
        after: str | None = None,
        before: str | None = None,
    ):
        await interaction.response.defer()

        after_ts = _parse_date(after) if after else None
        before_ts = _parse_date(before, end_of_day=True) if before else None

        if after_ts is None and after:
            await interaction.followup.send("after 日期格式错误，请用 YYYY-MM-DD。", ephemeral=True)
            return
        if before_ts is None and before:
            await interaction.followup.send("before 日期格式错误，请用 YYYY-MM-DD。", ephemeral=True)
            return

        total, rows = await db.search_files(
            self.db,
            guild_id=str(interaction.guild.id),
            extension=ext,
            channel_id=str(channel.id) if channel else None,
            author_id=str(from_user.id) if from_user else None,
            after=after_ts,
            before=before_ts,
            limit=PAGE_SIZE,
            offset=0,
        )

        if total == 0:
            await interaction.followup.send(f"没有找到 `.{ext.lower().lstrip('.')}` 文件。")
            return

        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        embed = _build_embed(rows, ext.lower().lstrip("."), 1, total_pages, total)
        view = SearchView(
            self.db, str(interaction.guild.id), ext.lower().lstrip("."),
            str(channel.id) if channel else None,
            str(from_user.id) if from_user else None,
            after_ts, before_ts, total,
        )
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg


def _parse_date(date_str: str, end_of_day: bool = False) -> int | None:
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return int(dt.timestamp())
    except ValueError:
        return None


async def setup(bot: commands.Bot, database: aiosqlite.Connection):
    await bot.add_cog(Search(bot, database))
