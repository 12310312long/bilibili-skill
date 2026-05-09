# B站 Skill — Bilibili API Tool

用于操作 B站 的 Python 工具集。通过浏览器 CDP 或手动 Cookie 登录，调用 B站 REST API 完成各项操作。

## 功能

- **视频信息** — 获取标题、时长、aid、bvid、cid 等
- **视频下载** — 支持充电视频，自动合并 DASH 视频+音频为 MP4
- **点赞 / 收藏** — 单独或一键操作
- **评论** — 查看评论、发表评论、回复评论
- **私信** — 发送文字私信（支持新联系人）
- **用户信息** — 查询用户资料、视频列表
- **Cookie 管理** — 从 CDP 浏览器提取，导出供 yt-dlp 使用

## 前置条件

- Python 3.8+，安装依赖：`pip install requests`
- 一个已登录 B站的 Chrome/Edge 浏览器（用于自动提取 Cookie）

## Cookie 登录

**方式一：自动提取（推荐）**

`load_cookies_from_cdp()` 会自动启动 Edge 浏览器并提取 Cookie。需要本目录同级有 `web-access/scripts/cdp-proxy.mjs`（或自行配置 CDP 代理），否则请用方式二。

**方式二：手动导出**

1. 浏览器打开 [bilibili.com](https://www.bilibili.com) 并登录
2. 按 F12 → 控制台执行：
   ```js
   document.cookie.split(';').map(c => c.trim()).join('\n')
   ```
3. 将输出保存为 `bilibili_cookies.txt`
4. 加载：
   ```python
   from bilibili_api import load_cookies_from_file
   load_cookies_from_file("bilibili_cookies.txt")
   ```

## 快速开始

```bash
# 加载 cookie（自动模式）
python bilibili_api.py load-cookies

# 视频信息
python bilibili_api.py info <视频BVID>

# 下载视频
python bilibili_api.py download <视频BVID>

# 点赞 + 收藏
python bilibili_api.py like-fav <视频BVID>

# 查看评论
python bilibili_api.py comments <视频BVID>

# 发送私信
python bilibili_api.py send-msg <对方UID> "<消息内容>"

# 用户信息
python bilibili_api.py user <用户UID>
python bilibili_api.py user-videos <用户UID>
```

## Python API

```python
from bilibili_api import *

# 加载 cookie
load_cookies_from_file("bilibili_cookies.txt")
# 或自动提取（需 CDP 代理）
# load_cookies_from_cdp()

# 视频信息
info = video_info(bvid="<视频BVID>")

# 点赞
like_video(bvid="<视频BVID>")

# 收藏
favorite_video(bvid="<视频BVID>")

# 评论
post_comment(bvid="<视频BVID>", message="评论内容")

# 私信
send_private_message(receiver_id=<对方UID>, message="<消息内容>")
send_private_message(receiver_id=<对方UID>, message="<消息内容>", from_firework=1)

# 下载（需要 CDP 代理）
download_video("<视频BVID>", output_dir="D:/videos")

# 用户
user_info(uid="<用户UID>")
user_videos(uid="<用户UID>")
```

## 技术要点

- **API 优先**：点赞/收藏/评论/私信均通过 REST API（Cookie + CSRF），比操作 DOM 快 10 倍
- **下载用 CDP**：从 `window.__playinfo__` 提取 DASH 流 URL，支持充电视频
- **CSRF token**：`bili_jct` cookie 的值即为 CSRF token
- **Referer 头**：所有 API 请求需要 `Referer: https://www.bilibili.com/`

## License

MIT
