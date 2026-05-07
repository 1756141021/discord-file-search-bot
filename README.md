# Discord 文件搜索 Bot

按文件扩展名搜索 Discord 服务器里的历史附件。

## 功能

- `/search ext:pdf` — 搜索所有 PDF 文件
- `/search ext:zip channel:#资源 from_user:@某人` — 组合过滤
- `/search ext:mp4 after:2025-01-01 before:2025-12-31` — 按时间范围
- `/index` — 管理员命令，爬取频道历史建立索引

## 部署

**1. 创建 Bot**

打开 [Discord Developer Portal](https://discord.com/developers/applications)：
- New Application → Bot → Reset Token → 复制 Token
- Bot 页面开启 `Message Content Intent`
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

## 注意

- Discord 附件 URL 有有效期，链接会在文件被删除后失效
- 数据库文件 `files.db` 在运行目录下，可以定期备份
