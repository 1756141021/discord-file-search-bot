# Discord 文件搜索 Bot / Discord File Search Bot

按文件扩展名、发布用户、时间范围、频道搜索 Discord 服务器里的历史附件。  
Search Discord server attachments by file extension, uploader, date range, and channel.

---

## 功能 / Features

- `/search` 支持按 **发布用户 / 时间 / 频道 / 扩展名** 组合搜索。扩展名可填可不填，填的话支持 `pdf` 和 `.pdf` 两种写法。  
  `/search` supports filtering by **uploader / date / channel / extension**. The extension is optional, and both `pdf` and `.pdf` are accepted.
- 搜索结果默认 **仅自己可见**。  
  Search results are **ephemeral by default**.
- 如果本地索引里暂时没有命中，Bot 会优先用 Discord 附件搜索补索引，再查一次；如果附件搜索不可用，才退回扫描历史消息。  
  If nothing is found in the local index, the bot first backfills through Discord attachment search and searches again; if attachment search is unavailable, it falls back to scanning message history.
- 自动补索引默认最多处理 5000 条含附件消息；搜索结果默认最多展示最新 200 条；上下文默认显示目标消息前后各 5 条，都可以在 `/search` 里手动改。  
  Auto-indexing processes up to 5000 messages with attachments by default, search results are capped to the newest 200 by default, and context shows 5 messages before and after the target by default; all can be overridden in `/search`.

### 示例 / Examples

- `/search ext:.safetensors` — 搜索 `.safetensors` 文件 / Search `.safetensors` files
- `/search from_user:@某人` — 搜索某人发过的所有附件 / Search all attachments posted by a user
- `/search from_user:@某人 after:2025-1-1 before:2025-12-31` — 按用户和时间范围搜索；`5` 和 `05` 都能用 / Search by user and date range; both `5` and `05` work
- `/search channel:#资源 ext:zip` — 限定频道搜索 ZIP / Search ZIP files in a specific channel
- `/search ext:mp4 scan_limit:10000 result_limit:300 context_limit:8` — 自定义扫描、结果和上下文上限 / Override scan, result, and context limits
- `/index` — 管理员命令，手动全量回填历史索引 / Admin command to backfill history manually

---

## 部署（中文）

**1. 创建 Bot**

打开 [Discord Developer Portal](https://discord.com/developers/applications)：
- New Application → Bot → Reset Token → 复制 Token
- Bot 页面开启 **Message Content Intent**
- OAuth2 → URL Generator：勾选 `bot` + `applications.commands`
- Bot Permissions 勾选：`Read Messages/View Channels`、`Read Message History`、`Send Messages`、`Embed Links`
- 复制生成的邀请链接，邀请 Bot 进服务器

**2. 安装依赖**

```bash
pip install -r requirements.txt
```

**3. 配置**

```bash
cp .env.example .env
# 编辑 .env，填入 DISCORD_TOKEN
```

**4. 运行**

```bash
python bot.py
```

Bot 上线后斜杠命令会自动同步（可能需要等几分钟才在 Discord 里出现）。

**5. 搜索与索引**

- Bot 启动后会自动索引它上线后的新消息。
- 旧消息里的附件，`/search` 在没命中时会优先用 Discord 附件搜索补索引；如果不可用，才退回扫描历史消息。
- 如果你想手动全量回填，也可以在 Discord 里用管理员账号输入：

```text
/index
```

或指定频道：

```text
/index channel:#资源频道
```

---

## Setup (English)

**1. Create a Bot**

Go to [Discord Developer Portal](https://discord.com/developers/applications):
- New Application → Bot → Reset Token → copy the token
- On the Bot page, enable **Message Content Intent**
- OAuth2 → URL Generator: check `bot` + `applications.commands`
- Bot Permissions: check `Read Messages/View Channels`, `Read Message History`, `Send Messages`, and `Embed Links`
- Copy the generated invite URL and invite the bot to your server

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure**

```bash
cp .env.example .env
# Edit .env and fill in your DISCORD_TOKEN
```

**4. Run**

```bash
python bot.py
```

Slash commands sync automatically on startup (may take a few minutes to appear in Discord).

**5. Search and indexing**

- The bot automatically indexes new messages after it starts.
- For older attachments, `/search` first backfills through Discord attachment search when the local index has no hit; if unavailable, it falls back to scanning history.
- You can still backfill manually as an admin:

```text
/index
```

Or for a specific channel:

```text
/index channel:#your-channel
```

---

## 注意 / Notes

- Discord 附件 URL 有有效期，文件被删除后链接会失效。  
  Discord attachment URLs expire after the file is deleted.
- 数据库文件 `files.db` 保存在运行目录下，建议定期备份。  
  The database `files.db` is stored in the working directory — back it up periodically.

---

## License

MIT
