import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import traceback
import aiosqlite
import db
from cogs.indexer import DEFAULT_SCAN_LIMIT, index_channels_history

PAGE_SIZE = 10
DEFAULT_RESULT_LIMIT = 200
DEFAULT_CONTEXT_LIMIT = 5
MAX_CONTEXT_LIMIT = 20


class ContextLoadError(Exception):
    pass


def _build_embed(
    rows,
    guild_id: str,
    ext: str | None,
    page: int,
    total_pages: int,
    visible_total: int,
    actual_total: int,
    effective_limit: int,
    auto_indexed: bool,
    indexed_channels: int,
    indexed_messages: int,
    scan_limit: int,
    used_file_search: bool,
    file_search_unavailable: bool,
):
    title_ext = f".{ext}" if ext else "全部条件"
    description = [f"共找到 **{actual_total}** 个文件  |  第 {page}/{total_pages} 页"]
    if actual_total > effective_limit:
        description.append(f"当前只展示最新 **{visible_total}** 条结果。")
    if auto_indexed:
        method = "Discord 附件搜索" if used_file_search else "频道历史扫描"
        fallback = "；附件搜索不可用，已自动退回历史扫描" if file_search_unavailable else ""
        description.append(
            f"本次已自动补索引：使用 **{method}**{fallback}；处理 **{indexed_channels}** 个频道、**{indexed_messages}** 条含附件消息；"
            f"上限 **{scan_limit}** 条；如果填了时间范围，会只搜索这个时间段。"
        )
    embed = discord.Embed(
        title=f"文件搜索：{title_ext}",
        color=0x5865F2,
        description="\n".join(description),
    )
    for filename, url, channel_id, message_id, author_id, timestamp in rows:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        embed.add_field(
            name=filename,
            value=f"[下载]({url})  |  [跳转消息]({jump_url})  |  <#{channel_id}>  |  <@{author_id}>  |  {dt}",
            inline=False,
        )
    return embed


def _format_message_line(message: discord.Message) -> str:
    content = message.content.strip() if message.content else ""
    attachment_names = ", ".join(attachment.filename for attachment in message.attachments)
    body = content or (f"附件：{attachment_names}" if attachment_names else "无文字内容")
    body = body.replace("\n", " ")
    if len(body) > 180:
        body = body[:177] + "..."
    created_at = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"**{created_at}** <@{message.author.id}>：{body}"


async def _build_context_embed(
    interaction: discord.Interaction,
    guild_id: str,
    channel_id: str,
    message_id: str,
    filename: str,
    context_limit: int,
) -> discord.Embed:
    channel = interaction.client.get_channel(int(channel_id))
    if channel is None:
        channel = await interaction.client.fetch_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        raise ContextLoadError

    target = await channel.fetch_message(int(message_id))
    before = [message async for message in channel.history(limit=context_limit, before=target, oldest_first=False)]
    after = [message async for message in channel.history(limit=context_limit, after=target, oldest_first=True)]
    messages = list(reversed(before)) + [target] + after

    jump_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    embed = discord.Embed(
        title=f"上下文：{filename}",
        color=0x2ECC71,
        description=f"前后各 **{context_limit}** 条消息  |  [跳转原消息]({jump_url})",
    )
    for message in messages:
        marker = "目标消息" if message.id == int(message_id) else "上下文"
        embed.add_field(name=marker, value=_format_message_line(message), inline=False)
    return embed


class ContextSelect(discord.ui.Select):
    def __init__(self, rows):
        options = []
        for filename, _, channel_id, message_id, _, _ in rows:
            label = filename[:100]
            options.append(discord.SelectOption(label=label, value=f"{channel_id}:{message_id}"))
        super().__init__(placeholder="选择一个文件查看上下文", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, SearchView):
            return
        if not await view._ensure_requester(interaction):
            return
        channel_id, message_id = self.values[0].split(":", 1)
        filename = view.context_filenames.get(self.values[0], "文件")
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            embed = await _build_context_embed(
                interaction,
                view.guild_id,
                channel_id,
                message_id,
                filename,
                view.context_limit,
            )
        except (ContextLoadError, discord.Forbidden, discord.NotFound, discord.HTTPException):
            await interaction.followup.send("上下文读取失败。可能是消息被删了，或者机器人没有读取这个频道历史的权限。", ephemeral=True)
            return
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("上下文读取失败。终端里已经打印错误。", ephemeral=True)
            return
        await interaction.followup.send(embed=embed, ephemeral=True)


class SearchView(discord.ui.View):
    def __init__(
        self,
        database: aiosqlite.Connection,
        requester_id: int,
        guild_id: str,
        ext: str | None,
        channel_id: str | None,
        author_id: str | None,
        after: int | None,
        before: int | None,
        visible_total: int,
        actual_total: int,
        effective_limit: int,
        auto_indexed: bool,
        indexed_channels: int,
        indexed_messages: int,
        scan_limit: int,
        used_file_search: bool,
        file_search_unavailable: bool,
        context_limit: int,
        rows,
        page: int = 1,
    ):
        super().__init__(timeout=120)
        self.db = database
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.ext = ext
        self.channel_id = channel_id
        self.author_id = author_id
        self.after = after
        self.before = before
        self.visible_total = visible_total
        self.actual_total = actual_total
        self.effective_limit = effective_limit
        self.auto_indexed = auto_indexed
        self.indexed_channels = indexed_channels
        self.indexed_messages = indexed_messages
        self.scan_limit = scan_limit
        self.used_file_search = used_file_search
        self.file_search_unavailable = file_search_unavailable
        self.context_limit = context_limit
        self.context_filenames: dict[str, str] = {}
        self.page = page
        self.total_pages = max(1, (visible_total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.message: discord.Message | None = None
        self._set_context_rows(rows)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages

    def _set_context_rows(self, rows):
        for item in list(self.children):
            if isinstance(item, ContextSelect):
                self.remove_item(item)
        self.context_filenames = {f"{channel_id}:{message_id}": filename for filename, _, channel_id, message_id, _, _ in rows}
        if rows:
            self.add_item(ContextSelect(rows))

    async def _ensure_requester(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("只有发起搜索的人可以翻页。", ephemeral=True)
        return False

    async def _goto(self, interaction: discord.Interaction, page: int):
        if not await self._ensure_requester(interaction):
            return
        self.page = max(1, min(page, self.total_pages))
        self._update_buttons()
        page_limit = min(PAGE_SIZE, max(self.visible_total - (self.page - 1) * PAGE_SIZE, 0))
        if page_limit <= 0:
            await interaction.response.edit_message(view=self)
            return
        _, rows = await db.search_files(
            self.db,
            self.guild_id,
            self.ext,
            self.channel_id,
            self.author_id,
            self.after,
            self.before,
            limit=page_limit,
            offset=(self.page - 1) * PAGE_SIZE,
        )
        self._set_context_rows(rows)
        embed = _build_embed(
            rows,
            self.guild_id,
            self.ext,
            self.page,
            self.total_pages,
            self.visible_total,
            self.actual_total,
            self.effective_limit,
            self.auto_indexed,
            self.indexed_channels,
            self.indexed_messages,
            self.scan_limit,
            self.used_file_search,
            self.file_search_unavailable,
        )
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
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Search(commands.Cog):
    def __init__(self, bot: commands.Bot, database: aiosqlite.Connection):
        self.bot = bot
        self.db = database

    @app_commands.guild_only()
    @app_commands.command(name="search", description="按用户、时间、频道或扩展名搜索附件")
    @app_commands.describe(
        from_user="限定上传者（可选）",
        after="起始日期，如 2026-5-1 或 2026-05-01（可选）",
        before="截止日期，如 2026-5-31 或 2026-05-31（可选）",
        channel="限定频道（可选）",
        ext="文件扩展名，如 safetensors、.pdf、zip（可选）",
        scan_limit=f"自动补索引时每个频道最多扫描多少条消息，默认 {DEFAULT_SCAN_LIMIT}",
        result_limit=f"最多返回多少条最新结果，默认 {DEFAULT_RESULT_LIMIT}",
        context_limit=f"查看上下文时前后各取多少条消息，默认 {DEFAULT_CONTEXT_LIMIT}",
    )
    async def search(
        self,
        interaction: discord.Interaction,
        from_user: discord.Member | None = None,
        after: str | None = None,
        before: str | None = None,
        channel: discord.TextChannel | None = None,
        ext: str | None = None,
        scan_limit: app_commands.Range[int, 1, 50000] | None = None,
        result_limit: app_commands.Range[int, 1, 1000] | None = None,
        context_limit: app_commands.Range[int, 1, MAX_CONTEXT_LIMIT] | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        after_ts = _parse_date(after) if after else None
        before_ts = _parse_date(before, end_of_day=True) if before else None
        normalized_ext: str | None = None
        if ext is not None:
            normalized_ext = db.normalize_extension(ext)
            if not normalized_ext:
                await interaction.followup.send("扩展名不能为空；要么留空，要么填合法后缀。", ephemeral=True)
                return

        if after_ts is None and after:
            await interaction.followup.send("after 日期格式错误，请用 2026-5-1 或 2026-05-01 这种写法。", ephemeral=True)
            return
        if before_ts is None and before:
            await interaction.followup.send("before 日期格式错误，请用 2026-5-31 或 2026-05-31 这种写法。", ephemeral=True)
            return
        if not any([from_user, after_ts is not None, before_ts is not None, channel, normalized_ext]):
            await interaction.followup.send("至少填 1 个筛选条件。", ephemeral=True)
            return

        effective_scan_limit = scan_limit or DEFAULT_SCAN_LIMIT
        effective_result_limit = result_limit or DEFAULT_RESULT_LIMIT
        effective_context_limit = context_limit or DEFAULT_CONTEXT_LIMIT

        total, rows = await db.search_files(
            self.db,
            guild_id=str(interaction.guild.id),
            extension=normalized_ext,
            channel_id=str(channel.id) if channel else None,
            author_id=str(from_user.id) if from_user else None,
            after=after_ts,
            before=before_ts,
            limit=min(PAGE_SIZE, effective_result_limit),
            offset=0,
        )

        auto_indexed = False
        indexed_channels = 0
        indexed_messages = 0
        indexed_new_records = 0
        limit_hit = False
        used_file_search = False
        file_search_unavailable = False

        if total == 0:
            channels = (
                [channel]
                if channel
                else [c for c in interaction.guild.text_channels if c.permissions_for(interaction.guild.me).read_message_history]
            )
            summary = await index_channels_history(
                self.db,
                str(interaction.guild.id),
                channels,
                effective_scan_limit,
                after_ts,
                before_ts,
                self.bot,
            )
            auto_indexed = True
            indexed_channels = summary.channels_scanned
            indexed_messages = summary.messages_scanned
            indexed_new_records = summary.new_records
            limit_hit = summary.limit_hit
            used_file_search = summary.used_file_search
            file_search_unavailable = summary.file_search_unavailable

            total, rows = await db.search_files(
                self.db,
                guild_id=str(interaction.guild.id),
                extension=normalized_ext,
                channel_id=str(channel.id) if channel else None,
                author_id=str(from_user.id) if from_user else None,
                after=after_ts,
                before=before_ts,
                limit=min(PAGE_SIZE, effective_result_limit),
                offset=0,
            )

        effective_total = min(total, effective_result_limit)
        rows = rows[:min(PAGE_SIZE, effective_result_limit)]

        if effective_total == 0:
            ext_text = f" `.{normalized_ext}`" if normalized_ext else ""
            limit_text = "本次扫描已触发上限。" if limit_hit else "本次扫描未触发上限。"
            range_text = "已按你填的时间范围搜索。" if after_ts is not None or before_ts is not None else "未填时间范围，所以从最新文件往前搜索。"
            method_text = "Discord 附件搜索" if used_file_search else "频道历史扫描"
            fallback_text = "附件搜索不可用，已退回频道历史扫描。" if file_search_unavailable else ""
            auto_index_text = (
                f" 已自动补索引：使用 {method_text}；处理 {indexed_channels} 个频道、{indexed_messages} 条含附件消息、新增 {indexed_new_records} 条记录；"
                f"上限 {effective_scan_limit} 条。{range_text}{fallback_text}"
                if auto_indexed else ""
            )
            await interaction.followup.send(
                f"没有找到{ext_text}文件。{auto_index_text} {limit_text} 如果你要找更早的文件，可以填 after/before 收窄时间，或把 scan_limit 调大后再搜。",
                ephemeral=True,
            )
            return

        total_pages = max(1, (effective_total + PAGE_SIZE - 1) // PAGE_SIZE)
        embed = _build_embed(
            rows,
            str(interaction.guild.id),
            normalized_ext,
            1,
            total_pages,
            effective_total,
            total,
            effective_result_limit,
            auto_indexed,
            indexed_channels,
            indexed_messages,
            effective_scan_limit,
            used_file_search,
            file_search_unavailable,
        )
        if auto_indexed:
            embed.set_footer(text=f"自动补索引新增 {indexed_new_records} 条记录。")
        elif effective_total < total:
            embed.set_footer(text="结果已按限制截断。")

        view = SearchView(
            self.db,
            interaction.user.id,
            str(interaction.guild.id),
            normalized_ext,
            str(channel.id) if channel else None,
            str(from_user.id) if from_user else None,
            after_ts,
            before_ts,
            effective_total,
            total,
            effective_result_limit,
            auto_indexed,
            indexed_channels,
            indexed_messages,
            effective_scan_limit,
            used_file_search,
            file_search_unavailable,
            effective_context_limit,
            rows,
        )
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
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
