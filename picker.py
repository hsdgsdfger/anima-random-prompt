# -*- coding: utf-8 -*-
"""角色选择引擎：从一个 2432 条的本地角色库里挑人，并把记录拆成三段提示词。

三段的分工（用户 2026-11-17 口径「角色外观一定要跟着提示词走」）：
  · character  —— 身份：`hatsune miku, vocaloid`
  · appearance —— 官方外观：发色 / 发型 / 瞳色 / 面部 / 身材 / 固定特征
  · outfit     —— 服装：从角色的服装预设里按档位挑一套

节点把三段拼成 `positive` 交给下游，也可以只接其中一段。
"""
import json
import math
import os
import random
import re

from . import char_state as S

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "characters.json")

OUTFIT_LEVELS = ["全年龄", "擦边", "成人"]
_LEVEL_NUM = {"全年龄": 0, "擦边": 1, "成人": 2}
_MODE_KEYS = {"随机": "random", "指定": "fixed", "收藏随机": "fav", "多选加权": "picked"}

# pop 的压缩指数：原值差 3 个数量级，直接加权热门会垄断，
# 0.35 次幂让「高人气稍微更容易」而不是「只有那几个」
POP_EXP = 0.35

_CACHE = {}


def _load_raw():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def library():
    """内置库 + 自定义角色（同 tag 覆盖），带缓存。"""
    if "lib" not in _CACHE:
        raw = _load_raw()
        chars = list(raw.get("characters") or [])
        works = list(raw.get("works") or [])
        by_tag = {c["tag"]: c for c in chars}
        for c in S.load_custom():
            if c["tag"] in by_tag:
                by_tag[c["tag"]].update(c)
            else:
                chars.append(c)
                by_tag[c["tag"]] = c
        _CACHE["lib"] = {"works": works, "characters": chars, "by_tag": by_tag}
    return _CACHE["lib"]


def invalidate():
    _CACHE.pop("lib", None)


def works_payload():
    lib = library()
    cnt = {}
    for c in lib["characters"]:
        cnt[c.get("work") or ""] = cnt.get(c.get("work") or "", 0) + 1
    out = []
    for w in lib["works"]:
        n = cnt.get(w["id"], 0)
        if n:
            out.append({"id": w["id"], "name": w.get("name") or w["id"],
                        "zh": w.get("zh") or "", "count": n})
    return out


# ---------------------------------------------------------------- 选择

def _weight_of(rec, weights):
    w = (float(rec.get("pop") or 0) + 1.0) ** POP_EXP
    w *= max(0.0, float(weights.get(rec["tag"], 1.0) or 0.0))
    return w


def _pick_weighted(pool, weights, rng):
    if not pool:
        return None
    ws = [_weight_of(c, weights) for c in pool]
    total = sum(ws)
    if total <= 0:
        return rng.choice(pool)
    r = rng.random() * total
    acc = 0.0
    for c, w in zip(pool, ws):
        acc += w
        if r < acc:
            return c
    return pool[-1]


def _find_by_name(lib, q):
    q = str(q or "").strip().lower()
    if not q:
        return None
    by_tag = lib["by_tag"]
    if q in by_tag:
        return by_tag[q]
    for c in lib["characters"]:
        if q == (c.get("name") or "").lower() or q == (c.get("zh") or ""):
            return c
    hits = [c for c in lib["characters"]
            if q in (c.get("tag") or "") or q in (c.get("name") or "").lower()
            or q in (c.get("zh") or "")]
    if not hits:
        return None
    hits.sort(key=lambda c: 0 if q in (c.get("zh") or "") else 1)
    return hits[0]


def select(mode="random", seed=-1, role_name="", work_filter="",
           st=None, rng=None):
    """返回 (角色记录, 说明文字)。挑不到时返回 (None, 原因)。"""
    lib = library()
    st = st or S.load_state()
    rng = rng or (random.Random(seed) if int(seed) >= 0 else random.Random())

    excluded = set(st.get("excluded") or [])
    weights = st.get("weights") or {}
    mode_key = _MODE_KEYS.get(mode, mode)

    if mode_key == "fixed":
        rec = _find_by_name(lib, role_name)
        if not rec:
            return None, f"没找到角色「{role_name}」"
        return rec, "指定"

    pool = [c for c in lib["characters"] if c["tag"] not in excluded]

    if mode_key == "fav":
        fav = [t for t in (st.get("favorites") or []) if t not in excluded]
        pool = [c for c in pool if c["tag"] in set(fav)]
        if not pool:
            return None, "收藏夹是空的（或收藏的角色都被排除了）"
        return _pick_weighted(pool, weights, rng), "收藏随机"

    if mode_key == "picked":
        picked = [t for t in (st.get("picked") or []) if t not in excluded]
        pool = [c for c in pool if c["tag"] in set(picked)]
        if not pool:
            return None, "面板里还没有勾选角色"
        return _pick_weighted(pool, weights, rng), "多选加权"

    # 随机：可按作品限定
    words = [w.strip().lower() for w in re.split(r"[|,，]", work_filter or "") if w.strip()]
    if words:
        by_id = {w["id"]: w for w in works_payload()}
        ids = set()
        for w in words:
            for wid, info in by_id.items():
                if w in wid or w in (info.get("name") or "").lower() or w in (info.get("zh") or ""):
                    ids.add(wid)
        if not ids:
            return None, f"作品「{work_filter}」一个角色都没有"
        pool = [c for c in pool if (c.get("work") or "") in ids]
        if not pool:
            return None, "该作品下的角色都被排除了"
        return _pick_weighted(pool, weights, rng), "按作品随机"

    if not pool:
        return None, "角色库是空的"
    return _pick_weighted(pool, weights, rng), "全库随机"


# ---------------------------------------------------------------- 拼装

def _uniq(seq):
    out, seen = [], set()
    for x in seq:
        x = str(x or "").strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def appearance_tags(rec):
    """外观段：发色 → 发型 → 瞳色 → 面部 → 身材 → 固定特征。"""
    ap = rec.get("appearance") or {}
    order = ("hair_color", "hair_style", "eyes", "face", "body", "extras")
    out = []
    for k in order:
        out.extend(ap.get(k) or [])
    return _uniq(out)


def outfit_tags(rec, level_key="全年龄", outfit_id=""):
    """服装段：按档位上限挑一套；同一角色有多套时优先选中的那套。"""
    cap = _LEVEL_NUM.get(level_key, 0)
    outs = [o for o in (rec.get("outfits") or []) if int(o.get("level") or 0) <= cap]
    if not outs:
        return [], ""
    if outfit_id:
        for o in outs:
            if o.get("id") == outfit_id:
                return _uniq(o.get("tags") or []), o.get("zh") or o.get("id") or ""
    o = outs[0]
    return _uniq(o.get("tags") or []), o.get("zh") or o.get("id") or ""


def compose(rec, include_appearance=True, include_outfit=False,
            outfit_level="全年龄", outfit_id=""):
    """把三段拼成返回结构。"""
    character = _uniq([rec.get("trigger") or rec.get("tag")])
    appear = appearance_tags(rec) if include_appearance else []
    outfit, outfit_name = outfit_tags(rec, outfit_level, outfit_id) if include_outfit else ([], "")

    parts = list(character)
    for t in appear:
        if t.lower() not in {p.lower() for p in parts}:
            parts.append(t)
    for t in outfit:
        if t.lower() not in {p.lower() for p in parts}:
            parts.append(t)

    return {
        "character": ", ".join(character),
        "appearance": ", ".join(appear),
        "outfit": ", ".join(outfit),
        "positive": ", ".join(parts),
        "outfit_name": outfit_name,
        "counts": {"character": len(character), "appearance": len(appear),
                   "outfit": len(outfit)},
    }
