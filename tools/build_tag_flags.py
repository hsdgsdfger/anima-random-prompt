# -*- coding: utf-8 -*-
"""由 data/scenes.json 预生成 data/tag_flags.json（REQ-114）。

索引结构：{ "tag": ["indoor", "night", ...] }
只保留六个契约标记：indoor / outdoor / water / cold / night / monster。
同一个 tag 出现在多个场景包时取并集（保留多来源标记，宁多不少）。

用法：python tools/build_tag_flags.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

FLAGS = ("indoor", "outdoor", "water", "cold", "night", "monster")

# 每个 bundle 里算作「场景绑定词」的槽位
SLOT_KEYS = ("env", "cloth", "shoes", "acc", "props", "poses", "time", "season", "weather")


def build():
    with open(os.path.join(DATA, "scenes.json"), encoding="utf-8") as f:
        sc = json.load(f)

    monster_ids = set(sc.get("monster_bundles") or [])
    idx = {}

    def push(tag, flag):
        tag = str(tag).strip()
        if not tag:
            return
        idx.setdefault(tag, set()).add(flag)

    for b in sc.get("bundles", []):
        flags = set()
        if b.get("indoor"):
            flags.add("indoor")
        else:
            flags.add("outdoor")
        if b.get("water"):
            flags.add("water")
        if b.get("cold"):
            flags.add("cold")
        if "night" in (b.get("time") or []):
            flags.add("night")
        if b["id"] in monster_ids:
            flags.add("monster")
        for key in SLOT_KEYS:
            for tag in b.get(key) or []:
                for flag in flags:
                    push(tag, flag)

    for tag in sc.get("monster_tags") or []:
        push(tag, "monster")

    return {k: [f for f in FLAGS if f in v] for k, v in sorted(idx.items())}


def main():
    out = build()
    path = os.path.join(DATA, "tag_flags.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"已写入 {path}：{len(out)} 个标签")


if __name__ == "__main__":
    main()
