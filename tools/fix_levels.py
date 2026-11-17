# -*- coding: utf-8 -*-
"""把「衣服 / 身材 / 姿势」里标错档位的词改回正确档位（v0.2.1）。

背景（用户 2026-11-17 报）：sfw 档仍然出比基尼、出大腿环、出大胸。
根因是 data/tags.json 里 clothing 分类有 187 条全标 lv0，
其中泳装 / 内衣 / 情趣装全在里面 —— sfw 的候选池（lv<=0）直接就能抽到它们。

这个脚本只做一件事：按下面的表重写 lv，幂等，重复跑不会越改越乱。

档位约定：
  0 全年龄：日常衣物，躯干和下装都要遮住
  1 擦边  ：泳装、连体紧身衣、露肩露脐、身材强调
  2 成人  ：内衣内裤、透明、情趣装、大腿环/吊带袜夹、巨乳
  3 硬核  ：脱衣、暴露、性行为前置
  4 极端  ：性行为本体
"""
import json
import os
import sys

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAGS = os.path.join(DIR, "data", "tags.json")

# (分类, 标签) -> 新档位
FIX = {
    # ---------------- 泳装 / 连体紧身衣：擦边 ----------------
    ("clothing", "bikini"): 1,
    ("clothing", "swimsuit"): 1,
    ("clothing", "one-piece swimsuit"): 1,
    ("clothing", "competition swimsuit"): 1,
    ("clothing", "school swimsuit"): 1,
    ("clothing", "leotard"): 1,
    ("clothing", "bodysuit"): 1,
    ("clothing", "bloomers"): 1,
    ("clothing", "tube top"): 1,
    ("clothing", "halter top"): 1,
    ("clothing", "camisole"): 1,
    ("clothing", "crop top"): 1,
    ("clothing", "midriff"): 1,
    ("clothing", "collarbone"): 1,
    ("clothing", "straps"): 1,
    ("clothing", "sarong"): 1,
    ("clothing", "cloth wrap"): 1,
    # ---------------- 真内衣 / 情趣装：成人 ----------------
    ("clothing", "bra"): 2,
    ("clothing", "underwear"): 2,
    ("clothing", "lingerie"): 2,
    ("clothing", "babydoll"): 2,
    ("clothing", "chemise"): 2,
    ("clothing", "garter straps"): 2,
    ("clothing", "garter belt"): 2,
    ("clothing", "corset"): 2,
    ("clothing", "see-through"): 2,
    ("clothing", "backless"): 2,
    ("clothing", "nightgown"): 2,
    ("clothing", "pajamas"): 1,
    # ---------------- 绑带 / 腿环类 ----------------
    ("extra", "thigh strap"): 1,
    ("extra", "jewelry"): 0,
    # ---------------- 身材：强调性化的往高档位推 ----------------
    # 只推「身材倾向」类；纯部位词（navel / hips / thighs）保持 0，
    # 它们本身不擦边，露不露由服装决定，推上去只会让正常角色失真。
    ("body", "huge breasts"): 2,
    ("body", "large breasts"): 1,
    ("body", "buxom"): 1,
    ("body", "voluptuous"): 1,
    ("body", "curvy"): 1,
    ("body", "thick thighs"): 1,
    ("body", "wide hips"): 1,
    ("body", "hourglass figure"): 1,
    ("body", "pear-shaped body"): 1,
    ("body", "navel"): 0,
    ("body", "hips"): 0,
    ("body", "thighs"): 0,
    ("body", "bare midriff"): 1,
    ("body", "midriff"): 1,
    # ---------------- 姿势 ----------------
    # 同理：只挡「明示性暗示」的姿势。「趴着 / 弯腰 / 手背在身后 / 床上」
    # 这些都是正常姿势，推档会把 sfw 模板里的 `on bed` 一起删掉
    # （nsfwact 分类里有同名条目 lv3，别被它带跑）。
    ("pose", "legs spread"): 1,
    ("pose", "on stomach"): 0,
    ("pose", "bending over"): 0,
    ("pose", "arms behind back"): 0,
}


def main():
    with open(TAGS, encoding="utf-8") as f:
        data = json.load(f)
    cats = {c["id"]: c for c in data["cats"]}
    changed, missing = [], []
    for (cid, en), lv in FIX.items():
        c = cats.get(cid)
        if not c:
            missing.append(f"{cid}/{en}")
            continue
        hit = False
        for t in c["tags"]:
            if t["en"].lower() == en.lower():
                hit = True
                if int(t["lv"]) != lv:
                    changed.append(f"{cid:10s} {en:24s} {t['lv']} -> {lv}")
                    t["lv"] = lv
        if not hit:
            missing.append(f"{cid}/{en}")

    # 自检：同名标签跨分类取最高，避免「clothing 里 0、nsfwcloth 里 2」这种打架
    best = {}
    for c in data["cats"]:
        for t in c["tags"]:
            k = t["en"].lower()
            best[k] = max(best.get(k, 0), int(t["lv"]))
    conflict = [(c["id"], t["en"], t["lv"], best[t["en"].lower()])
                for c in data["cats"] for t in c["tags"]
                if int(t["lv"]) < best[t["en"].lower()]]
    if conflict:
        for cid, en, lv, hi in conflict:
            print(f"  同名下限低于全库最高：{cid:10s} {en:24s} {lv} < {hi}")

    with open(TAGS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"改档 {len(changed)} 条")
    for line in changed:
        print("  ", line)
    if missing:
        print(f"表里有 {len(missing)} 个词在数据里找不到：{', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
