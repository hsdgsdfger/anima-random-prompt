# -*- coding: utf-8 -*-
"""按档位清洗模板库（v0.2.1）。

模板库是预生成的成品提示词，节点里「模板覆盖」模式会直接把它原样输出，
**完全不经过抽取引擎**。所以引擎再严，只要模板里写着 bikini，sfw 档照样出泳装
（用户 2026-11-17 报的那张比基尼就是 sfw-normal-* 里的）。

这个脚本做三件事，幂等：
  1. 按每条模板自己的 level 算出档位上限；
  2. 把超出上限的「形象 / 成人内容」词删掉；
  3. sfw 模板如果没有上衣，就补一件基础上衣（没有下装再补一条裙子）。

判定口径（很重要，第一版在这上面翻过车）：
  · 词出现在 clothing / body / pose / accessory / extra / hair / face 这些
    「形象类」分类里 → 用该分类的档位判；
  · 词只出现在 nsfwbody / nsfwcloth / nsfwact 里 → 只有命中裸露/成人词表
    才判档，位置词（on bed / on floor / against wall / lotus position）
    一律保留 —— nsfwact 里有同名条目 lv3，直接查全局档位会把整批
    sfw 模板的「躺在床上」删干净；
  · 查不到的词（环境、光影、画风）不动。
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import engine  # noqa: E402

CAP = {"sfw": 0, "suggestive": 1, "explicit": 2, "hardcore": 3, "extreme": 4, "any": 99}
RATING = {"safe", "sensitive", "nsfw", "explicit"}
SHAPE_CATS = {"clothing", "body", "pose", "accessory", "extra", "hair", "face", "expression"}

# 真正属于成人内容的词（只出现在 nsfw 分类里，位置词不在这个集合里）
ADULT = re.compile(
    r"\b(nude|naked|topless|nipples?|areolas?|pussy|penis|vagina|genitals?|"
    r"sex|sexual|penetration|masturbat\w*|cum\w*|ejaculat\w*|fellatio|blowjob|"
    r"oral|anal|creampie|orgasm|clitoris|testicles|semen|bondage|shibari|bdsm|"
    r"gag|leash|tentacles?|panties|bra|underwear|bikini|swimsuit|lingerie)\b", re.I)

_MAP = None


def build_map(path):
    global _MAP
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    m = {}
    for c in raw["cats"]:
        for t in c["tags"]:
            m.setdefault(t["en"].lower(), {})[c["id"]] = int(t["lv"])
    _MAP = m


def tag_ok(seg, cap):
    low = seg.lower()
    if low in RATING:
        return True
    info = _MAP.get(low)
    if not info:
        return True                       # 词库外（画风 / 环境 / 具体地点）不动
    shape = [lv for cid, lv in info.items() if cid in SHAPE_CATS]
    if shape:
        if min(shape) > cap:
            return False
    elif ADULT.search(seg):
        if min(info.values()) > cap:
            return False
    else:
        return True                       # 位置 / 动作词：保留
    if cap <= 0 and engine._NSFW_CLOTH.search(seg) and not engine._HOSIERY.search(seg):
        return False                      # sfw：泳装 / 内衣 / 透明一律不要
    return True


def clean(text, cap, rng):
    segs = [s.strip() for s in str(text).split(",") if s.strip()]
    kept = [s for s in segs if tag_ok(s, cap)]
    dropped = len(segs) - len(kept)
    filled = 0
    if cap <= 0:
        cloth = [s for s in kept if engine._GARMENT.search(s)]
        new_cloth, _, add = engine._dress_names(cloth, rng)
        if add:
            extra = [s for s in new_cloth if s not in cloth]
            pos = next((i for i, s in enumerate(kept) if s.lower() in RATING), len(kept))
            for k, s in enumerate(extra):
                kept.insert(pos + k, s)
            filled = len(extra)
    return ", ".join(kept), dropped, filled


def run(path, dry=False):
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    rng = random.Random(0)
    stat = {}
    changed = []
    for t in items:
        lv = str(t.get("level") or "sfw")
        cap = CAP.get(lv, 0)
        d1 = f1 = 0
        for field in ("prompt", "no_subject"):
            if not t.get(field):
                continue
            new, d, f = clean(t[field], cap, rng)
            if new != t[field]:
                t[field] = new
            d1 += d
            f1 += f
        if d1 or f1:
            stat[lv] = stat.get(lv, 0) + 1
            changed.append((t.get("id"), lv, d1, f1))
    if not dry:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{os.path.basename(path)}: 改动 {len(changed)} 条 / 共 {len(items)} 条 · 分布 {stat}")
    for cid, lv, d, f in changed[:8]:
        print(f"   {cid:30s} {lv:11s} 删 {d:3d} 补 {f}")
    if len(changed) > 8:
        print(f"   ... 另有 {len(changed) - 8} 条")


if __name__ == "__main__":
    build_map(os.path.join(HERE, "data", "tags.json"))
    for name in ("templates_ui.json", "templates_v6.json"):
        p = os.path.join(HERE, "data", name)
        if os.path.exists(p):
            run(p)
