---
name: bilibili
description: B站/Bilibili 操作技能。涵盖视频下载（含充电视频）、点赞、收藏、评论、用户信息查询。需要用户 Chrome/Edge 已登录 B站，通过 CDP 浏览器获取登录态。
---

# B站 操作技能

## 前置条件

1. Python 3.8+，安装依赖：`pip install requests websocket-client`
2. Chrome/Edge 已登录 B站（用于自动提取 Cookie）

## 获取 Cookie

**自动提取（推荐）**

`load_cookies_from_cdp()` 会自动启动浏览器并通过 Chrome DevTools Protocol 直接提取 Cookie，无需任何代理：

```python
from bilibili_api import load_cookies_from_cdp
load_cookies_from_cdp()
```

**手动方式**

也可以从浏览器控制台手动导出：

```bash
# 在浏览器控制台执行以下 JS，复制输出内容
document.cookie.split(';').map(c => c.trim()).join('\n')
# 保存为文件后用 Python 加载
```

```python
from bilibili_api import load_cookies_from_file
load_cookies_from_file("bilibili_cookies.txt")
```

## 功能清单

### 视频信息

```bash
python "bilibili_api.py" info <视频BVID>
```

### 点赞 + 收藏

```bash
# 分别操作
python "bilibili_api.py" like <视频BVID>
python "bilibili_api.py" fav <视频BVID>

# 一键点赞+收藏
python "bilibili_api.py" like-fav <视频BVID>
```

### 评论

```bash
# 查看评论
python "bilibili_api.py" comments <视频BVID>

# 发评论（需在 Python 代码中调用）
```

```python
from bilibili_api import post_comment
post_comment(bvid="<视频BVID>", message="评论内容")
```

### 视频下载

```bash
python "bilibili_api.py" download <视频BVID>
```

- 通过 CDP 从 `window.__playinfo__` 提取最高清流地址
- 自动合并 DASH 视频+音频为 MP4
- **充电视频也能下**（只要账号已充电并播放页面可见）

### 私信

```bash
python "bilibili_api.py" send-msg <对方UID> <消息内容>
```

```python
from bilibili_api import send_private_message

# 发送私信（普通）
send_private_message(receiver_id=<对方UID>, message="<消息内容>")

# from_firework=1 可对未聊过的新联系人发送（突破 1 条限制）
send_private_message(receiver_id=<对方UID>, message="<消息内容>", from_firework=1)
```

### 用户信息

## Python API 参考

```python
from bilibili_api import *

# 从浏览器自动提取 Cookie（无需手动导出）
load_cookies_from_cdp()

# 视频信息
info = video_info(bvid="<视频BVID>")
# => {"aid": 123, "bvid": "<视频BVID>", "title": "...", "cid": ..., "duration": ...}

# 点赞
like_video(bvid="<视频BVID>")

# 收藏（默认收藏夹）
favorite_video(bvid="<视频BVID>")

# 获取收藏夹列表
folders = favorite_folders()

# 一键点赞+收藏
like_and_favorite_video("<视频BVID>")

# 评论
comments = get_comments(bvid="<视频BVID>")
post_comment(bvid="<视频BVID>", message="评论内容")

# 回复评论
post_comment(bvid="<视频BVID>", message="回复内容", root=评论rpid, parent=父评论rpid)

# 视频下载（支持充电视频）
path = download_video("<视频BVID>", output_dir="D:/videos")

# 用户信息
user = user_info(uid="<用户UID>")
videos = user_videos(uid="<用户UID>")

# 私信
send_private_message(receiver_id=<对方UID>, message="<消息内容>")
send_private_message(receiver_id=<对方UID>, message="<消息内容>", from_firework=1)

# 导出 cookie 供 yt-dlp 使用
export_cookies_for_ytdlp()
```

## 技术要点

- **API 优先**：点赞/收藏/评论优先用 REST API（Cookie + CSRF），比 CDP 点击 DOM 快 10 倍
- **下载用 CDP**：从 `window.__playinfo__` 提取 DASH 流 URL，解决充电视频的鉴权问题
- **CSRF token**：`bili_jct` cookie 的值即为 CSRF token
- **Referer 头**：所有 API 请求需要 `Referer: https://www.bilibili.com/`
