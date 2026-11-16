# -*- coding: utf-8 -*-
"""PromptForge Random 的抽取引擎。

设计口径：
  · 档位在**候选池**这一层先筛（tag.lv <= 档位），不做「抽完再贴评级」；
  · 槽位（slot）= Forge 的分类，按固定顺序拼成一段完整提示词；
  · base_prob 是可选槽位的基准出现概率，slot_weights 可按槽位乘 0~3；
  · seed >= 0 时同一组输入逐字节可复现。
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "tags.json")

LEVEL_CHOICES = ["sfw", "suggestive", "explicit", "hardcore", "extreme", "any"]
LEVEL_NUM = {"sfw": 0, "suggestive": 1, "explicit": 2, "hardcore": 3, "extreme": 4, "any": 99}
LEVEL_ZH = {"sfw": "全年龄", "suggestive": "擦边", "explicit": "成人",
            "hardcore": "过激", "extreme": "极端", "any": "不限"}

# 槽位表：key / 用到的分类 / 是否必出 / 最多几条 / 基准概率 / 标签过滤
SLOTS = [
    {"key": "subject",   "cats": ["base"],        "need": 1, "max": 3, "prob": 1.00, "label": "主体"},
    {"key": "hair",      "cats": ["hair"],        "need": 1, "max": 1, "prob": 0.92, "label": "发型",
     "exclude": "color"},
    {"key": "hair_color","cats": ["hair"],        "need": 1, "max": 1, "prob": 0.88, "label": "发色",
     "only": "color"},
    {"key": "face",      "cats": ["face"],        "need": 1, "max": 1, "prob": 0.80, "label": "面部",
     "exclude": "color"},
    {"key": "eye_color", "cats": ["face"],        "need": 1, "max": 1, "prob": 0.85, "label": "瞳色",
     "only": "eye"},
    {"key": "body",      "cats": ["body"],        "need": 1, "max": 1, "prob": 0.70, "label": "身材"},
    {"key": "clothing",  "cats": ["clothing"],    "need": 1, "max": 2, "prob": 0.95, "label": "服装"},
    {"key": "accessory", "cats": ["accessory"],   "need": 1, "max": 1, "prob": 0.55, "label": "配饰"},
    {"key": "pose",      "cats": ["pose"],        "need": 1, "max": 2, "prob": 0.95, "label": "姿势"},
    {"key": "expression","cats": ["expression"],  "need": 1, "max": 1, "prob": 0.90, "label": "表情"},
    {"key": "camera",    "cats": ["camera"],      "need": 1, "max": 1, "prob": 0.60, "label": "镜头"},
    {"key": "composition","cats": ["composition"],"need": 1, "max": 1, "prob": 0.55, "label": "构图"},
    {"key": "environment","cats": ["environment"],"need": 1, "max": 1, "prob": 0.85, "label": "场景"},
    {"key": "weather",   "cats": ["weather"],     "need": 1, "max": 1, "prob": 0.40, "label": "天气"},
    {"key": "lighting",  "cats": ["lighting"],    "need": 1, "max": 1, "prob": 0.65, "label": "光影"},
    {"key": "props",     "cats": ["props"],       "need": 1, "max": 2, "prob": 0.55, "label": "道具"},
    {"key": "artstyle",  "cats": ["style"],       "need": 1, "max": 1, "prob": 0.30, "label": "画风"},
    {"key": "theme",     "cats": ["extra"],       "need": 1, "max": 1, "prob": 0.30, "label": "题材"},
    {"key": "monster",   "cats": ["monster"],     "need": 1, "max": 1, "prob": 0.06, "label": "异种"},
    {"key": "nsfw",      "cats": ["nsfwbody", "nsfwcloth", "nsfwact", "nsfwplay"],
     "need": 0, "max": 3, "prob": 1.00, "label": "成人向"},
]

# 拼装顺序（Danbooru 习惯：质量 → 主体 → 外观 → 服装 → 动作 → 表情 → 镜头 → 环境 → 特效 → 成人向）
ASM_ORDER = ["subject", "character", "hair", "hair_color", "face", "eye_color", "body",
             "clothing", "accessory", "pose", "expression", "camera", "composition",
             "environment", "weather", "lighting", "props", "artstyle", "theme",
             "monster", "nsfw", "rating"]

# 主体槽里绝对不要的（多人群像 / 男性 / 低龄 / 复合关系）
SUBJECT_DENY = re.compile(
    r"\b(1boy|2boys|2girls|3girls|multiple\w*|male focus|couple|twins|siblings|"
    r"androgynous|mature male|child|children|loli|shota|male)\b", re.I)

# 需要第二个人才能成立的姿势：抽到时主体改成 2girls（不再屏蔽）
MULTI_POSE = re.compile(
    r"\b(hugging from behind|hugging|holding hands|princess carry|back-to-back|"
    r"lap pillow|kiss|kissing|dancing waltz|carrying|embrace|embracing|headpat|"
    r"arm around|interlocked fingers)\b", re.I)
SOLO_POSE_SAFE = {"hugging knees", "hugging own legs", "hugging pillow", "hugging own knees"}

# 全库禁用的男性词（只有女性角色）
MALE_DENY = re.compile(
    r"\b(1boy|2boys|boys?|male|males|man|men|gentleman|penis|penises|testicles|"
    r"foreskin|erection|futanari|incubus)\b", re.I)

# 同一槽里避免「两个发色 / 两个瞳色」的冲突
COLORS = re.compile(
    r"\b(black|brown|blonde|blond|white|silver|grey|gray|red|pink|blue|purple|green|"
    r"orange|golden|auburn|turquoise|multicolored|two-tone|gradient|dark|light)\b", re.I)

# 成人向槽里，单人女性主体不成立的标签
NSFW_DENY = re.compile(
    r"\b(penis|penises|testicles|male|1boy|boys|yaoi|crotch|groin)\b", re.I)

RATING_TAGS = {0: ["safe"], 1: ["sensitive"], 2: ["nsfw"], 3: ["nsfw", "explicit"], 4: ["nsfw", "explicit"]}
NSFW_COUNT = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 99: 2}

_CORE_NEG = ["lowres", "bad anatomy", "worst quality", "low quality", "normal quality",
             "blurry", "extra fingers", "bad hands", "missing fingers", "extra digit",
             "fewer digits", "mutated hands", "poorly drawn face", "cropped",
             "out of frame", "jpeg artifacts", "watermark", "signature", "username",
             "text", "logo", "duplicate", "ugly"]

_CACHE = {}


def load_data():
    if "data" not in _CACHE:
        with open(DATA_PATH, encoding="utf-8") as f:
            _CACHE["data"] = json.load(f)
    return _CACHE["data"]


def _cat_map():
    if "cats" not in _CACHE:
        _CACHE["cats"] = {c["id"]: c for c in load_data()["cats"]}
    return _CACHE["cats"]


def _level_index():
    """en -> 档位（同名标签取最高，避免同一词在不同分类里档位打架）。"""
    if "lv" not in _CACHE:
        idx = {}
        for c in load_data()["cats"]:
            for t in c["tags"]:
                k = t["en"].lower()
                idx[k] = max(idx.get(k, 0), int(t["lv"]))
        _CACHE["lv"] = idx
    return _CACHE["lv"]


def tag_level(en):
    return _level_index().get(str(en).lower(), 0)


def drawable(cat_id, lv):
    """候选池：只保留 未标记 meta、且档位 <= 目标档位 的标签。"""
    out = []
    for t in _cat_map().get(cat_id, {}).get("tags", []):
        if t.get("meta"):
            continue
        if int(t["lv"]) <= lv:
            out.append(t)
    return out


def _subjects(lv):
    pool = [t for t in drawable("base", lv) if not SUBJECT_DENY.search(t["en"])]
    return pool or drawable("base", lv)


def pick_character(rng, role_mode, role_name, role_works):
    chars = load_data()["characters"]
    if role_mode == "specified" and role_name.strip():
        q = role_name.strip().lower()
        hits = [c for c in chars
                if q in c["tag"].lower() or q in c["name"].lower() or q in c["zh"].lower()]
        if hits:
            return hits[0]
        return None
    if role_mode != "random":
        return None
    pool = chars
    works = [w.strip().lower() for w in re.split(r"[|,，]", role_works or "") if w.strip()]
    if works:
        pool = [c for c in chars
                if any(w in c["game"].lower() or w in c["gameTag"].lower() for w in works)]
    return rng.choice(pool) if pool else None


def generate(level="sfw", seed=-1, tag_cap=0, base_prob=0.65, slot_weights="",
             role_mode="none", role_name="", role_works="", quality_prefix="masterpiece, best quality",
             artist_on=False, extra_body="", negative_on=True, scene_mode="scene",
             override_text=""):
    lv = LEVEL_NUM.get(str(level), 0)

    # 面板里选中成品模板时，直接用它当正向，仍按档位生成负向
    override = str(override_text or "").strip()
    if override:
        positive = override.rstrip(", ")
        if str(extra_body or "").strip():
            positive = positive + ", " + str(extra_body).strip().strip(",")
        negative = build_negative(lv, positive, negative_on)
        return {
            "positive": positive,
            "negative": negative,
            "level": level,
            "report": "\n".join([f"档位: {level}",
                                 "模式: 模板覆盖（使用面板选中的成品提示词）",
                                 "想恢复随机：把 template_override 清空"]),
        }

    rng = random.Random(seed) if int(seed) >= 0 else random.Random()

    try:
        weights = json.loads(slot_weights) if str(slot_weights or "").strip() else {}
        if not isinstance(weights, dict):
            weights = {}
    except Exception:
        weights = {}

    if str(scene_mode) == "scene":
        res = _generate_scene(lv, level, rng, tag_cap, base_prob, weights, role_mode,
                              role_name, role_works, quality_prefix, artist_on,
                              extra_body, negative_on, seed)
        if res:
            return res
        # 场景拼不出来（几乎不会发生）就退回自由随机，保证节点永远有输出
        return generate(level=level, seed=seed, tag_cap=tag_cap, base_prob=base_prob,
                        slot_weights=slot_weights, role_mode=role_mode, role_name=role_name,
                        role_works=role_works, quality_prefix=quality_prefix,
                        artist_on=artist_on, extra_body=extra_body,
                        negative_on=negative_on, scene_mode="free")
    chosen = {}          # slot -> [(en, zh)]
    seen = set()

    def add(slot_key, tag):
        en = tag["en"].strip()
        k = en.lower()
        if not en or k in seen:
            return False
        if MALE_DENY.search(en):          # 只出女性角色，男性词一律不进
            return False
        seen.add(k)
        chosen.setdefault(slot_key, []).append(tag)
        return True

    # 主体：必定 1girl + solo
    add("subject", {"en": "1girl", "zh": "一个女孩", "lv": 0})
    add("subject", {"en": "solo", "zh": "单人或单人特写", "lv": 0})
    if rng.random() < 0.55:
        for _ in range(6):
            t = rng.choice(_subjects(lv))
            if add("subject", t):
                break

    # 角色（可选）：角色 tag + 官方外观标签
    char = pick_character(rng, role_mode, role_name, role_works)
    if char:
        add("character", {"en": char["tag"], "zh": char["zh"], "lv": 0})
        for a in char.get("auto", [])[:6]:
            if tag_level(a["en"]) <= lv:
                add("character", {"en": a["en"], "zh": a.get("zh", ""), "lv": tag_level(a["en"])})

    # 画师（可选）
    if artist_on:
        pool = drawable("artist", lv)
        if pool:
            add("artstyle", rng.choice(pool))

    # 其余槽位
    default_base = 0.65
    for s in SLOTS:
        if s["key"] in ("subject", "nsfw"):
            continue
        if s["key"] == "artstyle" and artist_on:
            continue                      # 画师已经占用这个位置
        w = float(weights.get(s["key"], 1.0))
        if w <= 0:
            continue
        p = min(1.0, max(0.0, s["prob"] * w * (float(base_prob) / default_base)))
        if s["need"] and rng.random() > p:
            continue
        pool = [t for c in s["cats"] for t in drawable(c, lv)]
        only = s.get("only")
        if only == "color":
            pool = [t for t in pool if COLORS.search(t["en"])]
        elif only == "eye":
            pool = [t for t in pool if re.search(r"\beyes\b", t["en"], re.I)]
        elif s.get("exclude") == "color":
            pool = [t for t in pool if not COLORS.search(t["en"])]
        if not pool:
            continue
        n = s["need"] if s["max"] <= 1 else rng.randint(s["need"], s["max"])
        for _ in range(n * 3):
            if len(chosen.get(s["key"], [])) >= n:
                break
            t = rng.choice(pool)
            # 发色/瞳色冲突：同槽已有颜色词则跳过带颜色词的新标签
            if s["key"] in ("hair", "face"):
                cur = [x["en"] for x in chosen.get(s["key"], [])]
                if COLORS.search(t["en"]) and any(COLORS.search(c) for c in cur):
                    continue
            add(s["key"], t)

    # 抽到需要两个人的姿势：主体换成 2girls，去掉 solo（不再屏蔽这类姿势）
    multi_pose = next((x["en"] for x in chosen.get("pose", [])
                       if MULTI_POSE.search(x["en"])
                       and x["en"].lower() not in SOLO_POSE_SAFE), None)
    if multi_pose:
        chosen["subject"] = [{"en": "2girls", "zh": "两个女孩", "lv": 0}]
        seen.discard("1girl")
        seen.discard("solo")
        seen.add("2girls")
        duo = {"en": "duo", "zh": "双人构图", "lv": 0}
        chosen.setdefault("composition", []).append(duo)
        seen.add("duo")

    # 成人向：按档位定量，仍受同一套候选池闸门约束
    nsfw_n = NSFW_COUNT.get(lv, 0)
    if nsfw_n:
        pool = [t for s in SLOTS if s["key"] == "nsfw" for c in s["cats"] for t in drawable(c, lv)]
        pool = [t for t in pool if not NSFW_DENY.search(t["en"])]
        for _ in range(nsfw_n * 4):
            if len(chosen.get("nsfw", [])) >= nsfw_n or not pool:
                break
            add("nsfw", rng.choice(pool))

    # 评级词
    for r in RATING_TAGS.get(lv, []) if lv <= 4 else []:
        add("rating", {"en": r, "zh": "", "lv": 0})

    # 拼装
    order = ASM_ORDER
    parts = []
    if str(quality_prefix or "").strip():
        parts.append(str(quality_prefix).strip().rstrip(","))
    for key in order:
        for t in chosen.get(key, []):
            parts.append(t["en"])
    if str(extra_body or "").strip():
        parts.append(str(extra_body).strip())

    # 密度裁剪：去重后按 tag_cap 截断（从尾部丢，先丢修饰类）
    flat = []
    for p in parts:
        for seg in str(p).split(","):
            seg = seg.strip()
            if seg and seg.lower() not in {x.lower() for x in flat}:
                flat.append(seg)
    cap = int(tag_cap) if int(tag_cap or 0) > 0 else (28 if lv <= 1 else 32)
    if len(flat) > cap:
        drop_order = ["props", "weather", "composition", "camera", "accessory", "theme", "monster"]
        dropped = []
        for key in drop_order:
            for t in chosen.get(key, []):
                if t["en"] in flat and len(flat) > cap:
                    flat.remove(t["en"])
                    dropped.append(t["en"])
        flat = flat[:cap]

    positive = ", ".join(flat)
    negative = build_negative(lv, positive, negative_on)

    counts = {s["label"]: len(chosen.get(s["key"], [])) for s in SLOTS if chosen.get(s["key"])}
    if chosen.get("character"):
        counts["角色"] = len(chosen["character"])
    report_lines = [
        f"档位: {lv if lv != 99 else '不限'} · {LEVEL_ZH.get(str(level), '不限')}",
        f"标签: {len(flat)} 个（" + " / ".join(f"{k} {v}" for k, v in counts.items()) + "）",
        f"角色: {char['zh'] if char else '不指定'}",
        f"种子: {seed}",
        f"负面: {len([x for x in negative.split(',') if x.strip()])} 个",
    ]
    return {
        "positive": positive,
        "negative": negative,
        "level": f"{lv if lv != 99 else 'any'} · {LEVEL_ZH.get(str(level), '不限')}",
        "report": "\n".join(report_lines),
        "level_num": lv,
        "character": char,
        "picked": [{"slot": k, "en": t["en"], "lv": int(t.get("lv", 0))}
                   for k, items in chosen.items() for t in items],
    }


def _generate_scene(lv, level, rng, tag_cap, base_prob, weights, role_mode, role_name,
                    role_works, quality_prefix, artist_on, extra_body, negative_on, seed):
    """场景成套路径：环境/季节/服装/道具/姿势绑在一个包里，出来的串自带现实逻辑。"""
    try:
        from . import scenes
    except ImportError:                     # 单独跑脚本时的兜底
        import scenes

    char = pick_character(rng, role_mode, role_name, role_works)
    monster_on = float(weights.get("monster", 1.0) or 0) > 0 and rng.random() < 0.06

    items, bundle_id = None, None
    for _ in range(60):
        items, bundle_id = scenes.build(lv, rng, weights, base_prob,
                                        monster=monster_on,
                                        has_character=bool(char))
        if items:
            break
    if not items:
        return None

    # 角色：插在主体后面；官方外观按档位滤一遍
    char_tags = []
    if char:
        char_tags.append((char["tag"], 0))
        for a in char.get("auto", [])[:6]:
            if scenes.level_of(a["en"]) <= (99 if lv >= 99 else lv):
                char_tags.append((a["en"], scenes.level_of(a["en"])))

    ordered = []
    subject_done = False
    for slot, en in items:
        ordered.append((slot, en))
        if slot == "subject" and not subject_done:
            # 主体标签可能有两个（1girl + solo），等主体组结束后再插角色
            pass
    # 主体组在最前面，统一在第一个非 subject 之前插入角色
    first_non_subject = next((i for i, (s, _) in enumerate(ordered) if s != "subject"), len(ordered))
    for i, (en, _) in enumerate(char_tags):
        ordered.insert(first_non_subject + i, ("character", en))

    chosen = {}
    for slot, en in ordered:
        chosen.setdefault(slot, []).append({"en": en, "lv": 0})

    # 画师（可选）
    if artist_on:
        pool = drawable("artist", lv)
        if pool:
            chosen.setdefault("artstyle", []).append({"en": rng.choice(pool)["en"], "lv": 0})

    parts = []
    if str(quality_prefix or "").strip():
        parts.append(str(quality_prefix).strip().rstrip(","))
    for slot, en in ordered:
        parts.append(en)
    if artist_on:
        for t in chosen.get("artstyle", [])[1:]:
            parts.append(t["en"])
    if str(extra_body or "").strip():
        parts.append(str(extra_body).strip())

    flat = []
    for p in parts:
        for seg in str(p).split(","):
            seg = seg.strip()
            if seg and seg.lower() not in {x.lower() for x in flat}:
                flat.append(seg)
    cap = int(tag_cap) if int(tag_cap or 0) > 0 else (28 if lv <= 1 else 32)
    if len(flat) > cap:
        for key in ("props", "weather", "accessory", "camera", "composition", "theme", "monster"):
            for t in chosen.get(key, []):
                if t["en"] in flat and len(flat) > cap:
                    flat.remove(t["en"])
        flat = flat[:cap]

    positive = ", ".join(flat)
    negative = build_negative(lv, positive, negative_on)

    labels = {s["key"]: s["label"] for s in SLOTS}
    labels.update({"breast": "胸围", "season": "季节", "rating": "评级", "time": "时间",
                   "character": "角色", "composition": "构图", "theme": "题材"})
    counts = {}
    for slot, _ in ordered:
        counts[labels.get(slot, slot)] = counts.get(labels.get(slot, slot), 0) + 1
    report_lines = [
        f"档位: {lv if lv != 99 else '不限'} · {LEVEL_ZH.get(str(level), '不限')}",
        f"场景: {bundle_id}（场景成套，环境/服装/道具/姿势同一套）",
        f"标签: {len(flat)} 个（" + " / ".join(f"{k} {v}" for k, v in counts.items()) + "）",
        f"角色: {char['zh'] if char else '不指定'}",
        f"种子: {seed}",
        f"负面: {len([x for x in negative.split(',') if x.strip()])} 个",
    ]
    return {
        "positive": positive,
        "negative": negative,
        "level": f"{lv if lv != 99 else 'any'} · {LEVEL_ZH.get(str(level), '不限')}",
        "report": "\n".join(report_lines),
        "level_num": lv,
        "character": char,
        "bundle": bundle_id,
        "picked": [{"slot": slot, "en": en, "lv": 0} for slot, en in ordered],
    }


def build_negative(lv, positive, enabled=True):
    if not enabled:
        return ""
    rng = random.Random(0)  # 负面词固定，保证同 seed 全程可复现
    neg = list(_CORE_NEG)
    pool = [t["en"] for t in drawable("negative", 99) if t["en"].lower() not in {x.lower() for x in neg}]
    rng.shuffle(pool)
    for en in pool:
        if len(neg) >= 26:
            break
        neg.append(en)
    pos = {p.strip().lower() for p in positive.split(",")}
    neg = [n for n in neg if n.lower() not in pos]
    if lv >= 2:
        # 正向要成人内容时，负面里不能再压 nsfw / safe 一类词，否则互相打架
        neg = [n for n in neg if not re.search(r"\b(nsfw|safe|sensitive|rating|questionable)\b", n, re.I)]
    return ", ".join(neg)
