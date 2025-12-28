# Smart Pack v1.7 - YouCut Ready

Release note: `release/v1.7` is frozen; only critical bugfixes are allowed. New features must target v1.8+.

??????? **YouCut????** ??????????????????????????


---

## 目录结构（请勿修改）
.
├── raw/
│ └── raw.mp4 # 原始视频
├── audio/
│ └── voice_my.wav # 主音轨（当 tts=true 时生成）
├── subs/
│ └── my.srt # 字幕文件（源文本）
├── scenes/
│ └── scene_001.mp4 # 场景素材（可选占位）
├── manifest.json # 包描述（冻结）
└── README.md # 使用说明（本文件）

---

## 在 YouCut 中的推荐导入顺序
1. 打开 **YouCut**
2. 新建项目 → 导入视频：`raw/raw.mp4`
3. 导入音频：`audio/voice_my.wav`
4. 导入字幕：`subs/my.srt`
5. 在时间轴中进行**人工对齐**（见下方建议）

> 注意：请保持文件名与目录结构不变，否则可能影响后续校验与复用。

---

## 字幕与配音的人工对齐建议
- 将 `voice_my.wav` 作为**主音轨**
- 将字幕整体拖动到音频开始位置
- 若存在轻微错位：
  - 以音频为准微调字幕起始时间
  - 不建议逐句精调（v1.7 目标是效率优先）

---

## 常见问题（FAQ）
**Q：为什么不自动对齐字幕？**  
A：v1.7 聚焦“可用闭环”，自动对齐属于 v1.8 规划范围。

**Q：可以替换音频或字幕吗？**  
A：可以，但请保持文件路径与文件名不变。

**Q：没有生成 voice_my.wav 怎么办？**  
A：确认生成时 `tts=true`；或手动替换音频文件。

---

## 版本说明
- Pack 版本：v1.7
- 生成方式：Smart Pack Pipeline（YouCut Ready）
- 特性：结构冻结、支持 Edge TTS、支持云分发
