# Shortvideo V1 · CapCut Pipeline  
# 短视频 V1 · 剪映流程

> **EN**: This repo implements a minimal short-video pipeline for TikTok/Douyin.  
> **中文**：本仓库实现一个面向抖音/TikTok 的「最小可用」短视频生产流水线。

从一个 Douyin/TikTok 链接或本地 mp4 出发，通过后端自动完成：

> Link / mp4 → Parse & Download → Transcribe + Burmese → Burmese TTS → CapCut Pack

最终产物是一个 **CapCut 剪辑包（zip）**，交给剪辑师在剪映/CapCut 里完成创意剪辑。  
V1 **不做** 自动剪辑、自动混剪、卡点等创意工作。

---

## 1. Overview / 项目概览

**EN**

- Backend: FastAPI (Python), deployed on Render.
- Minimal toolchain:
  - Douyin/TikTok parser service (for download URL & metadata)
  - ffmpeg + OpenAI Whisper for audio extraction & ASR
  - GPT-4o / 4o-mini for subtitle-level translation into Burmese
  - LOVO.ai for Burmese TTS
  - CapCut/剪映 (PC) for human editing

**中文**

- 后端框架：FastAPI（Python），当前部署在 Render。
- 最小工具链包含：
  - 抖音/TikTok 解析服务（获取下载地址和基础元数据）
  - ffmpeg + OpenAI Whisper 完成音频抽取与语音转写
  - GPT-4o / 4o-mini 将字幕翻译成缅甸语
  - LOVO.ai 生成缅语配音
  - 剪映/CapCut（PC 版）由剪辑师完成剪辑成片

---

## 2. Workspace Layout / 工作空间目录结构

所有任务都在一个工作空间根目录下运行，例如：

```text
video_workspace/
  tv1_validation/
    raw/        # Step 1: downloaded / uploaded source videos (.mp4)
    edits/      # Step 2 + 3: technical intermediate results
      subs/       # audio + subtitles
        <task_id>.wav
        <task_id>_origin.srt   # original language subtitles
        <task_id>_mm.srt       # Burmese subtitles
      audio/      # TTS voiceover
        <task_id>_mm_vo.wav
      scenes/     # (optional) scene csv / alignment files
    packs/      # Step 4: CapCut packs (.zip)
      <task_id>_capcut_pack.zip
    deliver/    # final exported videos for upload (manual)
    assets/     # reusable assets (BGM, templates, common segments, covers, etc.)

## 3 Rules / 约定

raw/

EN: write-only for the pipeline; we only create new mp4, never modify in place.

中文：流水线只往里写原视频 mp4，不会原地修改。

edits/subs/

EN: everything produced by ffmpeg + Whisper + GPT (wav + SRTs).

中文：ffmpeg 抽音频、Whisper 转写和 GPT 翻译生成的所有中间结果。

edits/audio/

EN: everything produced by LOVO (or future TTS).

中文：LOVO（或其他 TTS）生成的配音音频。

packs/

EN: final zip packs handed off to editors.

中文：打包给剪辑师的剪辑包 zip。

assets/

EN: long-lived, reusable materials (logo, BGM, common segments, CapCut templates, covers…).

中文：长期复用的公共素材，例如 LOGO、BGM、通用片段、剪映模板、封面等。

WORKSPACE_ROOT 环境变量指向 tv1_validation 这一层目录。

## 3. Minimal Toolchain / 最小工具链说明

EN

V1 uses:

Video parsing & download

Douyin/TikTok parser service (already deployed)

Python + httpx to download final mp4 into raw/.

Transcription & translation

ffmpeg → edits/subs/<task_id>.wav

Whisper (whisper-1) → *_origin.srt

GPT-4o / 4o-mini → *_mm.srt (Burmese)

Voiceover

LOVO.ai TTS (LOVO_API_KEY, LOVO_VOICE_ID_MM)

Output to edits/audio/<task_id>_mm_vo.wav.

Editing (human)

Editors use CapCut templates and the pack zip to finish creative work.

中文

V1 工具链包括：

视频解析与下载

调用抖音/TikTok 解析服务获取下载地址

使用 httpx 下载到 raw/<task_id>.mp4

转写与翻译

ffmpeg 抽取音频为 edits/subs/<task_id>.wav

Whisper 生成原语种字幕 *_origin.srt

GPT-4o / 4o-mini 将字幕翻译成缅语 *_mm.srt

缅语配音

调用 LOVO.ai TTS（LOVO_API_KEY，LOVO_VOICE_ID_MM）

输出为 edits/audio/<task_id>_mm_vo.wav

人工剪辑

剪辑师在剪映/CapCut 模板工程中导入上述素材，完成剪辑成片。

## 4. API Overview / 接口总览

所有接口路径统一在 /v1/* 下。

4.1 POST /v1/parse — Parse & Download

解析并下载视频

Request

{
  "task_id": "indoor_makeup_v1",
  "platform": "douyin",
  "link": "https://www.douyin.com/video/7578..."
}


Behaviour / 行为

Call the Douyin/TikTok parser to get download_url, title, author, etc.
调用抖音/TikTok 解析服务，获取下载链接与基础元数据。

Download mp4 into raw/<task_id>.mp4.
将最终 mp4 下载到 raw/<task_id>.mp4。

Response (example)

{
  "task_id": "indoor_makeup_v1",
  "platform": "douyin",
  "title": "Example title",
  "type": "video",
  "download_url": "https://v9-default.365yg.com/...",
  "cover": "https://p3-sign.douyinpic.com/....webp",
  "author": "creator_name",
  "meta": { "duration": 81.8, "width": 1080, "height": 1920 },
  "raw_exists": true,
  "raw_path": "raw/indoor_makeup_v1.mp4"
}


Extra route / 额外接口

GET /v1/tasks/{task_id}/raw   # stream raw/<task_id>.mp4

4.2 POST /v1/subtitles — Transcribe & Translate

转写 + 翻译字幕

Request

{
  "task_id": "indoor_makeup_v1",
  "target_lang": "my",
  "force": false,
  "translate": true
}


Behaviour / 行为

Ensure raw/<task_id>.mp4 exists. （若不存在返回 400）

ffmpeg → edits/subs/<task_id>.wav（抽音频）

Whisper → edits/subs/<task_id>_origin.srt（原语种字幕）

If translate = true：
GPT-4o 翻译字幕文本 → edits/subs/<task_id>_mm.srt（缅语字幕）

Response

{
  "task_id": "indoor_makeup_v1",
  "origin_srt": "edits/subs/indoor_makeup_v1_origin.srt",
  "mm_srt": "edits/subs/indoor_makeup_v1_mm.srt",
  "wav": "edits/subs/indoor_makeup_v1.wav",
  "origin_preview": [
    "00:00:01,000 --> 00:00:02,500 this is very ...",
    "00:00:02,500 --> 00:00:04,000 ..."
  ],
  "mm_preview": [
    "00:00:01,000 --> 00:00:02,500 （Burmese …）",
    "..."
  ]
}


Extra routes / 额外接口

GET /v1/tasks/{task_id}/subs_origin   # 返回 *_origin.srt
GET /v1/tasks/{task_id}/subs_mm       # 返回 *_mm.srt

4.3 POST /v1/dub — Burmese TTS Voiceover

缅语 TTS 配音

Request

{
  "task_id": "indoor_makeup_v1",
  "voice_id": "mm_female_1",
  "force": false
}


Behaviour / 行为

Read edits/subs/<task_id>_mm.srt（若不存在返回 400）。

Convert SRT → plain Burmese text（简单拼接即可）。

Call LOVO TTS with LOVO_API_KEY + voice_id，保存为：
edits/audio/<task_id>_mm_vo.wav。

Response

{
  "task_id": "indoor_makeup_v1",
  "voice_id": "mm_female_1",
  "audio_path": "edits/audio/indoor_makeup_v1_mm_vo.wav",
  "duration_sec": 83.5
}


Extra route / 额外接口

GET /v1/tasks/{task_id}/audio_mm   # stream *_mm_vo.wav

4.4 POST /v1/pack — CapCut Pack

生成剪映剪辑包

Request

{
  "task_id": "indoor_makeup_v1"
}


Behaviour / 行为

Validate that the following files exist / 校验以下文件：

raw/<task_id>.mp4
edits/subs/<task_id>_mm.srt
edits/audio/<task_id>_mm_vo.wav


Create a temp dir tmp/pack_<task_id>/ and copy/rename:

raw.mp4        <- raw/<task_id>.mp4
audio_mm.wav   <- edits/audio/<task_id>_mm_vo.wav
subs_mm.srt    <- edits/subs/<task_id>_mm.srt
README.txt     <- auto-generated instructions for editors


Zip into packs/<task_id>_capcut_pack.zip
压缩上述文件为剪辑包 zip。

Response

{
  "task_id": "indoor_makeup_v1",
  "zip_path": "packs/indoor_makeup_v1_capcut_pack.zip",
  "files": [
    "raw.mp4",
    "audio_mm.wav",
    "subs_mm.srt",
    "README.txt"
  ]
}


Extra route / 额外接口

GET /v1/tasks/{task_id}/pack   # stream zip file

5. Environment Variables / 环境变量

服务从环境变量或 .env 中读取配置：

WORKSPACE_ROOT=/path/to/video_workspace/tv1_validation

# Douyin/TikTok parser service / 解析服务配置
DOUYIN_API_BASE=https://shortvideo-v1-capcut.onrender.com
DOUYIN_API_KEY=...

# OpenAI
OPENAI_API_KEY=sk-xxxx
OPENAI_API_BASE=https://api.openai.com/v1
WHISPER_MODEL=whisper-1
GPT_MODEL=gpt-4o-mini

# LOVO TTS
LOVO_API_KEY=...
LOVO_VOICE_ID_MM=mm_female_1

6. Optional Web UI (/ui) / 可选 Web 调试页面

EN

For internal testing you may add a simple “Pipeline Lab” page at /ui:

One panel per step: parse → subtitles → dub → pack.

Each panel has inputs, a “Run” button, and JSON output.

This is only for debugging; Swagger /docs continues to work.

中文

可选实现一个内部使用的「流程实验室」页面 /ui：

每个步骤一张卡片：解析下载 → 转写翻译 → 配音 → 打包。

每张卡片有输入框、「执行」按钮和 JSON 输出区域。

仅用于调试验证，正式使用仍以 API 和任务编排页为主。

7. End-to-End Example / 端到端示例

POST /v1/parse with a Douyin link → raw/<task_id>.mp4

POST /v1/subtitles → wav + *_origin.srt + *_mm.srt

POST /v1/dub → edits/audio/<task_id>_mm_vo.wav

POST /v1/pack → packs/<task_id>_capcut_pack.zip

Hand the zip to an editor, open a CapCut template project, replace the
placeholders with raw.mp4, audio_mm.wav, subs_mm.srt, then export the
final video into deliver/ and upload to TikTok.

剪辑师拿到 zip 后，在剪映模板工程中替换占位视频/音频/字幕，导出成片到 deliver/，再进行平台发布。
