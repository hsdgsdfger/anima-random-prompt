# -*- coding: utf-8 -*-
"""校验角色 trigger 里的 tag 在 booru 站上是否真的存在。

danbooru.donmai.us 在本机连不上（Cloudflare / 链路），
改用 safebooru.org 的 dapi 查「这个 tag 有多少帖子」：
  count > 0 → tag 存在
  count = 0 → 要么拼错了，要么太冷门没人传

用法：
    python tools/verify_triggers.py --only mihoyo      # 只查补充角色（39 个，快）
    python tools/verify_triggers.py --all --workers 6  # 全量 2471 个（慢，约 40 分钟）
    python tools/verify_triggers.py --limit 20
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

API = "https://safebooru.org/index.php?page=dapi&s=post&q=index"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def all_characters():
    base = load(os.path.join(DATA, "characters.json"), {"characters": []})
    chars = list(base.get("characters") or [])
    chars += load(os.path.join(DATA, "characters_extra.json"), [])
    return chars


def _get(url, timeout=12, retry=3):
    last = None
    for i in range(retry):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": UA}),
                timeout=timeout).read().decode("utf-8", "ignore")
        except Exception as exc:
            last = exc
            time.sleep(1.0 * (i + 1))
    raise last


def tag_count(tag, opener=None):
    """safebooru.org 上这个 tag 的帖子数。-1 表示查询失败。"""
    q = urllib.parse.urlencode({"tags": tag, "limit": 1})
    try:
        xml = _get(f"{API}&{q}")
    except Exception:
        return -1
    m = re.search(r'count="(\d+)"', xml)
    return int(m.group(1)) if m else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="mihoyo / wardrobe")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    chars = all_characters()
    if args.only:
        chars = [c for c in chars if (c.get("src") or "wardrobe") == args.only]
    elif not args.all:
        chars = [c for c in chars if (c.get("src") or "wardrobe") != "wardrobe"]
    if args.limit:
        chars = chars[:args.limit]

    print(f"待校验 {len(chars)} 个角色（每查一个 tag 一次请求）")
    rows = []

    def one(c):
        # trigger 第一段是角色（空格写法），查站上要换成下划线写法
        parts = [p.strip() for p in str(c.get("trigger") or "").split(",") if p.strip()]
        role_tag = parts[0] if parts else c["tag"]
        query = role_tag.replace(" ", "_")
        time.sleep(args.sleep)
        return c, role_tag, tag_count(query)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, min(8, args.workers))) as pool:
        futs = [pool.submit(one, c) for c in chars]
        for i, f in enumerate(as_completed(futs), 1):
            c, tag, n = f.result()
            rows.append((c, tag, n))
            if i % 20 == 0 or i == len(chars):
                print(f"  {i}/{len(chars)}", flush=True)

    missing = [(c, t, n) for c, t, n in rows if n == 0]
    failed = [(c, t, n) for c, t, n in rows if n < 0]
    print(f"\n用时 {time.time() - t0:.0f}s")
    print(f"存在 {len(rows) - len(missing) - len(failed)} · 查不到 {len(missing)} · 请求失败 {len(failed)}")

    if missing:
        print("\n【查不到 = 拼错 或 冷门没人传】")
        for c, t, n in sorted(missing, key=lambda x: x[0]["tag"]):
            print(f"  {c['tag']:34s} trigger={t:38s} {c.get('zh') or ''}")
    if failed:
        print("\n【请求失败，可重跑】")
        for c, t, n in failed[:20]:
            print(f"  {c['tag']}")

    out = os.path.join(DATA, "_trigger_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{"tag": c["tag"], "zh": c.get("zh"), "trigger_tag": t, "count": n}
                   for c, t, n in rows], f, ensure_ascii=False, indent=1)
    print(f"\n明细已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
