# Backend foundation

当前 Web MVP 支持 15 分钟录音、本地 ASR、Top 3 高光、声音明信片、家庭留声机、互动与限时分享、回收站恢复及隐私删除。四格漫画与电子书代码仍保留，但新的创建入口默认关闭。

## Local setup

请按仓库根目录的 [本地部署与运行说明](../docs/local-development.md) 安装依赖、配置 ASR 模型、依次应用 `0001`～`0024` 迁移并启动 API、Worker 与 Web。该文档是当前本地运行命令的统一入口。

## Contract verification

```bash
source .venv/bin/activate
pytest
python scripts/export_openapi.py
node --test ../miniprogram/tests/api-contract.test.js
```

回滚首个迁移：

```bash
docker compose exec -T postgres psql -U storybean -d storybean < database/migrations/0001_initial.down.sql
```

Mock API：

- `GET /health`
- `GET /v1/mock/home`
- `GET /v1/mock/jobs/{job_id}`
- Swagger UI：`/docs`
- Web 首页契约：`GET /v1/home`

## 微信登录配置

开发环境可使用 `dev:<identity>` code 完成可重复的模拟登录。真实小程序联调时，在 `.env` 中配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，并将 `ALLOW_DEV_WECHAT_LOGIN` 设为 `false`。Secret 仅保存在服务端，不写入小程序代码或版本库。

身份与家庭接口：

- `POST /v1/auth/wechat`
- `GET /v1/session`

## 异步处理与进度

上传完成后会幂等创建 `RECORDING_PIPELINE` 任务并投递到 Celery。入口支持音频、包含音轨的视频、手机浏览器录音和录音豆导出文件。Worker 使用 FFmpeg 提取音轨并临时统一成 16 kHz 单声道 WAV，再调用本地 `mlx-whisper` 模型转写；临时音频在转写结束后删除，转写期间持续更新任务租约心跳。

- `GET /v1/jobs/{job_id}`
- `GET /v1/recordings/{recording_id}/job`
- `POST /v1/jobs/{job_id}/retry`
- `GET /v1/pipeline/status`

任务最多自动重试 2 次，重复消息通过数据库原子领取跳过。Beat 每 30 秒检测超时心跳并重新投递；轮询 `CREATED` 任务也会在 Redis 恢复后机会性补投。可用 `PIPELINE_ACCEPT_NEW_JOBS=false` 暂停新任务。
- `POST /v1/families`
- `GET/PATCH /v1/families/{family_id}`
- `POST /v1/families/{family_id}/members`
- `PATCH /v1/families/{family_id}/members/{member_id}`

## 转写、人物映射与回放

- `GET /v1/recordings/{recording_id}/transcript`
- `PATCH /v1/recordings/{recording_id}/transcript/segments/{segment_id}`
- `PUT /v1/recordings/{recording_id}/speakers/{speaker_key}`
- `POST /v1/recordings/{recording_id}/playback-url`
- `GET /v1/playback/{signed_token}`

说话人分组是保守的声学 A/B/C 候选，不会自动声称识别出某个真实家庭成员。用户可将 A/B/C 映射为家庭成员，也可逐段修正说话人和文字。播放地址为短时签名 URL，与上传凭证不通用，并支持 HTTP Range 拖动。

本地模型配置：

这台 Mac 将可复用的模型统一放在 `/Users/WIN11/AI-Models/`。家庭故事豆当前使用
`/Users/WIN11/AI-Models/whisper-large-v3-turbo-mlx`；在自己的环境中将下方两个路径
替换为对应的共享目录即可。原项目模型路径保留兼容符号链接，供仍引用旧路径的本机进程使用。

```env
ASR_PROVIDER=mlx_whisper
ALLOW_DEMO_ASR=false
ASR_MODEL_PATH=/absolute/path/to/whisper-large-v3-turbo-mlx
ASR_RETRY_MODEL_PATH=/absolute/path/to/whisper-large-v3-turbo-mlx
ASR_RETRY_ENABLED=true
ASR_MAX_RETRY_SEGMENTS=8
ASR_INITIAL_PROMPT=请忠实转写为简体中文，保留人物名称、自然标点和完整语义。
ASR_LANGUAGE=zh
ASR_LOW_CONFIDENCE_THRESHOLD=0.65
PLAYBACK_TOKEN_TTL_SECONDS=600
```

固定演示逐字稿只允许显式用于本地开发或测试：必须同时设置
`APP_ENV=development`、`ASR_PROVIDER=demo` 和 `ALLOW_DEMO_ASR=true`。
生产环境即使误设 `ASR_PROVIDER=demo` 也会拒绝处理，避免把演示台词写入真实家庭录音。

合成回归集可用以下命令重建并评估：

```bash
python scripts/build_asr_eval_set.py /tmp/storybean-asr-eval
PYTHONPATH=. python scripts/evaluate_asr.py /tmp/storybean-asr-eval \
  --output ../docs/asr-eval-report.json
```

## 高光与统一故事板

Worker 在转写后根据欢乐、温暖、惊喜、情绪表达、家人参与度、故事完整度和转写可信度生成 Top 3。排序是确定性的，每个分数维度均可向用户解释。所有家人直接引语仅能来自 `transcript_segments`，并必须保留片段 ID 和原音时间戳。

- `GET /v1/recordings/{recording_id}/moments`
- `POST /v1/recordings/{recording_id}/moments/rebuild`
- `GET /v1/moments/{moment_id}`
- `PATCH /v1/moments/{moment_id}`

用户可将高光标记为保留或不保留，并调整原声起止边界。边界修改会重新计算故事板的原话引用，所有操作记入 `moment_feedback`。

```bash
PYTHONPATH=. python scripts/evaluate_moments.py \
  --output ../docs/moment-eval-report.json
```

## 四格家庭漫画

- `POST /v1/moments/{moment_id}/comics`
- `GET /v1/comics/{comic_id}`
- `POST /v1/comics/{comic_id}/panels/{panel_index}/regenerate`

只有用户已保留的高光才能生成漫画。四格共用一份 `visual_bible`，原话对白保存转写片段 ID，单格重画不改动其他分镜。MVP 使用内置生成图片和本地资产适配器；按每个家庭故事实时调用生图模型、队列化、限流和成本管理留待上线化阶段。

## 家庭播客

- `POST /v1/podcasts`
- `GET /v1/podcasts/{podcast_id}`
- `PATCH /v1/podcasts/{podcast_id}`
- `POST /v1/podcasts/{podcast_id}/playback-url`
- `GET /v1/ops/podcast-metrics`：发布门禁指标，不返回家庭或资产标识。
- `POST /v1/ops/recordings/{recording_id}/rollback`：回退到上一完成版本。
- `POST /v1/ops/podcast-shares/revoke-all-test`：带确认口令撤销当前家庭分享。

发布灰度由 `PODCAST_ROLLOUT_MODE=open|allowlist|off`、
`PODCAST_CREATION_ENABLED` 和 `PODCAST_SHARING_ENABLED` 控制。关闭新增不会阻断已有播客的读取、播放和下载。

播客可编排 1–3 个已保留高光。服务端默认使用火山引擎豆包 HTTP V3 大模型 TTS 生成真人感主持人旁白，使用 FFmpeg 剪辑原声、统一响度并与本地生成的双音环境床混音。它不克隆家人声音；云端 TTS 失败时会自动使用 macOS 系统音色，再失败则降级为原声精剪版。

凭证只能配置在后端 `.env`：

```env
PODCAST_TTS_PROVIDER=volcengine
PODCAST_TTS_FALLBACK_TO_SYSTEM=true
VOLCENGINE_TTS_APP_ID=
VOLCENGINE_TTS_ACCESS_TOKEN=
# 新版控制台仅提供 API Key 时，改填这一项
VOLCENGINE_TTS_API_KEY=
VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
VOLCENGINE_TTS_VOICE=zh_female_xiaohe_uranus_bigtts
```

## 沉浸式家庭电子书

电子书以漫画作品为来源，主记录保存当前版本，`storybook_versions` 保存不可变 Manifest 快照。漫画版本未变化时重复创建是幂等的；任一分镜重画使漫画版本增加后，再同步电子书会追加新版本，旧快照仍可读取。

- `POST /v1/comics/{comic_id}/storybook`
- `GET /v1/storybooks/{storybook_id}`
- `GET /v1/storybooks/{storybook_id}/versions`
- `GET /v1/storybooks/{storybook_id}/versions/{version}`
- `POST /v1/storybooks/{storybook_id}/audio-session`

Manifest 固定页面顺序、漫画格版本、真实原声片段 ID 与毫秒级时间轴，为后续服务端配音、分享和 PDF 导出提供统一输入。

首次创建音频会使用 FFmpeg 将每个入选原声时间段裁成独立 MP3，统一为单声道和适合对白的响度。书页只拿到十分钟有效的签名播放地址，不会暴露完整家庭录音；相同书册版本再次请求会复用已有资产。删除漫画、录音或整个家庭时，对应书页音频也会随隐私删除流程一并清理。

## 录音上传

本地 MVP 使用私有文件目录模拟对象存储；客户端仍通过短期签名 PUT URL 直传，替换为 S3/OSS 时无需改变前端流程。服务端使用 FFprobe 识别真实格式与时长，并校验 SHA-256。

- `POST /v1/recordings`
- `PUT /v1/uploads/{signed_token}`
- `POST /v1/recordings/{recording_id}/upload-complete`
- `GET /v1/recordings`
- `GET /v1/recordings/{recording_id}`
- `DELETE /v1/recordings/{recording_id}`（仅草稿或失败记录）

支持 MP3、M4A、WAV、AAC，最长 15:00，最大 100 MB。上传凭证默认 15 分钟有效，原始录音默认设置 7 天清理时间。

## 时间线、隐私与分享

- `GET /v1/timeline`
- `POST /v1/creations/{creation_id}/shares`
- `GET/DELETE /v1/shares/{share_id}`
- `GET /v1/public/shares/{token}`
- `GET/PUT /v1/privacy`
- `DELETE /v1/privacy/creations/{creation_id}`
- `DELETE /v1/privacy/recordings/{recording_id}`
- `DELETE /v1/privacy/families/{family_id}`
- `GET /v1/ops/family-metrics`

分享令牌只以 SHA-256 摘要保存。Celery Beat 每小时清理到期原始录音，只移除源文件并保留转写与作品。可用隔离脚本验证分享撤销、数据库级联、文件清理和删除审计：

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_lifecycle.py
```

## Web 手机号登录

本地开发可在 `.env` 中启用一次性测试验证码：

```env
ALLOW_DEV_WEB_OTP=true
WEB_OTP_DEV_CODE=123456
```

默认值为关闭。公网环境必须保持关闭并接入真实短信供应商，不能使用固定验证码。

- `POST /v1/auth/otp/request`
- `POST /v1/auth/otp/verify`
- `GET /v1/session`
