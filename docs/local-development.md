# 家庭故事豆（家庭录音豆）本地部署与运行

本文以当前 Web MVP 代码为准，适合在 **Apple Silicon Mac** 上运行完整的录音转写与作品生成链路。当前主入口是浏览器 Web 应用；`miniprogram/` 和 `preview/` 是早期参考，不参与以下启动步骤。

## 项目概览

用户在 Web 端上传录音、带音轨视频或录音豆导出的文件。后端异步提取音轨，用本地 MLX Whisper 转写并发现候选高光。家人校对文字、人物和片段后，可以保存“一句话 + 图片 + 原声片段”的**声音明信片**，或把多段原声与解说混音为**家庭留声机**。作品支持播放、点赞、评论、限时分享和移入回收站后恢复。

当前默认隐藏新的漫画与绘本创建入口；仓库仍保留旧作品的查看代码。录音豆通过**导出文件再上传**接入，当前没有蓝牙直连流程。

| 组件 | 当前实现 | 本地位置 |
|---|---|---|
| Web | React、TypeScript、Vite | `http://127.0.0.1:4173` |
| API | FastAPI | `http://127.0.0.1:8000` |
| 录音处理 | Celery Worker、FFmpeg、MLX Whisper | 后台进程 |
| 数据库与队列 | PostgreSQL 17、Redis 7.4 | 端口 `5432`、`6379` |
| 私有媒体 | 本地文件目录、短时签名链接 | `backend/.data/objects` |
| 解说配音 | 火山引擎 TTS，可降级为 macOS 系统语音 | 后端配置 |

## 1. 安装前准备

- Apple Silicon macOS。默认 ASR 使用 `mlx-whisper`；其他系统不能直接照此文档运行完整转写链路。
- Python 3.12、Node.js `20.19+` 或 `22.12+`、npm、Docker Desktop（含 Compose）、FFmpeg 与 FFprobe。
- 一份 MLX 格式的 `whisper-large-v3-turbo` 模型目录，含 `config.json` 和 `weights.safetensors`。模型不在仓库内；可准备 `mlx-community/whisper-large-v3-turbo` 对应的本地文件。本项目这台 Mac 的现有路径是 `/Users/WIN11/AI-Models/whisper-large-v3-turbo-mlx`，换机器时改为自己的绝对路径。
- 火山引擎配音凭证可选。没有凭证时，macOS 系统语音可作为降级；真实转写仍需要本地 ASR 模型。

检查本机命令：

```bash
python3.12 --version
node --version
npm --version
docker compose version
ffmpeg -version
ffprobe -version
```

下文假设已取得项目代码。将示例路径替换为自己的仓库绝对路径；路径有空格时保留引号。

```bash
cd "/path/to/family-story-bean-miniapp"
```

## 2. 安装依赖与配置

### 后端

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

如果本机还没有模型，可在网络可访问模型仓库时下载一次。把 `local_dir` 改成准备存放模型的**绝对路径**；模型文件较大，下载时间取决于网络。

```bash
.venv/bin/python -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/whisper-large-v3-turbo", local_dir="/你的绝对路径/whisper-large-v3-turbo-mlx")'
```

首次安装时，把 `backend/.env.example` 复制为 `backend/.env`；**已有 `.env` 不要覆盖**，其中可能保存凭证与本地模型路径。至少检查并修改以下配置：

```env
APP_ENV=development
ASR_PROVIDER=mlx_whisper
ASR_MODEL_PATH=/你的绝对路径/whisper-large-v3-turbo-mlx
ASR_RETRY_MODEL_PATH=/你的绝对路径/whisper-large-v3-turbo-mlx
AUTH_SIGNING_KEY=替换为一段足够长的随机字符串
ALLOW_DEV_WEB_OTP=true
WEB_OTP_DEV_CODE=123456
PODCAST_RENDER_DISPATCHER=local
```

可以先用 `cp .env.example .env` 创建新配置，再编辑上述值。固定验证码**只供本机开发**。`ASR_MODEL_PATH` 必须指向实际存在的模型目录；否则上传后的转写任务会失败。后端密钥只放在 `backend/.env`，不要写进 `web/.env.local`。

要使用项目接入的火山引擎 TTS，在 `backend/.env` 中填写 `VOLCENGINE_TTS_APP_ID`，并按账号凭证类型填写 `VOLCENGINE_TTS_ACCESS_TOKEN` 或 `VOLCENGINE_TTS_API_KEY`；资源 ID 与音色要对应已开通的资源。默认 `PODCAST_TTS_PROVIDER=auto` 优先尝试可用的火山引擎配置，再按设置降级。无需云配音时保留示例中的空凭证。

### Web

打开另一个终端，在仓库根目录运行：

```bash
cd web
npm ci
```

首次安装时，把 `web/.env.example` 复制为 `web/.env.local`。本地默认值应为：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_DATA_SOURCE=api
VITE_ENABLE_COMIC_CREATION=false
VITE_ENABLE_PODCAST_CREATION=true
```

## 3. 启动数据库并初始化表结构

在 `backend/` 目录运行：

```bash
docker compose up -d postgres redis
docker compose ps
```

**仅对全新的空数据库执行一次**下面的迁移循环。当前代码包含 `0001`～`0024` 共 24 个正向迁移；`*.down.sql` 是回滚文件，不能混入初始化。已有数据的数据库不要重跑全部脚本，应先确认已执行到哪个版本，再只补缺失迁移。

```bash
find database/migrations -maxdepth 1 -type f \
  -name '[0-9][0-9][0-9][0-9]_*.sql' ! -name '*.down.sql' -print \
  | sort \
  | while IFS= read -r migration_file; do
      docker compose exec -T postgres \
        psql -v ON_ERROR_STOP=1 -U storybean -d storybean \
        < "$migration_file" || exit 1
    done
```

数据库容器使用 `backend/docker-compose.yml` 中的本地开发账号。Compose 的 PostgreSQL 命名卷保存数据；停止服务不会清空记录。上传媒体另存于 `backend/.data/objects`，迁移或备份时要同时考虑这两部分。

## 4. 分别运行三个进程

保持数据库和 Redis 运行，在三个终端分别执行。**后端命令都从 `backend/` 目录启动**，使 `.env` 和相对媒体目录正确解析。

终端 A：API

```bash
cd "/path/to/family-story-bean-miniapp/backend"
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端 B：录音处理 Worker 与定时任务

```bash
cd "/path/to/family-story-bean-miniapp/backend"
.venv/bin/python -m celery -A worker.main.celery_app worker \
  --beat --loglevel=INFO --pool=solo \
  -Q pipeline,pipeline.maintenance,pipeline.dead,podcast
```

终端 C：Web

```bash
cd "/path/to/family-story-bean-miniapp/web"
npm run dev
```

默认 `PODCAST_RENDER_DISPATCHER=local` 时，播客渲染由 API 后台任务执行；Worker 负责上传后的转写和高光分析。如果改为 `celery`，播客生成也使用 Worker 监听的 `podcast` 队列。

## 5. 验证与体验

```bash
curl http://127.0.0.1:8000/health
```

返回 `{"status":"ok",...}` 表示 API 已启动。打开 `http://127.0.0.1:4173`，在本地开发配置下可用测试手机号请求验证码，并输入 `.env` 中的 `WEB_OTP_DEV_CODE`（示例为 `123456`）。首次登录后创建家庭空间，上传一段**不超过 15 分钟**的音频或带音轨视频。待处理完成，进入故事确认页保存声音明信片，或继续创作家庭留声机。

可检查 Web 构建与测试，以及后端测试：

```bash
cd "/path/to/family-story-bean-miniapp/web"
npm run build
npm test
```

```bash
cd "/path/to/family-story-bean-miniapp/backend"
.venv/bin/python -m pytest
```

API 文档位于 `http://127.0.0.1:8000/docs`。停止开发服务时，在三个前台终端按 `Ctrl+C`；数据库与 Redis 可在 `backend/` 目录用 `docker compose stop` 暂停。

## 6. 常见问题

| 现象 | 首先检查 |
|---|---|
| 页面可打开，但登录或数据请求失败 | API 是否在 `8000` 端口、`web/.env.local` 的 `VITE_API_BASE_URL` 是否一致，以及 `backend/.env` 的 `WEB_CORS_ORIGINS` 是否包含 Web 地址。 |
| 请求验证码返回“短信服务尚未配置” | 本地 `.env` 是否设置 `ALLOW_DEV_WEB_OTP=true` 和 `WEB_OTP_DEV_CODE`；公开环境应接入真实短信服务。 |
| 上传后一直不转写 | Redis 和 Celery Worker 是否运行，`ASR_MODEL_PATH` 是否为存在的 MLX 模型目录，FFmpeg/FFprobe 是否在 PATH 中。 |
| 播客没有火山引擎配音 | 检查后端凭证、`VOLCENGINE_TTS_RESOURCE_ID` 与 `VOLCENGINE_TTS_VOICE` 是否匹配；系统可能按配置使用 macOS 语音降级。 |
| 数据库报表或字段不存在 | 确认是否按顺序应用到 `0024_family_gramophone.sql`；不要在已有数据库上重放全部迁移。 |
| `5432`、`6379`、`8000` 或 `4173` 被占用 | 停止冲突进程，或同步修改 Compose、后端连接地址、Web API 地址和 CORS 配置。 |

本地流程使用 `127.0.0.1` 和 HTTP；若开放给其他设备或公网，还需要独立处理 HTTPS、真实短信、密钥、持久化存储、访问控制与模型部署容量。此文档不将本地启动等同于生产部署。
