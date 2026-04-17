#!/usr/bin/env python3
"""批量转写已下载的 B 站音频（faster-whisper base 模型）"""
import os
import glob
from faster_whisper import WhisperModel

INPUT_DIR = "../references/sources/transcripts"
MODEL_SIZE = "base"


def main():
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*_audio.m4a")))
    print(f"找到 {len(files)} 个音频文件，开始转写...")

    for i, audio_path in enumerate(files, 1):
        bvid = os.path.basename(audio_path).replace("_audio.m4a", "")
        out_path = os.path.join(INPUT_DIR, f"{bvid}_transcript.txt")

        if os.path.exists(out_path):
            print(f"[{i}/{len(files)}] {bvid} 已转写，跳过")
            continue

        print(f"[{i}/{len(files)}] 转写 {bvid} ...")
        segments, info = model.transcribe(audio_path, beam_size=5, language="zh")
        text = "\n".join([segment.text for segment in segments])

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[{i}/{len(files)}] {bvid} 完成，字数 {len(text)}")

    print("全部转写完成！")


if __name__ == "__main__":
    main()
