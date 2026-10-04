# corpus/ · 语料采集与质控工具

v2.10.0 起从 `scripts/` 迁出。包含 7 个与「训练语料」采集 / 质检相关的脚本，**不属于业务数据管道**。

## 文件清单

| 文件 | 用途 |
|------|------|
| `batch_download_bilibili.py` | yt-dlp 批量下载 B 站 ztalk 视频音频 |
| `batch_transcribe.py` | faster-whisper 批量音频转写 |
| `download_subtitles.sh` | yt-dlp 字幕下载 shell 脚本 |
| `srt_to_transcript.py` | SRT 字幕清洗为纯文本 transcript |
| `merge_research.py` | 多源调研结果合并工具 |
| `quality_check.py` | SKILL.md 质量门 **12 项**检查（pre-commit / CI 必跑） |
| `dual_axis_review.py` | SKILL.md 双轴评审（表达质量 + LLM 深度评审） |

## 与 `scripts/` 的区别

| 目录 | 职责 | 状态 |
|------|------|------|
| `scripts/` | 业务数据管道（K 线同步 / 指标计算 / 报告生成） | 12 个薄壳脚本 |
| `corpus/` | 训练语料采集 + 知识蒸馏质控 | 7 个工具 |

## 调用示例

```bash
# 1. 下载 B 站视频
cd corpus && python batch_download_bilibili.py

# 2. 音频转写
python batch_transcribe.py

# 3. 字幕清洗
python srt_to_transcript.py input.srt > transcript.txt

# 4. 调研合并
python merge_research.py

# 5. SKILL.md 质量门（pre-commit / CI 自动跑，本地手动验证）
python quality_check.py ../SKILL.md
python quality_check.py ../SKILL.md --json
python quality_check.py ../SKILL.md --strict

# 6. 双轴评审（--skip-llm 跳过 LLM 深度评审，无需 API Key）
python dual_axis_review.py ../SKILL.md
python dual_axis_review.py ../SKILL.md --skip-llm
```

## v2.10.0 之前的路径

迁移前的旧路径（已不存在）：
- `scripts/batch_download_bilibili.py` → `corpus/batch_download_bilibili.py`
- `scripts/batch_transcribe.py` → `corpus/batch_transcribe.py`
- `scripts/srt_to_transcript.py` → `corpus/srt_to_transcript.py`
- `scripts/merge_research.py` → `corpus/merge_research.py`
- `scripts/quality_check.py` → `corpus/quality_check.py`
- `scripts/download_subtitles.sh` → `corpus/download_subtitles.sh`

如果你的脚本/文档还引用旧路径，需要同步更新。
