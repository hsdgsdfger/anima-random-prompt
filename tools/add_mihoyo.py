# -*- coding: utf-8 -*-
"""补米哈游四款游戏里角色库还缺的女性角色（用户 2026-11-17 要求）。

写进 data/characters_extra.json —— 独立文件，重建 characters.json 不会覆盖它。
picker.library() 会把它和角色库、自定义角色合并（同 tag 时后者优先）。

只补「原神 / 崩坏：星穹铁道 / 绝区零 / 崩坏3」的**女性**角色；
已经在 characters.json 里的自动跳过，所以脚本可以反复跑。

缩略图这里留空（`thumb: ""`），面板会显示占位。
补图跑 `python tools/fetch_thumbs.py`（需要能上外网的环境）。

用法：python tools/add_mihoyo.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
BASE = os.path.join(DATA, "characters.json")
EXTRA = os.path.join(DATA, "characters_extra.json")
WORK_ZH = os.path.join(DATA, "work_zh.json")

# (tag, 中文名, 作品, 发色, 瞳色, 热度)
G = "genshin impact"
S = "honkai: star rail"
Z = "zenless zone zero"
H = "honkai impact"

ROLES = [
    # ── 原神 · 璃月 / 蒙德 ───────────────────────────────
    ("xinyan_(genshin_impact)", "辛焱", G, "black hair", "brown eyes", 9000),
    ("yun_jin_(genshin_impact)", "云堇", G, "black hair", "red eyes", 12000),
    ("yaoyao_(genshin_impact)", "瑶瑶", G, "brown hair", "brown eyes", 11000),
    # ── 原神 · 须弥 ─────────────────────────────────────
    ("candace_(genshin_impact)", "坎蒂丝", G, "blue hair", "amber eyes", 13000),
    ("dori_(genshin_impact)", "多莉", G, "pink hair", "purple eyes", 8000),
    # ── 原神 · 枫丹 ─────────────────────────────────────
    ("charlotte_(genshin_impact)", "夏洛蒂", G, "pink hair", "blue eyes", 10000),
    ("chevreuse_(genshin_impact)", "夏沃蕾", G, "purple hair", "purple eyes", 11000),
    ("emilie_(genshin_impact)", "艾梅莉埃", G, "green hair", "green eyes", 9000),
    # ── 原神 · 纳塔 ─────────────────────────────────────
    ("kachina_(genshin_impact)", "卡齐娜", G, "blonde hair", "green eyes", 8000),
    ("mualani_(genshin_impact)", "玛拉妮", G, "blue hair", "blue eyes", 12000),
    ("xilonen_(genshin_impact)", "希诺宁", G, "blonde hair", "green eyes", 13000),
    ("citlali_(genshin_impact)", "茜特菈莉", G, "pink hair", "red eyes", 14000),
    ("mavuika_(genshin_impact)", "玛薇卡", G, "red hair", "orange eyes", 18000),
    ("chasca_(genshin_impact)", "恰斯卡", G, "blonde hair", "blue eyes", 11000),
    ("iansan_(genshin_impact)", "伊安珊", G, "black hair", "yellow eyes", 7000),
    ("varesa_(genshin_impact)", "瓦蕾莎", G, "pink hair", "green eyes", 9000),
    ("lan_yan_(genshin_impact)", "蓝砚", G, "blue hair", "blue eyes", 7000),
    ("yumemizuki_mizuki_(genshin_impact)", "梦见月瑞希", G, "purple hair", "purple eyes", 8000),
    # ── 原神 · 其他 ─────────────────────────────────────
    ("skirk_(genshin_impact)", "丝柯克", G, "silver hair", "blue eyes", 15000),
    ("columbina_(genshin_impact)", "哥伦比娅", G, "white hair", "pink eyes", 16000),
    ("aloy_(horizon)", "埃洛伊", "horizon zero dawn", "red hair", "yellow eyes", 5000),
    # ── 绝区零 ──────────────────────────────────────────
    ("rina_(zenless_zone_zero)", "亚历山德丽娜", Z, "black hair", "purple eyes", 10000),
    ("lucy_(zenless_zone_zero)", "露西", Z, "blonde hair", "blue eyes", 9000),
    # ── 崩坏3 ──────────────────────────────────────────
    ("kallen_kaslana", "卡莲·卡斯兰娜", H, "white hair", "blue eyes", 12000),
    ("rosalia_(honkai_impact)", "萝莎莉娅·阿琳", H, "pink hair", "blue eyes", 9000),
    ("liliya_olenyeva", "莉莉娅·阿琳", H, "blue hair", "blue eyes", 9000),
    ("pardofelis_(honkai_impact)", "帕朵菲莉丝", H, "brown hair", "blue eyes", 10000),
    ("vill-v", "维尔薇", H, "brown hair", "red eyes", 9000),
    ("griseo", "格蕾修", H, "blue hair", "pink eyes", 8000),
    ("aponia_(honkai_impact)", "阿波尼亚", H, "purple hair", "purple eyes", 9000),
    ("eden_(honkai_impact)", "伊甸", H, "brown hair", "gold eyes", 8000),
    ("cocolia_(honkai_impact)", "可可利亚", H, "blonde hair", "blue eyes", 6000),
    ("cecilia_schariac", "塞西莉亚·沙尼亚特", H, "white hair", "blue eyes", 7000),
    ("susannah_(honkai_impact)", "苏莎娜", H, "orange hair", "green eyes", 6000),
    ("shigure_kirara_(honkai_impact)", "时雨绮罗", H, "black hair", "red eyes", 6000),
    ("carole_peppers", "卡萝尔·佩珀", H, "blonde hair", "blue eyes", 5000),
    ("timido_cute", "缇米朵·坎", H, "blonde hair", "blue eyes", 5000),
    ("frederica_nikola_tesla", "特斯拉", H, "blonde hair", "blue eyes", 6000),
    ("einstein_(honkai_impact)", "爱因斯坦", H, "blue hair", "blue eyes", 6000),
]


def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    base = load(BASE, {"characters": []})
    have = {c["tag"] for c in base.get("characters") or []}
    old = load(EXTRA, [])
    old_by_tag = {c["tag"]: c for c in old if isinstance(c, dict)}
    zh_work = load(WORK_ZH, {})

    added, skipped = [], []
    for tag, zh, work, hair, eyes, pop in ROLES:
        if tag in have:
            skipped.append((tag, "已在主库"))
            continue
        # danbooru 的 trigger 就是把 slug 里的下划线换成空格，括号内容原样保留：
        #   mavuika_(genshin_impact) -> "mavuika (genshin impact), genshin impact"
        #   aloy_(horizon)           -> "aloy (horizon), horizon zero dawn"
        name = tag.replace("_", " ").strip()
        trigger = f"{name}, {work}"
        ap = {}
        if hair:
            ap["hair_color"] = [hair]
        if eyes:
            ap["eyes"] = [eyes]
        rec = {
            "tag": tag,
            "name": name,
            "zh": zh,
            "work": work,
            "trigger": trigger,
            "pop": pop,
            "thumb": "",
            "src": "mihoyo",
            "subject": ["1girl"],
            "appearance": ap,
            "outfits": [],
        }
        if tag in old_by_tag:
            rec["thumb"] = old_by_tag[tag].get("thumb") or ""
        added.append(rec)

    merged = list(old_by_tag.values())
    merged.extend(added)
    with open(EXTRA, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)

    print(f"新增 {len(added)} 个，跳过 {len(skipped)} 个，extra 文件共 {len(merged)} 个")
    by_work = {}
    for c in added:
        by_work[c["work"]] = by_work.get(c["work"], 0) + 1
    print("按作品：", {zh_work.get(k, k): v for k, v in by_work.items()})
    if skipped:
        print("跳过：", ", ".join(t for t, _ in skipped[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
