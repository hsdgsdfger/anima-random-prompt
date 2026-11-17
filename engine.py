# -*- coding: utf-8 -*-
"""PromptForge Random 的抽取引擎。

设计口径：
  · 档位分两层：**选择档位**（用户选的 level）与**目标档位**（本次实际取词的上限）；
    目标档位由 settings 的档位分布 / any 配比抽样得到，永远不高于选择档位；
  · 档位在**候选池**这一层先筛（tag.lv <= 目标档位），不做「抽完再贴评级」；
  · 槽位（slot）= Forge 的分类，按固定顺序拼成一段完整提示词；
  · base_prob 是可选槽位的基准出现概率，slot_weights 可按槽位乘 0~3；
  · seed >= 0 时同一组输入逐字节可复现。
"""
import json
import os
import random
import re

try:                                        # 包内正常路径
    from .wordlists import regex as _wl_re
except ImportError:                         # 单独跑脚本时的兜底
    from wordlists import regex as _wl_re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "tags.json")

LEVEL_CHOICES = ["sfw", "suggestive", "explicit", "hardcore", "extreme", "any"]
LEVEL_NUM = {"sfw": 0, "suggestive": 1, "explicit": 2, "hardcore": 3, "extreme": 4, "any": 99}
LEVEL_ZH = {"sfw": "全年龄", "suggestive": "擦边", "explicit": "成人",
            "hardcore": "过激", "extreme": "极端", "any": "不限"}

# 档位抽样只认这五档（any 是选择档位，不是目标档位）
TARGET_LEVELS = ["sfw", "suggestive", "explicit", "hardcore", "extreme"]

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

# 外部角色输入里的主体词：命中即替换默认主体（REQ-104 缺口 5）
SUBJECT_TOKEN = re.compile(r"\b(1girl|1girls|2girls|3girls|multiple girls|solo|duo)\b", re.I)

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

# ---------------- 词表（统一维护在 data/garment_words.json） ----------------
# 以前 engine.py 与 scenes.py 各写一份，补词要改两处，容易漂移。
_GARMENT = _wl_re("garment")
_HOSIERY = _wl_re("hosiery")
_NUDE_RE = _wl_re("nude")
_NSFW_CLOTH = _wl_re("nsfw_cloth")
_APPEAR_HINT = _wl_re("appear")
_CLOTH_STATE = _wl_re("cloth_state")
# 兼容旧代码里 `t["en"] in NUDE_TAGS` 的写法
NUDE_TAGS = {"completely nude", "fully nude", "nude", "naked",
             "nude with accessories only"}

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
    """候选池：只保留 未标记 meta、且档位 <= 目标档位 的标签。

    结果按 (分类, 档位) 缓存 —— 出一次词要调 30 多次（20 个槽位 + nsfw 四类），
    每次遍历几百条纯属浪费。返回的 list 只读，调用方都在上面做推导式，不会改它。
    """
    key = ("pool", cat_id, int(lv))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    out = []
    for t in _cat_map().get(cat_id, {}).get("tags", []):
        if t.get("meta"):
            continue
        if int(t["lv"]) <= lv:
            out.append(t)
    _CACHE[key] = out
    return out


def _subjects(lv):
    pool = [t for t in drawable("base", lv) if not SUBJECT_DENY.search(t["en"])]
    return pool or drawable("base", lv)


def _char_pool():
    """角色池统一走 picker.library()：2471 个，带外观与服装预设。

    以前这里读 tags.json 里那 1401 个老记录（只有 tag/auto，没有服装），
    和角色库面板是两套数据 —— 用户设了收藏、勾选池，随机却完全不受影响。
    """
    try:
        from . import picker as _pk
        return _pk.library()["characters"]
    except Exception:
        return load_data().get("characters") or []


def char_appearance(char):
    """取一个角色的外观标签（兼容两套结构：老的 auto / 新的 appearance 桶）。"""
    auto = char.get("auto")
    if auto:
        return [str(a.get("en") if isinstance(a, dict) else a) for a in auto[:8]]
    ap = char.get("appearance") or {}
    out = []
    for k in ("hair_color", "hair_style", "eyes", "face", "body", "extras"):
        out.extend(str(x) for x in (ap.get(k) or []))
    return out[:8]


def char_outfit(char, outfit_id=""):
    """取角色的一套服装标签；装备了一套就只有那一套（其余自动失效）。"""
    outs = char.get("outfits") or []
    if not outs:
        return []
    if outfit_id:
        for o in outs:
            if str(o.get("id")) == str(outfit_id):
                return [str(x) for x in (o.get("tags") or [])]
    return [str(x) for x in (outs[0].get("tags") or [])]


def pick_character(rng, role_mode, role_name, role_works):
    """role_mode: none / random / specified / favorites / weighted。

    favorites = 只在收藏里抽；weighted = 只在勾选池里按权重抽。
    两者都直接读角色库的 userdata 状态，和面板是同一份数据。
    """
    chars = _char_pool()
    if not chars:
        return None
    name = str(role_name or "").strip().lower()
    if role_mode == "specified" and name:
        hits = [c for c in chars
                if name in str(c.get("tag") or "").lower()
                or name in str(c.get("name") or "").lower()
                or name in str(c.get("zh") or "").lower()]
        return hits[0] if hits else None
    if role_mode in ("none", ""):
        return None

    pool = chars
    if role_mode in ("favorites", "weighted"):
        try:
            from . import char_state as _cs
            st = _cs.load_state()
            key = "favorites" if role_mode == "favorites" else "picked"
            allow = [str(x) for x in (st.get(key) or [])]
            if not allow:
                return None
            pool = [c for c in chars if c["tag"] in set(allow)]
        except Exception:
            return None
        if not pool:
            return None

    works = [w.strip().lower() for w in re.split(r"[|,，]", role_works or "") if w.strip()]
    if works:
        zh_map = {}
        try:
            from . import picker as _pk
            zh_map = _pk.work_zh_map()
        except Exception:
            pass
        def _match(c):
            wid = str(c.get("work") or "").lower()
            blob = " ".join((wid, zh_map.get(wid, ""), str(c.get("trigger") or "").lower()))
            return any(w in blob for w in works)
        pool = [c for c in pool if _match(c)]
        if not pool:
            return None

    if role_mode == "weighted":
        try:
            from . import char_state as _cs
            w = (_cs.load_state().get("weights") or {})
            return _pick_weighted(pool, w, rng)
        except Exception:
            pass
    return rng.choice(pool) if pool else None


def _pick_weighted(pool, weights, rng):
    """按面板里设的权重抽；没设权重一律 1.0。"""
    total = 0.0
    vals = []
    for c in pool:
        try:
            w = float(weights.get(c["tag"], 1.0))
        except (TypeError, ValueError):
            w = 1.0
        w = max(0.0, w)
        vals.append(w)
        total += w
    if total <= 0:
        return rng.choice(pool)
    r = rng.random() * total
    acc = 0.0
    for c, w in zip(pool, vals):
        acc += w
        if r < acc:
            return c
    return pool[-1]


# ---------------------------------------------------------------- 档位抽样

def _wchoice(rng, weights):
    """按权重抽一个下标；全 0 时返回 0。"""
    total = sum(weights)
    if total <= 0:
        return 0
    r = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r < acc:
            return i
    return len(weights) - 1


def pick_target(level_key, settings, rng):
    """抽本次运行的目标档位；返回 (目标档位序号, 抽样依据)。"""
    st = settings or {}

    if level_key == "any":
        raw = st.get("any_weights") or {}
        weights = []
        for k in TARGET_LEVELS:
            try:
                weights.append(max(0.0, float(raw.get(k, 0) or 0)))
            except (TypeError, ValueError):
                weights.append(0.0)
        if sum(weights) <= 0:                     # 全 0 / 损坏 -> 默认 70 / 7.5×4
            weights = [0.7, 0.075, 0.075, 0.075, 0.075]
        return _wchoice(rng, weights), "any 配比"

    sel = LEVEL_NUM.get(level_key, 0)
    if not st.get("level_dist"):
        return sel, "上限过滤（档位分布未开启）"

    row = (st.get("level_matrix") or {}).get(level_key) or {}
    weights = []
    for i, k in enumerate(TARGET_LEVELS):
        if i > sel:                                # 上三角锁死：永远不越档
            weights.append(0.0)
            continue
        try:
            weights.append(max(0.0, float(row.get(k, 0) or 0)))
        except (TypeError, ValueError):
            weights.append(0.0)
    if sum(weights) <= 0:
        return sel, "上限过滤（矩阵无效回退）"
    return _wchoice(rng, weights), "档位分布矩阵"


def _auto_cap(tv):
    return 28 if tv <= 1 else 32


def _slot_weight(weights, key, default=1.0):
    """槽位权重读取：非数字（"high" / null / 对象）一律回落到默认值。

    以前这里是裸 float()，用户把 JSON 写错一个字就 ValueError，节点直接中断，
    而场景路径有自己的兜底，两条路径行为不一致。
    """
    try:
        return float((weights or {}).get(key, default))
    except (TypeError, ValueError, AttributeError):
        return default


# ---------------------------------------------------------------- 外部角色词

def split_role(role_prompt):
    """外部角色词：按英文逗号拆分、去空格、忽略大小写去重、丢掉男性词。

    返回 (保留词表, 被拒数量)。被拒的词直接丢弃，不整段拒绝（DEC-04）。
    """
    kept, rejected, seen = [], 0, set()
    for seg in str(role_prompt or "").split(","):
        s = seg.strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        if MALE_DENY.search(s):
            rejected += 1
            continue
        seen.add(k)
        kept.append(s)
    return kept, rejected


# ---------------------------------------------------------------- 主流程

def generate(level="sfw", seed=-1, tag_cap=0, base_prob=0.65, slot_weights="",
             role_mode="none", role_name="", role_works="", quality_prefix="masterpiece, best quality",
             artist_on=False, extra_body="", negative_on=True, scene_mode="scene",
             override_text="", override_mode="direct", role_prompt="", settings=None,
             appearance_follow=True, outfit_follow=False, scene_hint="",
             char_outfit_id=""):
    sel_key = str(level)
    if sel_key not in LEVEL_NUM:
        sel_key = "sfw"
    sel_num = LEVEL_NUM[sel_key]

    override = str(override_text or "").strip()
    mixed = str(override_mode or "direct") == "mixed"
    ext_kept, ext_rejected = split_role(role_prompt)
    # 主体词 / 让位槽位都要等目标档位定下来再算（档位会过滤掉泳装内衣），
    # 先占位，下面 pick_target 之后填。
    ext_subjects, ext_others, follow = [], [], set()

    # 覆盖直通：直接当正向，完全跳过随机（负向按用户选择档位）
    if override and not mixed:
        positive = override.rstrip(", ")
        if str(extra_body or "").strip():
            positive = positive + ", " + str(extra_body).strip().strip(",")
        negative = build_negative(sel_num, positive, negative_on)
        lines = [f"档位: {sel_key}",
                 "模式: 模板覆盖（使用面板选中的成品提示词）",
                 "想恢复随机：把 template_override 清空"]
        if ext_kept:
            lines.append("角色来源: 外部输入（当前为模板覆盖，角色输入未生效）")
        return {
            "positive": positive,
            "negative": negative,
            "level": f"{sel_num if sel_num != 99 else 'any'} · {LEVEL_ZH.get(sel_key, '不限')}",
            "report": "\n".join(lines),
        }

    rng = random.Random(seed) if int(seed) >= 0 else random.Random()
    tv, basis = pick_target(sel_key, settings, rng)

    # 低档位剔除外部输入里的泳装 / 内衣：角色库的 outfit 是统计出来的，
    # 有 8 个角色的「官方服装」本身就是比基尼（如 bay_(nikke)），
    # sfw 档照搬进来就是「全年龄出泳装」（用户 2026-11-17 报的）。
    if tv <= 1 and ext_kept:
        kept2 = [t for t in ext_kept if not _NSFW_CLOTH.search(t)]
        ext_rejected += len(ext_kept) - len(kept2)
        ext_kept = kept2

    ext_subjects = [t for t in ext_kept if SUBJECT_TOKEN.search(t)]
    ext_others = [t for t in ext_kept if not SUBJECT_TOKEN.search(t)]

    # 外部角色输入存在时，外观 / 服装是否让位（REQ：角色外观必须跟着提示词走）
    if ext_kept:
        # 让位要看外部**实际带了什么**：无条件让位会让服装槽永久关闭，
        # 角色节点没输出服装时整段提示词一件衣服都没有 —— 模型只能自己编，
        # sfw 档在雪地里画出比基尼就是这么来的（用户 2026-11-17 报的）。
        has_appear = any(_APPEAR_HINT.search(t) for t in ext_kept)
        has_cloth = any(_GARMENT.search(t) for t in ext_kept)
        if appearance_follow and has_appear:
            follow.update(["hair", "hair_color", "face", "eye_color", "body"])
        if outfit_follow and has_cloth:
            follow.update(["clothing", "accessory"])

    try:
        weights = json.loads(slot_weights) if str(slot_weights or "").strip() else {}
        if not isinstance(weights, dict):
            weights = {}
    except Exception:
        weights = {}

    head = [f"选择档位: {sel_key} · {LEVEL_ZH.get(sel_key, '不限')}",
            f"本次目标档位: Lv{tv} · {LEVEL_ZH.get(TARGET_LEVELS[tv], '')}",
            f"抽样依据: {basis}"]
    if ext_rejected:
        head.append(f"已剔除 {ext_rejected} 个不适用词（男性词 / 低档位泳装内衣）")
    if ext_kept:
        head.append("外部角色: 服装按档位过滤")
    if follow:
        head.append("让位槽位: " + " / ".join(
            s["label"] for s in SLOTS if s["key"] in follow) + "（交给角色输入）")

    if override:                                    # 混合模式：锁定词 + 局部随机
        return _generate_mixed(sel_key, sel_num, tv, basis, head, override, rng,
                               tag_cap, base_prob, weights, role_mode, role_name,
                               role_works, quality_prefix, artist_on, extra_body,
                               negative_on, scene_mode, seed, settings,
                               ext_kept, ext_rejected, follow,
                               appearance_follow, outfit_follow)

    if str(scene_mode) == "scene":
        # 让位的槽位在场景路径里靠权重 0 关闭：scenes.build 的完整性校验
        # 见到 `b.on(key)` 为 False 就跳过该槽，不会判「缺槽」重抽。
        #
        # 服装例外：先让场景正常产一套，build 之后再按场景类型取舍 ——
        # 普通场景用角色服装（删场景的），泳池/海边/浴室这类场景用场景服装
        # （删角色的）。一开始就把 clothing 权重打 0 的话，特殊场景也没衣服可换。
        scene_weights = dict(weights)
        for k in follow:
            if k == "clothing":
                continue
            scene_weights[k] = 0
        res = _generate_scene(tv, sel_key, sel_num, basis, head, rng, tag_cap, base_prob,
                              scene_weights, role_mode, role_name, role_works, quality_prefix,
                              artist_on, extra_body, negative_on, seed,
                              ext_subjects, ext_others, ext_rejected,
                              self_appear=("hair" in follow),
                              clothing_follow=("clothing" in follow),
                              scene_hint=scene_hint,
                              outfit_follow=outfit_follow,
                              char_outfit_id=char_outfit_id)
        if res:
            return res
        # 场景拼不出来（几乎不会发生）就退回自由随机，保证节点永远有输出
        return generate(level=sel_key, seed=seed, tag_cap=tag_cap, base_prob=base_prob,
                        slot_weights=slot_weights, role_mode=role_mode, role_name=role_name,
                        role_works=role_works, quality_prefix=quality_prefix,
                        artist_on=artist_on, extra_body=extra_body,
                        negative_on=negative_on, scene_mode="free",
                        role_prompt=", ".join(ext_kept), settings=settings,
                        appearance_follow=appearance_follow, outfit_follow=outfit_follow)

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

    # 主体：外部输入含主体词时替换默认主体（REQ-104 缺口 5）
    if ext_subjects:
        for t in ext_subjects:
            add("subject", {"en": t, "zh": "", "lv": 0})
    else:
        add("subject", {"en": "1girl", "zh": "一个女孩", "lv": 0})
        add("subject", {"en": "solo", "zh": "单人或单人特写", "lv": 0})
        if rng.random() < 0.55:
            for _ in range(6):
                t = rng.choice(_subjects(tv))
                if add("subject", t):
                    break

    # 角色：外部输入优先，其次内置词库（优先级 template_override > role_prompt > 词库）
    char = None
    role_from = "不指定"
    if ext_others:
        role_from = "外部输入"
        for t in ext_others:
            add("character", {"en": t, "zh": "", "lv": 0})
    else:
        char = pick_character(rng, role_mode, role_name, role_works)
        if char:
            role_from = "角色库"
            add("character", {"en": char["tag"], "zh": char.get("zh", ""), "lv": 0})
            for en in char_appearance(char):
                if tag_level(en) <= tv:
                    add("character", {"en": en, "zh": "", "lv": tag_level(en)})
            # 服装跟随角色：把角色那套塞进来，并把服装槽关掉
            if outfit_follow:
                outfit = [t for t in char_outfit(char, char_outfit_id)]
                if outfit:
                    for en in outfit:
                        add("character", {"en": en, "zh": "", "lv": tag_level(en)})
                    follow.update(["clothing", "accessory"])

    # 画师（可选）
    if artist_on:
        pool = drawable("artist", tv)
        if pool:
            add("artstyle", rng.choice(pool))

    # 其余槽位
    default_base = 0.65
    for s in SLOTS:
        if s["key"] in ("subject", "nsfw"):
            continue
        if s["key"] in follow:
            continue                      # 外观 / 服装已交给角色输入
        if s["key"] == "artstyle" and artist_on:
            continue                      # 画师已经占用这个位置
        w = _slot_weight(weights, s["key"])
        if w <= 0:
            continue
        p = min(1.0, max(0.0, s["prob"] * w * (float(base_prob) / default_base)))
        if s["need"] and rng.random() > p:
            continue
        pool = [t for c in s["cats"] for t in drawable(c, tv)]
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
    if multi_pose and not ext_subjects:
        chosen["subject"] = [{"en": "2girls", "zh": "两个女孩", "lv": 0}]
        seen.discard("1girl")
        seen.discard("solo")
        seen.add("2girls")
        duo = {"en": "duo", "zh": "双人构图", "lv": 0}
        chosen.setdefault("composition", []).append(duo)
        seen.add("duo")

    # 成人向：按目标档位定量，仍受同一套候选池闸门约束
    nsfw_n = NSFW_COUNT.get(tv, 0)
    if nsfw_n and _slot_weight(weights, "nsfw") <= 0:
        nsfw_n = 0                 # slot_weights 里 nsfw:0 = 真的关掉（以前写了不生效）
    if nsfw_n:
        pool = [t for s in SLOTS if s["key"] == "nsfw" for c in s["cats"] for t in drawable(c, tv)]
        pool = [t for t in pool if not NSFW_DENY.search(t["en"])]
        for _ in range(nsfw_n * 4):
            if len(chosen.get("nsfw", [])) >= nsfw_n or not pool:
                break
            add("nsfw", rng.choice(pool))

    # 全裸时清空服装：`completely nude` 和 `white nurse dress` 同时进正文，
    # 模型只能折中 —— 画一条布带"既算穿又算没穿"，这就是用户看到的胸前遮挡。
    # 保留袜子与配饰（only socks 配全裸是合法画风），其余服装一律删。
    #
    # ⚠️ `character` 槽也要清：角色节点/左侧连线喂进来的 role_prompt 里
    #    带着角色的整套服装（white shirt / skirt / school uniform），
    #    它们走的是 character 槽而不是 clothing 槽 ——
    #    只清 clothing 的话，全裸和这身水手服照样打架（v0.1.12 的漏口）。
    if any(_NUDE_RE.match(str(t.get("en") or "").strip())
           for t in chosen.get("nsfw", [])):
        for slot in ("clothing", "accessory", "character"):
            chosen[slot] = [t for t in chosen.get(slot, [])
                            if not _GARMENT.search(t["en"]) or _HOSIERY.search(t["en"])]
        # nsfw 槽里的「湿衣服 / 掀衣服」和全裸同样打架
        chosen["nsfw"] = [t for t in chosen.get("nsfw", [])
                          if not _CLOTH_STATE.search(t["en"])]

    # 评级词
    for r in RATING_TAGS.get(tv, []):
        add("rating", {"en": r, "zh": "", "lv": 0})

    # 拼装
    parts = []
    if str(quality_prefix or "").strip():
        parts.append(str(quality_prefix).strip().rstrip(","))
    for key in ASM_ORDER:
        for t in chosen.get(key, []):
            parts.append(t["en"])
    if str(extra_body or "").strip():
        parts.append(str(extra_body).strip())

    flat = _flatten(parts)
    cap = int(tag_cap) if int(tag_cap or 0) > 0 else _auto_cap(tv)
    flat = _trim_to_cap(flat, chosen, cap)

    positive = ", ".join(flat)
    negative = build_negative(tv, positive, negative_on)

    counts = {s["label"]: len(chosen.get(s["key"], [])) for s in SLOTS if chosen.get(s["key"])}
    if chosen.get("character"):
        counts["角色"] = len(chosen["character"])
    report_lines = list(head) + [
        f"标签: {len(flat)} 个（" + " / ".join(f"{k} {v}" for k, v in counts.items()) + "）",
        f"角色来源: {role_from}",
        f"种子: {seed}",
        f"负面: {len([x for x in negative.split(',') if x.strip()])} 个",
    ]
    return {
        "positive": positive,
        "negative": negative,
        "level": f"{sel_num if sel_num != 99 else 'any'} · {LEVEL_ZH.get(sel_key, '不限')}",
        "report": "\n".join(report_lines),
        "level_num": sel_num,
        "target_level": tv,
        "character": char,
        "picked": [{"slot": k, "en": t["en"], "lv": int(t.get("lv", 0))}
                   for k, items in chosen.items() for t in items],
    }


def _flatten(parts):
    flat = []
    for p in parts:
        for seg in str(p).split(","):
            seg = seg.strip()
            if seg and seg.lower() not in {x.lower() for x in flat}:
                flat.append(seg)
    return flat


# 超上限时的丢弃顺序：越靠前越先让位（都是"有它更好、没它也成"的槽位）
TRIM_ORDER = ["props", "weather", "composition", "camera", "accessory", "theme",
              "monster", "artstyle", "expression", "body", "lighting", "environment",
              "hair_color", "face", "hair", "eye_color", "pose", "clothing"]
# 这几个槽位绝不因为超上限被剪：剪掉它们会出现"选了极端档却没人任何成人词 / 没有评级词"
TRIM_KEEP = ("subject", "character", "nsfw", "rating")


def _trim_to_cap(flat, chosen, cap):
    """把整段压到 cap 以内，但保住评级词、成人向词、主体与角色。

    以前是 drop_order 之后直接 flat[:cap] 从尾部硬截，而 ASM_ORDER 末尾正好是
    monster -> nsfw -> rating，于是最先被切掉的就是最该留的那几个。
    现在的顺序是：保住必留项 -> 补质量前缀/手写补充 -> 还有空位就按
    "重要度从高到低"回填可选槽位（服装、姿势、发型优先，道具、天气最后）。
    """
    if cap <= 0 or len(flat) <= cap:
        return flat
    keep, drop = set(), set()
    for key in TRIM_KEEP:
        for t in chosen.get(key, []):
            keep.add(str(t.get("en", "")).strip().lower())
    for key in TRIM_ORDER:
        for t in chosen.get(key, []):
            drop.add(str(t.get("en", "")).strip().lower())

    out = [t for t in flat if t.strip().lower() in keep]
    spare = max(0, cap - len(out))

    # 1) 不在丢弃名单里的词（质量前缀、extra_body）先留着
    for t in flat:
        if spare <= 0:
            break
        k = t.strip().lower()
        if k in keep or k in drop:
            continue
        out.append(t)
        spare -= 1

    # 2) 还有空位就回填可选槽位：TRIM_ORDER 越靠后越重要，所以倒着补
    if spare > 0:
        have = {t.strip().lower() for t in out}
        for key in reversed(TRIM_ORDER):
            for t in chosen.get(key, []):
                if spare <= 0:
                    break
                en = str(t.get("en", "")).strip()
                k = en.lower()
                if not k or k in have:
                    continue
                if k not in {x.strip().lower() for x in flat}:
                    continue      # 已被 _flatten 去重掉的，不重复补
                out.append(en)
                have.add(k)
                spare -= 1

    order = {t.strip().lower(): i for i, t in enumerate(flat)}
    return sorted(out, key=lambda t: order.get(t.strip().lower(), 0))[:cap]


def _generate_mixed(sel_key, sel_num, tv, basis, head, override, rng, tag_cap, base_prob,
                    weights, role_mode, role_name, role_works, quality_prefix, artist_on,
                    extra_body, negative_on, scene_mode, seed, settings,
                    ext_kept, ext_rejected, follow, appearance_follow, outfit_follow):
    """混合模式：覆盖文本当锁定词条，其余槽位继续随机（REQ-102）。

    顺序策略（Q7 MVP）：锁定词保持原顺序在前，随机补充追加在后。
    角色词走正常角色槽（主体之后），既不重复也不丢失。
    """
    locked, seen = [], set()
    for seg in override.split(","):
        s = seg.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            locked.append(s)

    prefix = str(quality_prefix or "").strip().rstrip(",")
    prefix_n = len(_flatten([prefix])) if prefix else 0
    cap = int(tag_cap) if int(tag_cap or 0) > 0 else _auto_cap(tv)

    if len(locked) + prefix_n >= cap:
        out = ([prefix] if prefix else []) + locked
        positive = ", ".join(_flatten(out))
        negative = build_negative(tv, positive, negative_on)
        lines = list(head) + [
            "模式: 混合（覆盖词已达标签上限，未追加随机）",
            f"锁定词: {len(locked)} 个",
            f"角色来源: {'外部输入' if ext_kept else '不指定'}",
            f"种子: {seed}",
        ]
        return {"positive": positive, "negative": negative,
                "level": f"{sel_num if sel_num != 99 else 'any'} · {LEVEL_ZH.get(sel_key, '不限')}",
                "report": "\n".join(lines), "level_num": sel_num, "target_level": tv}

    remain = max(1, cap - len(locked) - prefix_n)
    # 内层不再抽样：直接把目标档位当选择档位传入，保证内外档位一致
    inner_cfg = dict(settings or {})
    inner_cfg["level_dist"] = False
    body = generate(level=TARGET_LEVELS[tv], seed=seed, tag_cap=remain, base_prob=base_prob,
                    slot_weights=json.dumps(weights) if weights else "",
                    role_mode=role_mode, role_name=role_name, role_works=role_works,
                    quality_prefix="", artist_on=artist_on, extra_body="",
                    negative_on=negative_on, scene_mode=scene_mode,
                    override_text="", override_mode="direct",
                    role_prompt=", ".join(ext_kept), settings=inner_cfg,
                    appearance_follow=appearance_follow, outfit_follow=outfit_follow,
                    scene_hint=override)

    body_tags = [x.strip() for x in str(body.get("positive", "")).split(",") if x.strip()]
    merged = list(locked)
    for t in body_tags:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        merged.append(t)
        if len(merged) + prefix_n >= cap:
            break

    out = ([prefix] if prefix else []) + merged
    if str(extra_body or "").strip():
        out.append(str(extra_body).strip())
    positive = ", ".join(_flatten(out))
    negative = build_negative(tv, positive, negative_on)

    lines = list(head) + [
        "模式: 混合（锁定词在前，其余槽位随机补充）",
        f"锁定词: {len(locked)} 个 · 随机补充: {max(0, len(merged) - len(locked))} 个",
        f"角色来源: {'外部输入' if ext_kept else ('词库' if body.get('character') else '不指定')}",
        f"种子: {seed}",
    ]
    return {"positive": positive, "negative": negative,
            "level": f"{sel_num if sel_num != 99 else 'any'} · {LEVEL_ZH.get(sel_key, '不限')}",
            "report": "\n".join(lines), "level_num": sel_num, "target_level": tv}


def _generate_scene(tv, sel_key, sel_num, basis, head, rng, tag_cap, base_prob, weights,
                    role_mode, role_name, role_works, quality_prefix, artist_on,
                    extra_body, negative_on, seed, ext_subjects=None, ext_others=None,
                    ext_rejected=0, self_appear=True, clothing_follow=False,
                    scene_hint="", outfit_follow=False, char_outfit_id=""):
    """场景成套路径：环境/季节/服装/道具/姿势绑在一个包里，出来的串自带现实逻辑。"""
    try:
        from . import scenes
    except ImportError:                     # 单独跑脚本时的兜底
        import scenes

    ext_subjects = ext_subjects or []
    ext_others = ext_others or []

    char = None if ext_others else pick_character(rng, role_mode, role_name, role_works)
    role_from = "外部输入" if ext_others else ("词库" if char else "不指定")
    monster_on = _slot_weight(weights, "monster") > 0 and rng.random() < 0.06

    # self_appear=False 表示用户关掉了「外观让位」：即使有角色也照抽外观
    has_character = (bool(ext_others) or bool(char)) and self_appear
    items, bundle_id = None, None
    # 场景包自带 7 条互斥校验，不合格就整包重抽。原来是 60 次：极端情况下
    # 单次排队会被这 60 轮完整构建拖住；12 次已经足够（再多就说明权重配置本身
    # 让这个场景包凑不出来，直接退回自由随机更快也更稳）。
    for _ in range(12):
        items, bundle_id = scenes.build(tv, rng, weights, base_prob,
                                        monster=monster_on,
                                        has_character=has_character,
                                        hint=scene_hint)
        if items:
            break
    if not items:
        return None

    # 角色：插在主体后面；官方外观按档位滤一遍
    char_tags = []
    if ext_others:
        char_tags = [(t, 0) for t in ext_others]
    elif char:
        char_tags.append((char["tag"], 0))
        for en in char_appearance(char):
            if scenes.level_of(en) <= tv:
                char_tags.append((en, scenes.level_of(en)))
        if outfit_follow:
            for en in char_outfit(char, char_outfit_id):
                if scenes.level_of(en) <= tv:
                    char_tags.append((en, scenes.level_of(en)))

    ordered = list(items)
    if ext_subjects:
        # 外部主体替代内置主体，位置仍在最前
        ordered = [(s, e) for s, e in ordered if s != "subject"]
        ordered = [("subject", t) for t in ext_subjects] + ordered

    # 场景与角色服装谁优先（用户 2026-11-17 定的规则）：
    #   · 普通场景 → 角色服装优先，删掉场景那套；
    #   · 泳池 / 海边 / 浴场 / 温泉这类 → 场景优先，删掉角色那套
    #     （穿常服站在泳池边在现实里不成立，模型也画不出合理的光影）。
    # 角色没带服装时不删场景的 —— 否则整段提示词一件衣服都没有。
    char_has_cloth = any(_GARMENT.search(en) and not _HOSIERY.search(en)
                         for en, _ in char_tags)
    if clothing_follow and char_has_cloth:
        if scenes.is_special_scene(bundle_id):
            char_tags = [(en, lv) for en, lv in char_tags
                         if not (_GARMENT.search(en) and not _HOSIERY.search(en))]
        else:
            ordered = [(s, e) for s, e in ordered if s != "clothing"]

    # 主体组在最前面，统一在第一个非 subject 之前插入角色
    first_non_subject = next((i for i, (s, _) in enumerate(ordered) if s != "subject"),
                             len(ordered))
    for i, (en, _) in enumerate(char_tags):
        ordered.insert(first_non_subject + i, ("character", en))

    # 全裸时把角色自带的那身衣服也清掉。
    # scenes.build 只清场景包自己的 clothing，管不到这里 —— 角色服装是场景拼完之后
    # 才插进来的，所以「completely nude + 水手服」会从这条路漏出去（用户 2026-11-17 报的就是它）。
    if any(_NUDE_RE.match(e) for _, e in ordered):
        ordered = [(s, e) for s, e in ordered
                   if not (s in ("clothing", "accessory", "character")
                           and _GARMENT.search(e) and not _HOSIERY.search(e))
                   and not (s == "nsfw" and _CLOTH_STATE.search(e))]

    chosen = {}
    for slot, en in ordered:
        chosen.setdefault(slot, []).append({"en": en, "lv": 0})

    # 画师（可选）
    if artist_on:
        pool = drawable("artist", tv)
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

    flat = _flatten(parts)
    cap = int(tag_cap) if int(tag_cap or 0) > 0 else _auto_cap(tv)
    flat = _trim_to_cap(flat, chosen, cap)

    positive = ", ".join(flat)
    negative = build_negative(tv, positive, negative_on)

    labels = {s["key"]: s["label"] for s in SLOTS}
    labels.update({"breast": "胸围", "season": "季节", "rating": "评级", "time": "时间",
                   "character": "角色", "composition": "构图", "theme": "题材"})
    counts = {}
    for slot, _ in ordered:
        lb = labels.get(slot, slot)
        counts[lb] = counts.get(lb, 0) + 1
    report_lines = list(head) + [
        f"场景: {bundle_id}（场景成套，环境/服装/道具/姿势同一套）",
        f"标签: {len(flat)} 个（" + " / ".join(f"{k} {v}" for k, v in counts.items()) + "）",
        f"角色来源: {role_from}",
        f"种子: {seed}",
        f"负面: {len([x for x in negative.split(',') if x.strip()])} 个",
    ]
    return {
        "positive": positive,
        "negative": negative,
        "level": f"{sel_num if sel_num != 99 else 'any'} · {LEVEL_ZH.get(sel_key, '不限')}",
        "report": "\n".join(report_lines),
        "level_num": sel_num,
        "target_level": tv,
        "character": char,
        "bundle": bundle_id,
        "picked": [{"slot": slot, "en": en, "lv": 0} for slot, en in ordered],
    }


def _neg_base():
    """负向前半段（固定 seed=0 洗过的那 26 条），算一次缓存。

    这张表跟档位、正向都无关，每张图重新 shuffle 一遍没有意义。
    """
    if "neg_base" in _CACHE:
        return _CACHE["neg_base"]
    rng = random.Random(0)
    neg = list(_CORE_NEG)
    pool = [t["en"] for t in drawable("negative", 99)
            if t["en"].lower() not in {x.lower() for x in neg}]
    rng.shuffle(pool)
    for en in pool:
        if len(neg) >= 26:
            break
        neg.append(en)
    _CACHE["neg_base"] = neg
    return neg


def build_negative(lv, positive, enabled=True):
    if not enabled:
        return ""
    neg = list(_neg_base())     # 拷贝：下面要按正向去重
    pos = {p.strip().lower() for p in positive.split(",")}
    neg = [n for n in neg if n.lower() not in pos]
    if lv >= 2:
        # 正向要成人内容时，负面里不能再压 nsfw / safe 一类词，否则互相打架
        neg = [n for n in neg if not re.search(r"\b(nsfw|safe|sensitive|rating|questionable)\b", n, re.I)]
    return ", ".join(neg)
