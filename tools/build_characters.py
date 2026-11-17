# -*- coding: utf-8 -*-
"""从 Comfyui-Anima-Wardrobe-V6 的角色库生成本插件自己的 data/characters.json。

一次性脚本：跑完就不再依赖 V6。之后要同步 V6 的新角色，重跑即可。

角色原记录只有 `tags`（一锅乱炖：主语 + 发色 + 发型 + 瞳色 + 服装），
本脚本按规则把它拆成 appearance 的四个桶 + outfit，节点才能精确控制
「只出身份」「只出外观」「带服装」。

用法：
    python tools/build_data.py --v6 "E:/.../Comfyui-Anima-Wardrobe-V6"
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
THUMBS = os.path.join(ROOT, "thumbs")

# 颜色词（判发色用）
COLORS = r"(black|brown|blonde|blond|white|silver|grey|gray|red|pink|blue|purple|green|" \
         r"orange|golden|auburn|turquoise|aqua|mint|lavender|violet|indigo|cyan|magenta|" \
         r"multicolored|two-tone|gradient|platinum|ash|sakura|peach|cream|navy|teal)"
COLOR_RE = re.compile(r"\b" + COLORS + r"\b", re.I)
EYES_RE = re.compile(r"\beyes?\b", re.I)
HAIR_RE = re.compile(r"\bhair\b", re.I)
BODY_RE = re.compile(r"\b(breasts?|chest|hips?|thighs?|legs?|waist|muscular|slim|chubby|"
                     r"plump|curvy|petite|tall|short stature)\b", re.I)
FACE_RE = re.compile(r"\b(freckles|mole|blush|eyelashes|eyebrows|eyebags|fang|scar|"
                     r"makeup|lipstick|tsurime|tareme|sharp eyes|eyepatch|monocle)\b", re.I)
SUBJECT_RE = re.compile(r"^(1girl|1boy|2girls|2boys|solo|multiple girls|mature female|"
                        r"female|girl)$", re.I)
# 明显属于「穿在身上」的词 —— 只用作兜底拆分参考，不代表完整服装体系
CLOTH_HINT = re.compile(
    r"\b(shirt|dress|skirt|uniform|jacket|coat|hoodie|sweater|cardigan|vest|suit|"
    r"kimono|yukata|robe|cloak|cape|apron|bikini|swimsuit|leotard|bodysuit|"
    r"pants|shorts|jeans|stockings|thighhighs|socks|boots|shoes|sandals|heels|"
    r"sleeves|gloves|hat|cap|headband|hairband|ribbon|bow|scarf|muffler|necktie|"
    r"necklace|earrings|bracelet|belt|garter|lingerie|underwear|bra|panties|"
    r"camisole|tank top|crop top|hood|veil|armor|gauntlet|greaves)\b", re.I)


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def load(v6, name):
    p = os.path.join(v6, "presets", name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def split_tags(tags):
    """把角色的官配 tags 拆成四个外观桶 + 服装桶。

    分不清类别的标签**直接丢弃**而不是塞进 extras —— 角色库里的脏标签
    混进外观段会污染输出（实测有 `crystal` / `one side up` 这类残渣）。
    extras 只认 char_feat.json 里人工核定的那几张表。
    """
    ap = {"hair_color": [], "hair_style": [], "eyes": [], "face": [], "body": []}
    outfit, subject, dropped = [], [], []
    for raw in tags or []:
        t = norm(raw)
        if not t:
            continue
        if SUBJECT_RE.match(t):
            subject.append(t)
            continue
        if EYES_RE.search(t):
            ap["eyes"].append(t)
        elif HAIR_RE.search(t):
            # `aqua hair` 归发色，`twintails` / `very long hair` 归发型
            (ap["hair_color"] if COLOR_RE.search(t) else ap["hair_style"]).append(t)
        elif BODY_RE.search(t):
            ap["body"].append(t)
        elif FACE_RE.search(t):
            ap["face"].append(t)
        elif CLOTH_HINT.search(t):
            outfit.append(t)
        else:
            dropped.append(t)
    for k in list(ap):
        ap[k] = list(dict.fromkeys(ap[k]))
    return ap, list(dict.fromkeys(outfit)), list(dict.fromkeys(subject)), dropped


def build(v6):
    chars_raw = load(v6, "anima_v4_characters.json")
    out_tags = load(v6, "char_output_tags.json").get("tags") or {}
    feats = load(v6, "char_feat.json").get("feats") or {}
    hair_styles = load(v6, "char_hair_style.json").get("styles") or {}
    outfits_raw = load(v6, "character_outfits.json").get("outfits") or {}

    works_raw = chars_raw.get("works") or []
    chars = chars_raw.get("characters") or {}

    # 作品表：兼容 list / dict 两种形态
    works, work_index = [], {}
    if isinstance(works_raw, dict):
        works_raw = [{"id": k, **v} for k, v in works_raw.items()]
    for w in works_raw:
        wid = norm(w.get("id") or w.get("slug") or w.get("name"))
        if not wid:
            continue
        rec = {"id": wid,
               "name": w.get("name") or wid,
               "zh": w.get("zh") or ""}
        works.append(rec)
        work_index[wid] = rec

    items = []
    if isinstance(chars, dict):
        chars = [dict(v, tag=k) if isinstance(v, dict) else {"tag": k} for k, v in chars.items()]

    for c in chars:
        tag = norm(c.get("tag"))
        if not tag:
            continue
        trigger = str(c.get("trigger") or "").strip()
        if not trigger:
            name = str(c.get("name") or tag).replace("_", " ")
            trigger = f"{name}, {c.get('work')}" if c.get("work") else name

        ap, outfit, subject, dropped = split_tags(c.get("tags") or [])

        # 发色 / 瞳色字段兜底（V6 的 hair / eyes 列）
        hair = norm(c.get("hair"))
        eyes = norm(c.get("eyes"))
        if hair:
            ht = hair if hair.endswith("hair") else f"{hair} hair"
            if not ap["hair_color"]:
                ap["hair_color"].append(ht)
        if eyes:
            et = eyes if eyes.endswith("eyes") else f"{eyes} eyes"
            if not ap["eyes"]:
                ap["eyes"].append(et)

        # 官方发型（char_hair_style）
        hs = hair_styles.get(tag) or {}
        for k in ("hair_len", "hair_tie", "hair_curl"):
            v = norm(hs.get(k))
            if v and v != "none" and v not in ap["hair_style"]:
                ap["hair_style"].append(v)

        # 固定特征（char_feat 的 extras）—— 人工核定的才留，且不能与外观桶重复
        feat = feats.get(tag) or {}
        already = {x for k, v in ap.items() for x in v}
        extras = [norm(x) for x in (feat.get("extras") or [])
                  if norm(x) and norm(x) not in already]
        if extras:
            ap["extras"] = list(dict.fromkeys(extras))

        # 服装预设（character_outfits）
        of = outfits_raw.get(tag) or {}
        outfits = []
        for o in of.get("list") or []:
            tgs = [norm(x) for x in (o.get("tags") or []) if norm(x)]
            if not tgs:
                continue
            outfits.append({
                "id": str(o.get("id") or "default"),
                "zh": str(o.get("zh") or ""),
                "level": int(o.get("level") or 0),
                "tags": tgs,
            })
        if not outfits and outfit:
            outfits = [{"id": "default", "zh": "官方外观里的服装", "level": 0, "tags": outfit}]

        # 输出用词（char_output_tags 核验过的 trigger）
        ot = out_tags.get(trigger.lower()) or {}
        out_trigger = ot.get("out") or trigger

        rec = {
            "tag": tag,
            "name": norm(c.get("name")) or tag.replace("_", " "),
            "zh": str(c.get("zh") or ""),
            "work": norm(c.get("work")),
            "trigger": str(out_trigger),
            "pop": int(c.get("pop") or 0),
            "src": norm(c.get("src")) or "wardrobe",
            "thumb": str(c.get("thumb") or ""),
            "subject": subject,
            "appearance": {k: v for k, v in ap.items() if v},
            "outfits": outfits,
        }
        items.append(rec)

    items.sort(key=lambda x: (-x["pop"], x["tag"]))

    # 作品计数
    cnt = {}
    for it in items:
        cnt[it["work"]] = cnt.get(it["work"], 0) + 1
    works = [w for w in works if cnt.get(w["id"])]
    known = {w["id"] for w in works}
    for wid, n in cnt.items():
        if wid and wid not in known:
            works.append({"id": wid, "name": wid, "zh": ""})
    for w in works:
        w["count"] = cnt.get(w["id"], 0)
    works.sort(key=lambda w: (-w["count"], w["id"]))

    return {
        "_meta": {
            "schema": "anima-character-picker/characters@1",
            "source": "Comfyui-Anima-Wardrobe-V6 presets",
            "characters": len(items),
            "works": len(works),
            "note": "由 tools/build_data.py 生成；改了角色库请重跑",
        },
        "works": works,
        "characters": items,
    }


def copy_thumbs(v6, only=None):
    src = os.path.join(v6, "presets", "thumbs")
    if not os.path.isdir(src):
        print("! 找不到 thumbs 目录，跳过缩略图", file=sys.stderr)
        return 0
    os.makedirs(THUMBS, exist_ok=True)
    n = 0
    for fn in os.listdir(src):
        if not fn.lower().endswith(".webp"):
            continue
        if only is not None and os.path.splitext(fn)[0] not in only:
            continue
        shutil.copy2(os.path.join(src, fn), os.path.join(THUMBS, fn))
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v6", default=os.environ.get("ANIMA_V6_DIR", ""),
                    help="Comfyui-Anima-Wardrobe-V6 目录")
    args = ap.parse_args()
    v6 = args.v6
    if not v6 or not os.path.isdir(v6):
        print("需要 --v6 指向 Comfyui-Anima-Wardrobe-V6 目录", file=sys.stderr)
        return 1

    data = build(v6)
    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, "characters.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    thumbs = {c["thumb"] for c in data["characters"] if c["thumb"]}
    n = copy_thumbs(v6, thumbs)

    size = os.path.getsize(out) / 1024
    print(f"角色 {len(data['characters'])} / 作品 {len(data['works'])}")
    print(f"数据 → {out}（{size:.0f} KB）")
    print(f"缩略图 → {THUMBS}（{n} 张）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
