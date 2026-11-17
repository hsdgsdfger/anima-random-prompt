# -*- coding: utf-8 -*-
"""数据校验（REQ-101）：提交前必跑。

校验项：
  1. data/tags.json：分类数 / 词条数 / 每条都有 en、lv 合法
  2. data/scenes.json：场景包数量、每个包六个互斥标记齐全
  3. data/templates_ui.json：模板数、每套都有合法 bundle 且 bundle 存在于 scenes.json、level 合法
  4. data/tag_flags.json：与 scenes.json 同步（可重建）

用法：python tools/validate_data.py        # 有失败则退出码 1
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

EXPECT_CATS = 25
EXPECT_TAGS = 2956
EXPECT_BUNDLES = 45
EXPECT_TEMPLATES = 1800
VALID_LEVELS = {"sfw", "suggestive", "explicit", "hardcore", "extreme", "any"}
VALID_KINDS = {"normal", "monster"}

errors = []


def err(msg):
    errors.append(msg)


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def check_tags():
    raw = load("tags.json")
    cats = raw.get("cats", [])
    if len(cats) != EXPECT_CATS:
        err(f"tags.json 分类数 {len(cats)} != {EXPECT_CATS}")
    total = 0
    for c in cats:
        for t in c.get("tags", []):
            total += 1
            if not str(t.get("en") or "").strip():
                err(f"tags.json 分类 {c.get('id')} 有空标签")
            if not isinstance(t.get("lv"), int) or t["lv"] < 0 or t["lv"] > 4:
                err(f"tags.json 标签 {t.get('en')} 的 lv 非法: {t.get('lv')}")
    if total != EXPECT_TAGS:
        err(f"tags.json 词条数 {total} != {EXPECT_TAGS}")
    return total


def check_scenes():
    sc = load("scenes.json")
    bundles = sc.get("bundles", [])
    if len(bundles) != EXPECT_BUNDLES:
        err(f"scenes.json 场景包数 {len(bundles)} != {EXPECT_BUNDLES}")
    ids = set()
    for b in bundles:
        bid = b.get("id")
        if not bid:
            err("scenes.json 有场景包缺 id")
            continue
        if bid in ids:
            err(f"scenes.json 场景包 id 重复: {bid}")
        ids.add(bid)
        for key in ("env", "cloth", "shoes", "acc", "props", "poses"):
            if not isinstance(b.get(key), list) or not b.get(key):
                err(f"scenes.json {bid} 的 {key} 为空")
        if not isinstance(b.get("indoor"), bool):
            err(f"scenes.json {bid} 缺 indoor 标记")
        for key in ("water", "cold"):
            if not isinstance(b.get(key), bool):
                err(f"scenes.json {bid} 缺 {key} 标记")
        if not isinstance(b.get("time"), list):
            err(f"scenes.json {bid} 缺 time 标记")
    for mid in sc.get("monster_bundles") or []:
        if mid not in ids:
            err(f"scenes.json monster_bundles 含不存在的包: {mid}")
    for mid in sc.get("multi_bundles") or []:
        if mid not in ids:
            err(f"scenes.json multi_bundles 含不存在的包: {mid}")
    return ids


def check_templates(bundle_ids):
    items = load("templates_ui.json")
    if len(items) != EXPECT_TEMPLATES:
        err(f"templates_ui.json 模板数 {len(items)} != {EXPECT_TEMPLATES}")
    seen_id = set()
    for it in items:
        tid = it.get("id")
        if not tid:
            err(f"模板 #{it.get('index')} 缺 id")
        elif tid in seen_id:
            err(f"模板 id 重复: {tid}")
        else:
            seen_id.add(tid)
        idx = it.get("index")
        if not isinstance(idx, int) or not (1 <= idx <= EXPECT_TEMPLATES // 9):
            err(f"模板 {tid} 的 index 越界: {idx}")
        b = it.get("bundle")
        if b not in bundle_ids:
            err(f"模板 {tid} 的 bundle 不存在: {b}")
        if it.get("level") not in VALID_LEVELS:
            err(f"模板 {tid} 的 level 非法: {it.get('level')}")
        if it.get("kind") not in VALID_KINDS:
            err(f"模板 {tid} 的 kind 非法: {it.get('kind')}")
        prompt = str(it.get("prompt") or "")
        if not prompt.strip():
            err(f"模板 {tid} 的 prompt 为空")
        elif len([x for x in prompt.split(",") if x.strip()]) < 3:
            err(f"模板 {tid} 的 prompt 不足三段式")
    return len(items)


def check_tag_flags():
    path = os.path.join(DATA, "tag_flags.json")
    if not os.path.exists(path):
        err("data/tag_flags.json 不存在，先跑 python tools/build_tag_flags.py")
        return
    with open(path, encoding="utf-8") as f:
        on_disk = json.load(f)
    sys.path.insert(0, HERE)
    import build_tag_flags
    fresh = build_tag_flags.build()
    if set(on_disk) != set(fresh):
        err("data/tag_flags.json 与 scenes.json 不同步，请重跑 tools/build_tag_flags.py")


def main():
    n_tags = check_tags()
    bundle_ids = check_scenes()
    n_tpl = check_templates(bundle_ids)
    check_tag_flags()

    if errors:
        print(f"校验失败 {len(errors)} 项：")
        for e in errors[:40]:
            print("  ✗", e)
        return 1
    print(f"校验通过：{EXPECT_CATS} 分类 / {n_tags} 词条 / {len(bundle_ids)} 场景包 / {n_tpl} 模板")
    return 0


if __name__ == "__main__":
    sys.exit(main())
