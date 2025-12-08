# ShortVideo V1 Pipeline (CapCut)

本仓库目标：输入一条抖音/短视频链接，自动产出可直接导入 CapCut 的剪辑素材包（zip），包含：

- `raw.mp4`：去水印原视频
- `audio_mm.wav`：缅语配音
- `subs_mm.srt`：缅语字幕
- `README.txt`：给剪辑师的使用说明

## 快速开始

1. 复制环境变量模板

```bash
cp .env.example .env
# 根据实际填入 XIONGMAO_API_KEY、OPENAI_API_KEY、LOVO_API_KEY 等；
# SUBTITLES_BACKEND/ASR_BACKEND 控制转写后端，默认 Gemini，也可以设为 whisper（Whisper+GPT）。
# 默认字幕翻译/分段使用 Gemini 2.0 Flash，需要配置 GEMINI_API_KEY（Google AI Studio 密钥）
# 和可选的 GEMINI_MODEL（默认 gemini-2.0-flash）。
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 配置工作目录

`WORKSPACE_ROOT` 默认为 `./workspace`，首次运行会自动创建并按固定结构写入：

```
workspace/
  raw/        # 去水印原视频 <task_id>.mp4
  edits/
    subs/     # 抽取音频 wav + *_origin.srt + *_mm.srt
    audio/    # 缅语配音 *_mm_vo.wav
    scenes/   # 预留场景/对齐文件
  packs/      # <task_id>_capcut_pack.zip
  deliver/    # 剪辑师导出的成片（手动）
  assets/     # 可复用素材（BGM、模版等）
```

4. 本地运行网关服务

```bash
uvicorn gateway.app.main:app --reload
```

测试接口：

```bash
curl -X POST "http://127.0.0.1:8000/v1/parse" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1","platform":"douyin","link":"https://www.douyin.com/video/7578478453415851707"}'
```

5. 运行完整流水线（Windows 本地 workspace）

```bash
python pipeline/run_v1_pipeline.py \
  --task-id dy_1130_v1 \
  --platform douyin \
  --link "https://www.douyin.com/video/7578478453415851707"
```

如果已经有本地 mp4，可跳过下载：

```bash
python pipeline/run_v1_pipeline.py --task-id local_demo_v1 --input-file "raw/local_demo_v1.mp4"
```

## API 说明（4 个步骤）

### 1) `POST /v1/parse`

- 输入：`task_id`、`platform`、`link`
- 逻辑：调用 Xiongmao 解析并下载 mp4 至 `WORKSPACE_ROOT/raw/{task_id}.mp4`
- 输出：解析字段 + `raw_exists`、`raw_path`
- 下载：`GET /v1/tasks/{task_id}/raw`

示例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/parse" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1","platform":"douyin","link":"https://www.douyin.com/video/7578478453415851707"}'
```

### 2) `POST /v1/subtitles`（转写+翻译）

- 输入：`task_id`，可选 `target_lang`（默认缅甸语 my）、`force`、`translate`、`with_scenes`
- 逻辑：检查 raw 是否存在 → 根据 `ASR_BACKEND`（兼容 `SUBTITLES_BACKEND`）选择 Gemini（默认，生成场景段落 JSON + 缅语翻译）或 OpenAI（Whisper/GPT，保留可选 ffmpeg 提取音频路径） → 写入 `_origin.srt`、`_mm.srt`，Gemini 还会生成 `edits/scenes/<task_id>_segments.json`。
- 输出：`wav`（OpenAI+ffmpeg 时存在）、`origin_srt`、`mm_srt`、`segments_json`、`origin_preview`、`mm_preview`
- 下载：`GET /v1/tasks/{task_id}/subs_origin`、`GET /v1/tasks/{task_id}/subs_mm`

示例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/subtitles" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1","target_lang":"my"}'
```

### 3) `POST /v1/dub`（缅语配音）

- 输入：`task_id`，可选 `voice_id`（默认 LOVO_VOICE_ID_MM）、`force`
- 逻辑：读取缅语 SRT 调用 LOVO 生成 `edits/audio/<task_id>_mm_vo.wav`
- 输出：`audio_path`、`duration_sec`
- 下载/试听：`GET /v1/tasks/{task_id}/audio_mm`

示例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/dub" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1"}'
```

### 4) `POST /v1/pack`（打剪辑包）

- 输入：`task_id`
- 逻辑：检查 raw/mm_vo.wav/mm.srt，生成 `packs/<task_id>_capcut_pack.zip`
- 输出：`zip_path`、`files`
- 下载：`GET /v1/tasks/{task_id}/pack`

示例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/pack" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1"}'
```

## Render 部署说明

- 构建：`pip install -r requirements.txt`
- 启动：`uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT`
- 在 Render Dashboard 配置环境变量：
  - `XIONGMAO_API_BASE`
  - `XIONGMAO_APP_ID`
  - `XIONGMAO_API_KEY`
  - `WORKSPACE_ROOT`
  - 其他按需：`OPENAI_API_KEY` 等

网关返回格式保持稳定，后续可将 Xiongmao 换成自研下载服务（如 Douyin_TikTok_Download_API、XHS-Downloader 等）而不影响对外 API。

## V1 Pipeline Lab（Web UI）

为方便在浏览器里逐步验证 V1 链路，可以在 FastAPI 中提供一个极简的 `/ui` 页面（手写 HTML + JS，风格接近 Swagger），串起 4 个步骤：解析下载 → 转写&翻译 → 缅语配音 → 剪辑包打包。

### 页面结构示意

- 顶部：标题 “Shortvideo V1 · Pipeline Lab”，展示当前环境（Render / local）。
- 任务区：Task ID 输入框（可自动生成）、平台选择（douyin/tiktok/local_file）、链接或本地文件上传占位。“一键跑完整流程”按钮可在后续迭代。
- Step 1 解析 & 下载：输入 task_id/platform/link，点击执行 parse。展示解析返回 JSON、raw/<task_id>.mp4 是否生成，并提供“下载 raw.mp4”按钮（使用 `GET /v1/tasks/{task_id}/raw`）。
- Step 2 转写 & 翻译：输入 task_id、目标语言（默认 my 缅甸语），执行后展示 origin/mm SRT 路径、下载按钮、以及前 3~5 句预览。
- Step 3 缅语配音：输入 task_id、voice_id（默认 LOVO_VOICE_ID_MM），执行后展示 wav 路径、下载按钮，并提供 `<audio>` 播放器试听。
- Step 4 剪辑包打包：输入 task_id，执行后展示 packs/<task_id>_capcut_pack.zip 下载按钮，并列出包内文件（raw.mp4、audio_mm.wav、subs_mm.srt、README.txt）。
- 底部：简短说明及当前 .env 配置摘要（不显示敏感值）。

### 配套 API I/O 设计

- ✅ `POST /v1/parse`
  - 请求：`{task_id, platform, link}`
  - 行为：解析下载链接并落盘到 `raw/{task_id}.mp4`。
  - 返回：解析字段（title/type/cover/origin_text 等）+ `raw_exists`、`raw_path`。
  - 下载：`GET /v1/tasks/{task_id}/raw`。
- 🆕 `POST /v1/subtitles`
  - 请求：`{task_id, target_lang:"my", force:false, translate:true}`。
  - 行为：检查 raw 是否存在 → ffmpeg 抽音频 → Whisper 转写 `_origin.srt` → GPT 翻译 `_mm.srt`。
  - 返回：`wav`、`origin_srt`、`mm_srt`、`origin_preview`、`mm_preview`。
  - 下载：`GET /v1/tasks/{task_id}/subs_origin`、`GET /v1/tasks/{task_id}/subs_mm`。
- 🆕 `POST /v1/dub`
  - 请求：`{task_id, voice_id, force:false}`（voice_id 默认 `LOVO_VOICE_ID_MM`）。
  - 行为：读取缅语 SRT，调用 LOVO 生成配音 wav。
  - 返回：`audio_path`、`duration_sec`。
  - 下载/试听：`GET /v1/tasks/{task_id}/audio_mm`（可在 `<audio>` 中引用）。
- 🆕 `POST /v1/pack`
  - 请求：`{task_id}`。
  - 行为：检查 raw/mm_vo.wav/mm.srt，生成 packs/<task_id>_capcut_pack.zip。
  - 返回：`zip_path`、`files` 列表。
  - 下载：`GET /v1/tasks/{task_id}/pack`。

### 最小实现路线

1. 先补齐 `/v1/subtitles`、`/v1/dub`、`/v1/pack` 三个接口，内部直接调用已有脚本逻辑并按上述目录规范读写。
2. 新增一个简单模板 `/ui`，每个 Step 一个按钮直连对应 API，输出区格式化 JSON + 生成的文件下载链接。
3. 等四步都能在 `/ui` 分步跑通后，再迭代“顶部一键跑全流程”和移动端体验。
