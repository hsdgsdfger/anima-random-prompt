# -*- coding: utf-8 -*-
"""把 Comfyui-Anima-Wardrobe-V6 的场景搭配库（scenes）转成本插件的模板卡片。

用户口径（2026-11-17 最终）：只要 V6 的 **场景搭配** 和 **姿势库** 两组。
  · 取 `nsfw`（🔞 NSFW 跨槽位配方）+ `pose`（🧎 姿势场景）
  · 不要 `art`（艺术构图）、`weapon`（武器场景）、`near`（特写）、`sfw`（全年龄场景）
  · 不再按档位过滤 —— 档位由节点的 level 参数与设置页矩阵控制，模板页只负责挑内容
  · 仍排除含 `1boy` / `2boys` 的条目（本插件是全女性库，套异性配方会和下游打架），
    `--keep-male` 放开

转换规则：
  · prompt = count_lock（默认 `1girl, solo`）+ tags 各值（按原顺序）+ extra
  · level  = scenes 里的 0–4 数字档位，转成模板页用的档位键
  · bundle = 空（V6 场景不绑本插件那 45 个场景包，所以「室内 / 夜景」这类筛选命中不了）
  · index  = 从 1001 起编号，和原 1800 套的 1–200 页码不冲突

用法：python tools/build_v6_templates.py --v6 "路径/Comfyui-Anima-Wardrobe-V6"
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

LEVEL_BY_NUM = {0: "sfw", 1: "suggestive", 2: "explicit", 3: "hardcore", 4: "extreme"}
KEEP_GROUPS = {"nsfw", "pose"}
GROUP_ZH = {"nsfw": "跨槽位配方", "near": "特写搭配", "pose": "姿势场景",
            "art": "艺术构图", "weapon": "武器场景"}


def clean(s):
    s = str(s or "").strip().strip(",")
    s = re.sub(r"\s+", " ", s)
    return s


def build_prompt(scene):
    parts = []
    lock = clean(scene.get("count_lock")) or "1girl, solo"
    parts.append(lock)
    tags = scene.get("tags") or {}
    if isinstance(tags, dict):
        order = list(tags.keys())
        for k in order:
            v = tags[k]
            if isinstance(v, list):
                for x in v:
                    parts.append(clean(x))
            elif v:
                parts.append(clean(v))
    elif isinstance(tags, list):
        for x in tags:
            parts.append(clean(x))
    extra = clean(scene.get("extra"))
    if extra:
        parts.append(extra)
    out, seen = [], set()
    for p in parts:
        for seg in str(p).split(","):
            seg = clean(seg)
            if seg and seg.lower() not in seen:
                seen.add(seg.lower())
                out.append(seg)
    return ", ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v6", default=os.environ.get("ANIMA_V6_DIR", ""))
    ap.add_argument("--keep-sfw", action="store_true", default=True,
                    help="保留 level=0 的条目（默认就保留，档位交给节点控制）")
    ap.add_argument("--drop-sfw", action="store_true", help="排掉 level=0 的条目")
    ap.add_argument("--keep-male", action="store_true", help="保留含 1boy / 2boys 的条目")
    args = ap.parse_args()
    if not args.v6 or not os.path.isdir(args.v6):
        print("需要 --v6 指向 Comfyui-Anima-Wardrobe-V6 目录", file=sys.stderr)
        return 1

    path = os.path.join(args.v6, "presets", "anima_v4_scenes.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 序号接在自产模板之后，全站唯一（用户在面板里报「第 N 套」才定位得到）
    base = 1800
    try:
        with open(os.path.join(DATA, "templates_ui.json"), encoding="utf-8") as f:
            base = len(json.load(f))
    except Exception:
        pass
    scenes = raw.get("scenes") or []
    items, idx = [], base
    dropped_sfw = dropped_male = dropped_group = 0
    MALE = re.compile(r"\b(1boy|2boys|3boys|male)\b", re.I)
    for sc in scenes:
        group = str(sc.get("group") or "").strip().lower()
        if group not in KEEP_GROUPS:
            dropped_group += 1
            continue
        prompt = build_prompt(sc)
        if not prompt:
            continue
        lv = sc.get("level")
        try:
            lv_num = int(lv)
        except (TypeError, ValueError):
            lv_num = 2
        lv_key = LEVEL_BY_NUM.get(lv_num, "explicit")
        if args.drop_sfw and lv_num <= 0:
            dropped_sfw += 1
            continue   # --keep-sfw 已默认开启（档位交给节点控制）
        if not args.keep_male and MALE.search(prompt):
            dropped_male += 1
            continue
        idx += 1
        items.append({
            "id": f"v6-{group}-{sc.get('id') or idx}",
            "index": idx,
            "level": lv_key,
            "kind": "normal",
            "bundle": "",
            "src": "v6",
            "group": group,
            "group_zh": GROUP_ZH.get(group, group),
            "zh": cleaner_zh(sc),
            "prompt": prompt,
        })

    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, "templates_v6.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=0)

    by_group = {}
    for it in items:
        by_group[it["group"]] = by_group.get(it["group"], 0) + 1
    print(f"已写入 {out}：{len(items)} 套")
    print(f"排除：非目标组 {dropped_group} · sfw 档位 {dropped_sfw} · 含男性词 {dropped_male}")
    print("按组:", by_group)
    print("\n样例：")
    for it in items[:2] + items[-1:]:
        print(f"  #{it['index']} [{it['level']}] {it['zh']}")
        print(f"    {it['prompt'][:160]}")
    return 0


def cleaner_zh(sc):
    zh = clean(sc.get("zh"))
    desc = clean(sc.get("desc"))
    if zh and desc:
        return f"{zh} · {desc}" if len(desc) <= 18 else zh
    return zh or desc or str(sc.get("id") or "")


if __name__ == "__main__":
    sys.exit(main())
