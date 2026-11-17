# -*- coding: utf-8 -*-
"""给角色库补预览图：按角色 tag 去 safebooru 抓一张 SFW 图，转成 320px webp。

为什么是独立脚本：抓图需要能上外网，插件本身不该在运行时联网。
在你自己的机器上跑一次即可（ComfyUI 自带 Pillow，不用另装）。

用法：
    python tools/fetch_thumbs.py                    # 只补缺图的
    python tools/fetch_thumbs.py --all              # 全部重抓
    python tools/fetch_thumbs.py --only mihoyo      # 只抓米哈游新增的那批
    python tools/fetch_thumbs.py --proxy http://127.0.0.1:7890
    python tools/fetch_thumbs.py --limit 20         # 先试 20 个

抓完重启 ComfyUI，面板就会显示图；没抓到的继续显示「无预览」。
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
THUMBS = os.path.join(ROOT, "thumbs")
CUSTOM = os.path.join(ROOT, "custom_thumbs")

API = "https://safebooru.donmai.us/posts.json"

try:
    from PIL import Image
except ImportError:
    print("需要 Pillow。用 ComfyUI 自带环境跑就行，例如：", file=sys.stderr)
    print('  "E:/Game/ComfyUI-Installs/Anima模型/standalone-env/python.exe" tools/fetch_thumbs.py', file=sys.stderr)
    print("或者 pip install pillow", file=sys.stderr)
    sys.exit(1)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def all_characters():
    base = load_json(os.path.join(DATA, "characters.json"), {"characters": []})
    chars = list(base.get("characters") or [])
    chars += load_json(os.path.join(DATA, "characters_extra.json"), [])
    return chars


def tag_to_query(tag):
    """`mavuika_(genshin_impact)` -> `mavuika_(genshin_impact) rating:general`"""
    return f"{tag} rating:general"


def build_opener(proxy):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def fetch_post(opener, tag):
    q = urllib.parse.urlencode({"tags": tag_to_query(tag), "limit": 1,
                                "only": "file_url"})
    req = urllib.request.Request(f"{API}?{q}",
                                 headers={"User-Agent": "anima-character-picker/1.0"})
    with opener.open(req, timeout=25) as r:
        posts = json.loads(r.read().decode("utf-8"))
    if not posts:
        return None
    p = posts[0]
    return p.get("file_url") or p.get("large_file_url") or p.get("preview_file_url")


def download(opener, url):
    req = urllib.request.Request(url, headers={"User-Agent": "anima-character-picker/1.0"})
    with opener.open(req, timeout=40) as r:
        return r.read()


def to_webp(raw, out_path, size=320):
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((size, size), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "WEBP", quality=86, method=4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全部重抓（默认只补缺图）")
    ap.add_argument("--only", default="", help="只抓某个来源：mihoyo / wardrobe / custom")
    ap.add_argument("--proxy", default=os.environ.get("THUMB_PROXY", ""),
                    help="HTTP 代理，如 http://127.0.0.1:7890")
    ap.add_argument("--limit", type=int, default=0, help="最多抓几个（试跑用）")
    ap.add_argument("--sleep", type=float, default=1.2, help="每次请求间隔秒数，别把人家站打崩")
    args = ap.parse_args()

    os.makedirs(THUMBS, exist_ok=True)
    chars = all_characters()
    if args.only:
        chars = [c for c in chars if (c.get("src") or "wardrobe") == args.only]

    todo = []
    for c in chars:
        tag = c["tag"]
        safe = "".join(ch for ch in tag.lower() if ch.isalnum() or ch in "_-")
        target = os.path.join(THUMBS, safe + ".webp")
        if not args.all and os.path.exists(target) and os.path.getsize(target) > 0:
            continue
        todo.append((tag, target))
    if args.limit:
        todo = todo[:args.limit]

    total = len(todo)
    if not total:
        print("没有要抓的（都已有图）；要全部重抓加 --all")
        return 0
    print(f"待抓 {total} 个" + (f"，代理 {args.proxy}" if args.proxy else "，直连"))

    opener = build_opener(args.proxy)
    okc = fail = 0
    t0 = time.time()
    for i, (tag, target) in enumerate(todo, 1):
        try:
            url = fetch_post(opener, tag)
            if not url:
                raise RuntimeError("safebooru 没有这张 tag 的 SFW 图")
            raw = download(opener, url)
            to_webp(raw, target)
            okc += 1
            print(f"[{i}/{total}] ✓ {tag}")
        except Exception as exc:
            fail += 1
            print(f"[{i}/{total}] ✗ {tag} —— {exc}")
        if i < total:
            time.sleep(args.sleep)

    print(f"\n完成：成功 {okc} / 失败 {fail}，用时 {time.time() - t0:.0f}s")
    print("重启 ComfyUI 后生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
