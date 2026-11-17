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
# animadex 的 JSON 接口：角色库 3.6 万条，返回 slug/trigger/tags/thumb_url
ADEX_API = "https://animadex.net/api/characters/search"
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


def adex_lookup(tag):
    """返回 animadex 上的匹配条数（slug 完全一致算命中）。-1 表示请求失败。"""
    q = urllib.parse.urlencode({"q": tag, "limit": 8})
    try:
        raw = _get(f"{ADEX_API}?{q}")
        data = json.loads(raw)
    except Exception:
        return -1
    for r in data.get("results") or []:
        if r.get("slug") == tag:
            return int(r.get("count") or 0) or 1
    return 0


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
    ap.add_argument("--source", default="safebooru", choices=("safebooru", "animadex"),
                    help="safebooru 快但限速狠；animadex 更准但 1 秒/次")
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
        # ⚠️ 必须用 c["tag"]（规范 tag，形如 `ganyu_(genshin_impact)`）去查，
        #    不能用 trigger 的第一段 —— trigger 是给人看的简写（`ganyu`），
        #    站点 tag 表里没有它，会全部返回 0（第一版就栽在这，529 个假阴性）。
        time.sleep(args.sleep)
        if args.source == "animadex":
            return c, c["tag"], adex_lookup(c["tag"])
        return c, c["tag"], tag_count(c["tag"])

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
