import aiosqlite


async def init(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            author_id  TEXT NOT NULL,
            filename   TEXT NOT NULL,
            extension  TEXT NOT NULL,
            url        TEXT NOT NULL,
            timestamp  INTEGER NOT NULL,
            UNIQUE(message_id, filename)
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_guild_ext ON files(guild_id, extension)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_channel   ON files(channel_id)")
    await db.commit()


def normalize_extension(value: str) -> str:
    return value.strip().lower().lstrip(".")


async def insert_file(db: aiosqlite.Connection,
                      guild_id: str, channel_id: str, message_id: str,
                      author_id: str, filename: str, url: str, timestamp: int):
    ext = normalize_extension(filename.rsplit(".", 1)[-1]) if "." in filename else ""
    cursor = await db.execute(
        "INSERT OR IGNORE INTO files(guild_id,channel_id,message_id,author_id,filename,extension,url,timestamp) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (guild_id, channel_id, message_id, author_id, filename, ext, url, timestamp),
    )
    await db.commit()
    return cursor.rowcount > 0


def _build_where(guild_id: str, extension: str | None,
                 channel_id: str | None, author_id: str | None,
                 after: int | None, before: int | None):
    clause = "WHERE guild_id=?"
    params: list[str | int] = [guild_id]
    if extension is not None:
        clause += " AND extension=?"
        params.append(normalize_extension(extension))
    if channel_id:
        clause += " AND channel_id=?"
        params.append(channel_id)
    if author_id:
        clause += " AND author_id=?"
        params.append(author_id)
    if after is not None:
        clause += " AND timestamp>=?"
        params.append(after)
    if before is not None:
        clause += " AND timestamp<=?"
        params.append(before)
    return clause, params


async def search_files(db: aiosqlite.Connection,
                       guild_id: str, extension: str | None = None,
                       channel_id: str | None = None,
                       author_id: str | None = None,
                       after: int | None = None,
                       before: int | None = None,
                       limit: int = 10,
                       offset: int = 0):
    clause, params = _build_where(guild_id, extension, channel_id, author_id, after, before)
    async with db.execute(f"SELECT COUNT(*) FROM files {clause}", params) as cur:
        total = (await cur.fetchone())[0]
    async with db.execute(
        f"SELECT filename, url, channel_id, message_id, author_id, timestamp FROM files {clause} "
        f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ) as cur:
        rows = await cur.fetchall()
    return total, rows
