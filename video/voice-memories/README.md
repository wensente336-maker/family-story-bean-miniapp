# 家庭录音豆 · 声音没有消失

45秒 / 16:9 / 1280×720 / 24fps。真实Three.js几何场景通过Remotion逐帧渲染，包含中文第三人称旁白、字幕、原创合成环境配乐。

## 镜头

| 秒数 | 内容 |
|---|---|
| 0–7 | 微缩家庭：孩子、妈妈和长辈，发光的声音粒子 |
| 7–13 | 日常场景逐渐安静，声音消散 |
| 13–20 | 根据实拍参考近似建模的银色录音豆：机身、挂带、按键、拾音孔、指示灯 |
| 20–28 | 声音明信片：家庭画面、播放按钮和动态波形 |
| 28–34 | 带唱片沟槽与红色中心标签的旋转黑胶 |
| 34–39 | 明信片向家人展开，声音粒子连接 |
| 39–45 | 录音豆、明信片与黑胶组合，品牌结尾 |

模型按单张产品照片近似还原，并非安克官方CAD或官方宣传片。家庭人物为程序化微缩角色。未使用或仿造真人家庭录音；旁白由本机Tingting语音合成。

## 文件

- `src/models.tsx`：产品、人物、场景与声波几何模型
- `src/scenes/Scenes.tsx`：七个镜头
- `src/index.tsx`：时间轴、排版、字幕、音频
- `audio.cjs`：分镜旁白合成与原创环境音轨
- `public/`：旁白和音轨
- 成片：`../../docs/showcase/family-voice-memories-45s.mp4`

本地借用已安装的视频依赖，通过node_modules符号链接引用 `/Users/Agent 项目开发/zhangbiao-3d-career/node_modules`。迁移到其他机器时运行 `npm install`，需要macOS中文语音服务才能重新生成当前旁白；已有WAV可以直接使用。

渲染：

```sh
npx remotion render src/index.tsx VoiceMemories ../../docs/showcase/family-voice-memories-45s.mp4 --gl=angle --concurrency=3 --browser-executable='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --codec=h264 --crf=19
```

预览编辑：`npm run studio`。

## 火山引擎男声版

新版旁白使用项目已接入的火山引擎 Seed TTS 2.0、云舟 2.0 男声（`zh_male_m191_uranus_bigtts`），语速参数 -8。分镜独立合成、响度统一并对齐画面；保留原视频流，与背景音乐重新混音。此版本是 AI 合成旁白，并非真人录音。

- 新成片：`../../docs/showcase/family-voice-memories-45s-volcengine-male.mp4`
- 音频与合成记录：`public/volcengine-male/`
- 重建：在项目根目录运行 `backend/.venv/bin/python video/voice-memories/volcengine_voiceover.py`，复用后端已配置的凭证，不修改后端默认音色。
