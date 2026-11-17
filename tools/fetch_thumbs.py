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
import json
import os
import sys
import time
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
THUMBS = os.path.join(ROOT, "thumbs")
CUSTOM = os.path.join(ROOT, "custom_thumbs")

# animadex.net 的 JSON 接口：一次请求就能拿到角色记录，里面直接带 thumb_url。
# 比 safebooru 快一个数量级（0.7s vs 60s），而且是 webp，不用转格式。
ADEX_API = "https://animadex.net/api/characters/search"
# 备用：safebooru.org 的 dapi（.us 那个域名有 Cloudflare 403）
API = "https://safebooru.org/index.php?page=dapi&s=post&q=index"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 这里**故意不依赖 Pillow**：抓图用系统 Python 跑（能连外网），
# 但 ComfyUI 自带的 Python 连 TLS 握手都会超时，装不了也跑不通。
# 所以直接下载 safebooru 的 preview 缩略图（约 150px）存成 .jpg，
# 后端路由先找 .webp 再找 .jpg，两种格式都能出图。


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
    """safebooru.org 本身就是 SFW 站，不需要 rating 参数。"""
    return str(tag).strip()


def build_opener(proxy):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def _get(opener, url, timeout=12, retry=3, referer=None):
    """带重试的 GET。这个站的 TLS 握手会间歇性超时，单发一次成功率只有一半。"""
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    last = None
    for i in range(retry):
        try:
            return opener.open(urllib.request.Request(url, headers=h), timeout=timeout).read()
        except Exception as exc:
            last = exc
            time.sleep(1.0 * (i + 1))
    raise last


def fetch_animadex(opener, tag):
    """animadex：搜角色 → 找 slug 完全匹配的那条 → 返回 (thumb_url, None)。"""
    q = urllib.parse.urlencode({"q": tag, "limit": 8})
    raw = _get(opener, f"{ADEX_API}?{q}", timeout=20)
    data = json.loads(raw.decode("utf-8", "ignore"))
    results = data.get("results") or []
    exact = [r for r in results if r.get("slug") == tag]
    hit = exact[0] if exact else (results[0] if results else None)
    if not hit:
        return None, None
    url = hit.get("thumb_url") or hit.get("img_url")
    if not url:
        return None, None
    return url, hit.get("count")


def fetch_post(opener, tag):
    """返回 (图片 url, 原图宽高)；没有结果返回 (None, None)。"""
    q = urllib.parse.urlencode({"tags": tag_to_query(tag), "limit": 3})
    xml = _get(opener, f"{API}&{q}").decode("utf-8", "ignore")
    posts = re.findall(r"<post\s+([^>]+?)/?>", xml)
    for raw in posts:
        a = dict(re.findall(r'(\w+)="([^"]*)"', raw))
        # 优先 preview（小、快）；sample 太大，150px 卡片够用
        url = a.get("preview_url") or a.get("sample_url") or a.get("file_url")
        if url:
            try:
                w, h = int(a.get("width") or 0), int(a.get("height") or 0)
            except ValueError:
                w = h = 0
            return url, (w, h)
    return None, None


def download(opener, url):
    return _get(opener, url, timeout=20, referer="https://safebooru.org/")


def save_img(raw, out_path):
    """按文件头判断格式，webp / jpeg 都收。"""
    ok = raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" or raw[:3] == b"\xff\xd8\xff"
    if not ok:
        raise RuntimeError("返回的不是图片")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ext = ".webp" if raw[:4] == b"RIFF" else ".jpg"
    if not out_path.endswith(ext):
        out_path = os.path.splitext(out_path)[0] + ext
    with open(out_path, "wb") as f:
        f.write(raw)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全部重抓（默认只补缺图）")
    ap.add_argument("--only", default="", help="只抓某个来源：mihoyo / wardrobe / custom")
    ap.add_argument("--proxy", default=os.environ.get("THUMB_PROXY", ""),
                    help="HTTP 代理，如 http://127.0.0.1:7890")
    ap.add_argument("--limit", type=int, default=0, help="最多抓几个（试跑用）")
    ap.add_argument("--sleep", type=float, default=0.5, help="每个线程内的请求间隔秒数")
    ap.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    ap.add_argument("--source", default="animadex", choices=("animadex", "safebooru"),
                    help="图源，默认 animadex（快且直接给 webp）")
    args = ap.parse_args()

    os.makedirs(THUMBS, exist_ok=True)
    chars = all_characters()
    if args.only:
        chars = [c for c in chars if (c.get("src") or "wardrobe") == args.only]

    todo = []
    for c in chars:
        tag = c["tag"]
        safe = "".join(ch for ch in tag.lower() if ch.isalnum() or ch in "_-")
        target = os.path.join(THUMBS, safe + (".webp" if args.source == "animadex" else ".jpg"))
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
    t0 = time.time()
    okc = 0
    failed = []
    lock_state = {"done": 0}

    use_adex = args.source == "animadex"

    def one(item):
        tag, target = item
        try:
            if use_adex:
                url, _cnt = fetch_animadex(opener, tag)
                if not url:
                    raise RuntimeError("animadex 没有这个角色")
            else:
                url, _size = fetch_post(opener, tag)
                if not url:
                    raise RuntimeError("safebooru 没有这张 tag 的图")
            raw = _get(opener, url, timeout=25) if use_adex else download(opener, url)
            save_img(raw, target)
            return tag, None
        except Exception as exc:
            return tag, str(exc)[:80]
        finally:
            time.sleep(args.sleep)

    workers = max(1, min(8, args.workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, it) for it in todo]
        for f in as_completed(futs):
            tag, err = f.result()
            lock_state["done"] += 1
            i = lock_state["done"]
            if err is None:
                okc += 1
                print(f"[{i}/{total}] ✓ {tag}", flush=True)
            else:
                failed.append((tag, err))
                print(f"[{i}/{total}] ✗ {tag} —— {err}", flush=True)

    print(f"\n完成：成功 {okc} / 失败 {len(failed)}，用时 {time.time() - t0:.0f}s")
    if failed:
        print("失败清单（可再跑一次补）：")
        for tag, err in failed:
            print(f"  {tag}  —— {err}")
    print("重启 ComfyUI 后生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
