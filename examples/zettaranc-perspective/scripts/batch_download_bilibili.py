#!/usr/bin/env python3
"""批量下载 B 站合集音频（用于 zettaranc ztalk 语料提取）"""
import subprocess
import sys
import json
import urllib.request
import ssl

SERIES_ID = "2194911"
MID = "326246517"
OUTPUT_DIR = "../references/sources/transcripts"


def get_archives():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"https://api.bilibili.com/x/series/archives?mid={MID}&series_id={SERIES_ID}&only_normal=true&sort=asc&pn=1&ps=30"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://space.bilibili.com/{MID}"
    })
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    return json.loads(resp.read().decode("utf-8"))["data"]["archives"]


def download_audio(bvid):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "ba",
        "-o", f"{OUTPUT_DIR}/{bvid}_audio.%(ext)s",
        f"https://www.bilibili.com/video/{bvid}/"
    ]
    print(f"[下载] {bvid} ...")
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    archives = get_archives()
    print(f"共 {len(archives)} 个视频，开始批量下载音频...")
    for item in archives:
        download_audio(item["bvid"])
    print("全部下载完成。")
