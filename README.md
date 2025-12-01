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
# 根据实际填入 XIONGMAO_API_KEY、OPENAI_API_KEY、LOVO_API_KEY 等
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 本地运行网关服务

```bash
uvicorn gateway.app.main:app --reload
```

测试接口：

```bash
curl -X POST "http://127.0.0.1:8000/v1/parse" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"dy_demo_v1","platform":"douyin","link":"https://www.douyin.com/video/7578478453415851707"}'
```

4. 运行完整流水线（Windows 本地 workspace）

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

## 目录结构

```
gateway/            # Render 可部署的 FastAPI 服务
  app/
    main.py
    settings.py
    providers/
      xiongmao.py
pipeline/           # 本地处理脚本
  run_v1_pipeline.py
  fetch_raw_gateway.py
  transcribe_translate.py
  dubbing_lovo.py
  pack_for_capcut.py
```

## Render 部署说明

- 构建：`pip install -r requirements.txt`
- 启动：`uvicorn gateway.app.main:app --host 0.0.0.0 --port $PORT`
- 在 Render Dashboard 配置环境变量：
  - `XIONGMAO_API_BASE`
  - `XIONGMAO_APP_ID`
  - `XIONGMAO_API_KEY`
  - 其他按需：`OPENAI_API_KEY` 等

网关返回格式保持稳定，后续可将 Xiongmao 换成自研下载服务（如 Douyin_TikTok_Download_API、XHS-Downloader 等）而不影响对外 API。
