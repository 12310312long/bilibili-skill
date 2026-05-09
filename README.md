# B站 Skill — Bilibili API Tool

用于 [Claude Code](https://claude.ai/code) 的 B站操作技能。通过 CDP 浏览器获取登录态，调用 B站 REST API 完成各项操作。

## 功能

- **视频信息** — 获取标题、时长、aid、bvid、cid 等
- **视频下载** — 支持充电视频，自动合并 DASH 视频+音频为 MP4
- **点赞 / 收藏** — 单独或一键操作
- **评论** — 查看评论、发表评论、回复评论
- **私信** — 发送文字私信（支持新联系人）
- **用户信息** — 查询用户资料、视频列表
- **Cookie 管理** — 从 CDP 浏览器提取，导出供 yt-dlp 使用

## 前置条件

1. Chrome/Edge 已登录 [bilibili.com](https://www.bilibili.com)
2. CDP 代理运行中（通过 `web-access` skill 启动）
3. Python 依赖：`requests`

## 快速开始

```bash
# 加载 cookie
python bilibili_api.py load-cookies

# 视频信息
python bilibili_api.py info BV1xx411c7mD

# 下载视频
python bilibili_api.py download BV1xx411c7mD

# 点赞 + 收藏
python bilibili_api.py like-fav BV1xx411c7mD

# 查看评论
python bilibili_api.py comments BV1xx411c7mD

# 发送私信
python bilibili_api.py send-msg 12345678 "你好"

# 用户信息
python bilibili_api.py user 266765166
python bilibili_api.py user-videos 266765166
```

## Python API

```python
import sys
sys.path.insert(0, "path/to/bilibili-skill")
from bilibili_api import *

load_cookies_from_cdp()

# 视频信息
info = video_info(bvid="BV1xx411c7mD")

# 点赞
like_video(bvid="BV1xx411c7mD")

# 收藏
favorite_video(bvid="BV1xx411c7mD")

# 评论
post_comment(bvid="BV1xx411c7mD", message="评论内容")

# 私信
send_private_message(receiver_id=12345678, message="你好")
send_private_message(receiver_id=12345678, message="你好", from_firework=1)

# 下载
download_video("BV1xx411c7mD", output_dir="D:/videos")

# 用户
user_info(uid="266765166")
user_videos(uid="266765166")
```

## 技术要点

- **API 优先**：点赞/收藏/评论/私信均通过 REST API（Cookie + CSRF），比操作 DOM 快 10 倍
- **下载用 CDP**：从 `window.__playinfo__` 提取 DASH 流 URL，支持充电视频
- **CSRF token**：`bili_jct` cookie 的值即为 CSRF token
- **Referer 头**：所有 API 请求需要 `Referer: https://www.bilibili.com/`

## License

MIT
