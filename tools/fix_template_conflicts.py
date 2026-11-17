# -*- coding: utf-8 -*-
"""修模板里的穿衣冲突（用户 2026-11-17 要求「符合正常人的穿衣逻辑」）。

三类问题，按严重度排：
  ① **全裸 + 穿衣服** —— 259 套。`completely nude` / `nude` / `naked` 与
     t-shirt / winter coat / kimono 同时出现，模型必糊。处理：删服装，保留袜子与配饰
     （`only socks` 是合法风格，眼镜发饰不影响裸体成立）。
  ② 裙装 + 裤子 —— 13 套。见下方分层判定。
  ③ 上空 + 上装 —— 15 套。`topless` 与 shirt / sweater 同时出现，删上装。

判定分三层，只认「穿在身上」的词：
  · 一体式（dress / kimono / yukata / qipao / hanfu / 长裙）：占满下身，任何裤子都不要
  · 半身裙（skirt / pleated skirt / pencil skirt）：长裤与短裤都删
  · 泳装特例：one-piece swimsuit / bikini + swim shorts 是合理组合，保留

`up skirt` / `skirt lift` / `dress lift` 这类是**动作词**，不是服装，不参与判定 ——
早期按裸词匹配把它们算成裙子，才出现「30 套冲突」的误报。

用法：
    python tools/fix_template_conflicts.py          # 只看，不改
    python tools/fix_template_conflicts.py --write  # 真改 templates_ui.json
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
TPL = os.path.join(DATA, "templates_ui.json")

ONE_PIECE = re.compile(
    r"\b(one-piece dress|sundress|cocktail dress|wedding dress|evening gown|"
    r"china dress|cheongsam|qipao|hanfu|sari|kimono|yukata|japanese clothes|"
    r"dress)\b", re.I)
SKIRT = re.compile(r"\b(skirt|pleated skirt|pencil skirt|mini ?skirt|"
                   r"long skirt|denim skirt|tutu)\b", re.I)
LONG_PANTS = re.compile(r"\b(jeans|pants|trousers|slacks|leggings|sweatpants|"
                        r"cargo pants|track pants|jodhpurs)\b", re.I)
SHORTS = re.compile(r"\b(shorts|denim shorts|hot pants|bike shorts|"
                    r"spats|bloomers)\b", re.I)
# 动作 / 状态词：看着像服装，其实不是
ACTION = re.compile(r"\b(lift|up skirt|pull|aside|adjust|removed|"
                    r"partially removed|around waist|on one leg|"
                    r"holding|holding clothes|in mouth)\b", re.I)
# 泳装：和 swim shorts 同时出现是合理的
SWIM_TOP = re.compile(r"\b(bikini|one-piece swimsuit|competition swimsuit|"
                      r"school swimsuit|racing swimsuit|micro bikini|swimsuit)\b", re.I)
SWIM_SHORTS = re.compile(r"\bswim shorts\b", re.I)


def classify(tag):
    """返回 body / skirt / long / short / None。"""
    t = str(tag).strip()
    if not t or ACTION.search(t):
        return None
    if ONE_PIECE.search(t):
        return "body"
    if SKIRT.search(t):
        return "skirt"
    if LONG_PANTS.search(t):
        return "long"
    if SHORTS.search(t):
        return "short"
    return None


# 全裸 / 上空 / 下空
NUDE = re.compile(r"^(completely nude|fully nude|nude|naked)$", re.I)
TOPLESS_ONLY = re.compile(r"^topless$", re.I)
BOTTOMLESS_ONLY = re.compile(r"^bottomless$", re.I)
# 服装大类（全裸时要清掉）
GARMENT = re.compile(
    r"\b(skirt|dress|shirt|t-shirt|blouse|sweater|hoodie|jacket|coat|uniform|"
    r"jeans|pants|trousers|shorts|slacks|leggings|kimono|yukata|jinbei|qipao|"
    r"hanfu|sari|robe|bathrobe|pajamas|nightgown|leotard|bodysuit|swimsuit|"
    r"bikini|lingerie|underwear|bra|panties|camisole|cardigan|vest|apron|"
    r"cloak|cape|armor|serafuku|sailor collar|necktie|bowtie|scarf|muffler)\b", re.I)
# 上半身服装（上空时删）
TOPS = re.compile(
    r"\b(shirt|t-shirt|blouse|sweater|hoodie|jacket|coat|cardigan|vest|"
    r"bra|camisole|tank top|crop top|cloak|cape|necktie|bowtie|scarf|muffler)\b", re.I)
# 下半身服装（下空时删）
BOTTOMS = re.compile(
    r"\b(skirt|jeans|pants|trousers|shorts|slacks|leggings|panties|thong)\b", re.I)
# 袜子类：全裸也能留
HOSIERY = re.compile(r"\b(socks|thighhighs|stockings|pantyhose|kneehighs|"
                     r"leg warmers|garter straps?|garter belt)\b", re.I)


def resolve(tags):
    """返回 (新 tag 列表, 删掉的词, 原因)。没有冲突时原样返回。"""
    low = [str(t).strip().lower() for t in tags]

    # ① 全裸：清掉所有服装，保留袜子与配饰
    if any(NUDE.match(t) for t in low):
        drop = [t for t in tags
                if GARMENT.search(t) and not HOSIERY.search(t)]
        if drop:
            kept = [t for t in tags if t not in drop]
            return kept, drop, "全裸不穿衣服，删服装（保留袜子与配饰）"

    # ③ 上空 / 下空
    if any(TOPLESS_ONLY.match(t) for t in low):
        drop = [t for t in tags if TOPS.search(t)]
        if drop:
            return [t for t in tags if t not in drop], drop, "上空不穿上装"
    if any(BOTTOMLESS_ONLY.match(t) for t in low):
        drop = [t for t in tags if BOTTOMS.search(t)]
        if drop:
            return [t for t in tags if t not in drop], drop, "下空不穿下装"

    # ② 裙 / 裤
    kinds = [(t, classify(t)) for t in tags]
    bodies = [t for t, k in kinds if k == "body"]
    skirts = [t for t, k in kinds if k == "skirt"]
    longs = [t for t, k in kinds if k == "long"]
    shorts = [t for t, k in kinds if k == "short"]
    if not (bodies or skirts) or not (longs or shorts):
        return list(tags), [], ""

    text = ", ".join(tags)
    swim = bool(SWIM_TOP.search(text))
    drop = set()

    if bodies:
        drop.update(longs)
        drop.update(s for s in shorts if not (swim and SWIM_SHORTS.search(s)))
        reason = "一体式占满下身，删裤子"
    else:
        drop.update(longs)
        drop.update(shorts)
        reason = "半身裙不与裤子同穿，删裤子"

    kept = [t for t in tags if t not in drop]
    return kept, sorted(drop), reason


def check_all(items):
    bad = []
    for it in items:
        tags = [t.strip() for t in str(it.get("prompt") or "").split(",") if t.strip()]
        kept, dropped, why = resolve(tags)
        if dropped:
            bad.append((it, tags, kept, dropped, why))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="真的写回 templates_ui.json")
    args = ap.parse_args()

    with open(TPL, "r", encoding="utf-8") as f:
        items = json.load(f)

    bad = check_all(items)
    print(f"模板 {len(items)} 套，发现穿衣冲突 {len(bad)} 套\n")
    for it, tags, kept, dropped, why in bad:
        print(f"{it['id']} [{it['level']}]")
        print(f"  删：{', '.join(dropped)}   （{why}）")

    if not bad:
        print("没有冲突，无需修改")
        return 0
    if not args.write:
        print("\n（只是预览，加 --write 才真正写回）")
        return 0

    for it, tags, kept, dropped, why in bad:
        it["prompt"] = ", ".join(kept)
    with open(TPL, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n已写回 {TPL}，修了 {len(bad)} 套")

    left = check_all(items)
    print(f"复查：剩余冲突 {len(left)} 套")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
