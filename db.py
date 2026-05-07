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
            timestamp  INTEGER NOT NULL
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_guild_ext ON files(guild_id, extension)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_channel   ON files(channel_id)")
    await db.commit()


async def insert_file(db: aiosqlite.Connection,
                      guild_id: str, channel_id: str, message_id: str,
                      author_id: str, filename: str, url: str, timestamp: int):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    async with db.execute(
        "SELECT 1 FROM files WHERE message_id=? AND filename=?", (message_id, filename)
    ) as cur:
        if await cur.fetchone():
            return False
    await db.execute(
        "INSERT INTO files(guild_id,channel_id,message_id,author_id,filename,extension,url,timestamp) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (guild_id, channel_id, message_id, author_id, filename, ext, url, timestamp),
    )
    await db.commit()
    return True


async def search_files(db: aiosqlite.Connection,
                       guild_id: str, extension: str,
                       channel_id: str | None = None,
                       author_id: str | None = None,
                       after: int | None = None,
                       before: int | None = None,
                       limit: int = 10,
                       offset: int = 0):
    query = "SELECT filename, url, channel_id, author_id, timestamp FROM files WHERE guild_id=? AND extension=?"
    params: list = [guild_id, extension.lower().lstrip(".")]
    if channel_id:
        query += " AND channel_id=?"
        params.append(channel_id)
    if author_id:
        query += " AND author_id=?"
        params.append(author_id)
    if after is not None:
        query += " AND timestamp>=?"
        params.append(after)
    if before is not None:
        query += " AND timestamp<=?"
        params.append(before)
    count_query = query.replace(
        "SELECT filename, url, channel_id, author_id, timestamp", "SELECT COUNT(*)"
    )
    async with db.execute(count_query, params) as cur:
        total = (await cur.fetchone())[0]
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return total, rows
