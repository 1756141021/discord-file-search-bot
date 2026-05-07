# Discord 文件搜索 Bot / Discord File Search Bot

按文件扩展名搜索 Discord 服务器里的历史附件。  
Search Discord server attachments by file extension.

---

## 功能 / Features

`ext` 参数支持**任意文件后缀**，不限类型。`pdf` 只是示例，`zip`、`psd`、`mp3`、`exe`、`docx` 等所有后缀都能搜。  
The `ext` parameter accepts **any file extension** — `pdf` is just an example. Works with `zip`, `psd`, `mp3`, `exe`, `docx`, or anything else.

- `/search ext:pdf` — 搜索所有 PDF / Search all PDFs
- `/search ext:psd` — 搜索所有 PSD 文件 / Search all PSDs
- `/search ext:zip channel:#资源 from_user:@某人` — 组合过滤 / Combined filters
- `/search ext:mp4 after:2025-01-01 before:2025-12-31` — 按时间范围 / Date range filter
- `/index` — 管理员命令，爬取频道历史建立索引 / Admin command to index channel history

---

## 部署（中文）

**1. 创建 Bot**

打开 [Discord Developer Portal](https://discord.com/developers/applications)：
- New Application → Bot → Reset Token → 复制 Token
- Bot 页面开启 **Message Content Intent**
- OAuth2 → URL Generator：勾选 `bot` + `applications.commands`
- Bot Permissions 勾选：`Read Messages/View Channels`、`Read Message History`
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

**5. 建立历史索引**

Bot 只会自动索引它启动后的新消息。若要索引历史文件，在 Discord 里用管理员账号输入：

```
/index
```

或指定频道：

```
/index channel:#资源频道
```

---

## Setup (English)

**1. Create a Bot**

Go to [Discord Developer Portal](https://discord.com/developers/applications):
- New Application → Bot → Reset Token → copy the token
- On the Bot page, enable **Message Content Intent**
- OAuth2 → URL Generator: check `bot` + `applications.commands`
- Bot Permissions: check `Read Messages/View Channels` and `Read Message History`
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

**5. Index existing files**

The bot only indexes new messages after it starts. To index historical files, run as an admin in Discord:

```
/index
```

Or for a specific channel:

```
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
