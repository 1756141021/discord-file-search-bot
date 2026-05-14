import discord
from discord import app_commands
from discord.ext import commands
from discord.http import Route
from datetime import datetime, timezone
import aiosqlite
import db


DEFAULT_SCAN_LIMIT = 5000


class IndexSummary:
    def __init__(self):
        self.channels_scanned = 0
        self.channels_skipped = 0
        self.messages_scanned = 0
        self.new_records = 0
        self.limit_hit = False
        self.used_file_search = False
        self.file_search_unavailable = False


async def _insert_message_attachments(
    database: aiosqlite.Connection,
    guild_id: str,
    channel_id: str,
    message,
) -> int:
    added_count = 0
    for attachment in message.attachments:
        added = await db.insert_file(
            database,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=str(message.id),
            author_id=str(message.author.id),
            filename=attachment.filename,
            url=attachment.url,
            timestamp=int(message.created_at.timestamp()),
        )
        if added:
            added_count += 1
    return added_count


async def _insert_payload_attachments(
    database: aiosqlite.Connection,
    guild_id: str,
    payload: dict,
) -> int:
    added_count = 0
    timestamp = int(datetime.fromisoformat(payload["timestamp"]).timestamp())
    for attachment in payload.get("attachments", []):
        filename = attachment.get("filename", "")
        url = attachment.get("url") or attachment.get("proxy_url") or ""
        if not filename or not url:
            continue
        added = await db.insert_file(
            database,
            guild_id=guild_id,
            channel_id=str(payload["channel_id"]),
            message_id=str(payload["id"]),
            author_id=str(payload["author"]["id"]),
            filename=filename,
            url=url,
            timestamp=timestamp,
        )
        if added:
            added_count += 1
    return added_count


async def index_channel_history(
    database: aiosqlite.Connection,
    guild_id: str,
    channel: discord.TextChannel,
    scan_limit: int,
    after: int | None = None,
    before: int | None = None,
) -> IndexSummary:
    summary = IndexSummary()
    if scan_limit <= 0:
        return summary

    after_dt = datetime.fromtimestamp(after, tz=timezone.utc) if after is not None else None
    before_dt = datetime.fromtimestamp(before, tz=timezone.utc) if before is not None else None

    try:
        summary.channels_scanned = 1
        async for message in channel.history(limit=scan_limit, after=after_dt, before=before_dt):
            summary.messages_scanned += 1
            summary.new_records += await _insert_message_attachments(database, guild_id, str(channel.id), message)
        summary.limit_hit = summary.messages_scanned >= scan_limit
    except (discord.Forbidden, discord.HTTPException):
        summary.channels_scanned = 0
        summary.channels_skipped = 1
    return summary


async def _index_guild_file_search(
    bot: commands.Bot,
    database: aiosqlite.Connection,
    guild_id: str,
    channels: list[discord.TextChannel],
    scan_limit: int,
    after: int | None = None,
    before: int | None = None,
) -> IndexSummary:
    summary = IndexSummary()
    if scan_limit <= 0:
        return summary

    channel_map = {str(channel.id): channel for channel in channels}
    params: dict[str, str | int] = {
        "has": "file",
        "include_nsfw": "true",
        "sort_by": "timestamp",
        "sort_order": "desc",
    }
    if len(channel_map) == 1:
        params["channel_id"] = next(iter(channel_map))
    if after is not None:
        params["min_id"] = discord.utils.time_snowflake(datetime.fromtimestamp(after, tz=timezone.utc), high=False)
    if before is not None:
        params["max_id"] = discord.utils.time_snowflake(datetime.fromtimestamp(before, tz=timezone.utc), high=True)

    offset = 0
    seen_messages: set[str] = set()
    print(f"[file_search] guild={guild_id} channels={len(channel_map)} params={params}")
    try:
        while summary.messages_scanned < scan_limit:
            page_limit = min(25, scan_limit - summary.messages_scanned)
            data = await bot.http.request(
                Route("GET", "/guilds/{guild_id}/messages/search", guild_id=int(guild_id)),
                params={**params, "offset": offset},
            )
            print(f"[file_search] offset={offset} got groups={len(data.get('messages', []))} total_results={data.get('total_results')}")
            groups = data.get("messages", [])
            if not groups:
                break
            for group in groups:
                if summary.messages_scanned >= scan_limit:
                    break
                if not group:
                    continue
                payload = group[0]
                message_id = str(payload["id"])
                if message_id in seen_messages:
                    continue
                channel_id = str(payload["channel_id"])
                if channel_id not in channel_map:
                    continue
                seen_messages.add(message_id)
                if not payload.get("attachments"):
                    continue
                summary.messages_scanned += 1
                summary.new_records += await _insert_payload_attachments(database, guild_id, payload)
            if len(groups) < page_limit:
                break
            offset += len(groups)
        summary.channels_scanned = len(channel_map)
        summary.limit_hit = summary.messages_scanned >= scan_limit
        summary.used_file_search = True
    except discord.HTTPException as e:
        print(f"[file_search] HTTPException status={e.status} code={e.code} text={e.text!r}")
        summary.file_search_unavailable = True
    except Exception as e:
        print(f"[file_search] Unexpected {type(e).__name__}: {e}")
        summary.file_search_unavailable = True
    return summary


async def index_channels_history(
    database: aiosqlite.Connection,
    guild_id: str,
    channels: list[discord.TextChannel],
    scan_limit: int,
    after: int | None = None,
    before: int | None = None,
    bot: commands.Bot | None = None,
) -> IndexSummary:
    if bot is not None:
        total = await _index_guild_file_search(bot, database, guild_id, channels, scan_limit, after, before)
        if total.used_file_search:
            return total

    total = IndexSummary()
    total.file_search_unavailable = bot is not None
    for channel in channels:
        summary = await index_channel_history(database, guild_id, channel, scan_limit, after, before)
        total.channels_scanned += summary.channels_scanned
        total.channels_skipped += summary.channels_skipped
        total.messages_scanned += summary.messages_scanned
        total.new_records += summary.new_records
        total.limit_hit = total.limit_hit or summary.limit_hit
    return total


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
    @app_commands.describe(
        channel="要索引的频道，不填则索引所有频道",
        scan_limit=f"每个频道最多扫描多少条消息，默认 {DEFAULT_SCAN_LIMIT}",
    )
    @app_commands.default_permissions(administrator=True)
    async def index(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        scan_limit: app_commands.Range[int, 1, 50000] | None = None,
    ):
        await interaction.response.defer(ephemeral=False)

        channels: list[discord.TextChannel] = (
            [channel] if channel
            else [c for c in interaction.guild.text_channels
                  if c.permissions_for(interaction.guild.me).read_message_history]
        )
        effective_scan_limit = scan_limit or DEFAULT_SCAN_LIMIT

        status_msg = await interaction.followup.send(
            f"开始索引 {len(channels)} 个频道，每个频道最多扫描 {effective_scan_limit} 条消息，请稍候……"
        )

        summary = await index_channels_history(
            self.db,
            str(interaction.guild.id),
            channels,
            effective_scan_limit,
        )

        limit_note = "已触发扫描上限。" if summary.limit_hit else "未触发扫描上限。"
        await status_msg.edit(
            content=(
                f"索引完成。新增文件记录：**{summary.new_records}** 条；"
                f"已扫描频道：**{summary.channels_scanned}**；"
                f"跳过频道：**{summary.channels_skipped}**；"
                f"已扫描消息：**{summary.messages_scanned}**。{limit_note}"
            )
        )


async def setup(bot: commands.Bot, database: aiosqlite.Connection):
    await bot.add_cog(Indexer(bot, database))
