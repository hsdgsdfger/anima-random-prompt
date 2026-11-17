# -*- coding: utf-8 -*-
"""场景成套拼装：把模板那套「场景包」逻辑搬进节点。

数据来自 data/scenes.json（tools/export_scenes.py 从模板生成器导出）：
环境 / 季节 / 天气 / 时间 / 光线 / 服装 / 鞋 / 配饰 / 道具 / 姿势 / 成人向
全部绑在同一个场景里，所以拼出来的串自带现实逻辑。
"""
import json
import os
import re

try:
    from .wordlists import regex as _wl_re, words as _wl_words
except ImportError:
    from wordlists import regex as _wl_re, words as _wl_words

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_SC = None
_LV = None
_CATS = None

MALE = re.compile(
    r"\b(1boy|2boys|boys?|male|males|man|men|penis|testicles|incubus|futanari|beard)\b", re.I)
SWIM = re.compile(
    r"\b(bikini|swimsuit|swim shorts|one-piece swimsuit|competition swimsuit|"
    r"micro bikini|racing swimsuit|school swimsuit)\b", re.I)
WINTER = re.compile(
    r"\b(winter coat|parka|duffle coat|fur coat|beanie|snow boots|ear muffs)\b", re.I)
RAIN = re.compile(r"\b(rain|light rain|rainy day|storm|raindrops)\b", re.I)

# 全裸与服装互斥：模型同时看到"全裸"和"护士服"只会画一条布带折中
GARMENT = _wl_re("garment")
HOSIERY = _wl_re("hosiery")
NUDE_RE = _wl_re("nude")
CLOTH_STATE = _wl_re("cloth_state")

# 构图里这些是"整张图结构词"，单条提示词里不能混
COMP_SKIP = ("solo", "duo", "group", "multiple views", "character sheet",
             "reference sheet", "comic panel", "split screen", "collage layout", "scenery")

CORE = ("hair", "hair_color", "face", "eye_color", "body", "clothing", "accessory",
        "pose", "expression", "camera", "composition", "environment", "time",
        "lighting", "props", "artstyle", "theme")

# 现实中必须换装的场景：泳池 / 海边 / 浴场 / 温泉 / 淋浴。
# 这类场景穿常服在画面上不成立，所以服装由场景决定，角色自带的那套让位。
SPECIAL_SCENE = _wl_re("special_scene")

# 数据里 water=True 但实际穿常服的场景：水族馆是「参观」，不是下水
NOT_SPECIAL = _wl_words("not_special_scene")


# ---------------- 锁定词与场景的一致性 ----------------
# 混合模式下用户写的锁定词（"cherry blossoms, spring"）和随机抽到的场景
# 可能矛盾（抽到温泉）。这里不硬性拒绝，只做「优先挑不冲突的」——
# 过滤后为空就退回全集，保证一定有输出。
_HINT_WINTER = re.compile(r"\b(snow|snowing|snowy|winter|blizzard|ice|frozen)\b", re.I)
_HINT_SPRING = re.compile(r"\b(cherry blossoms?|sakura|spring|hanami|flower field)\b", re.I)
_HINT_WATER = re.compile(r"\b(beach|ocean|sea|pool|swimsuit|bikini|underwater|"
                        r"waves|seaside|shore)\b", re.I)
_HINT_INDOOR = re.compile(r"\b(indoor|bedroom|classroom|kitchen|bathroom|library|"
                          r"cafe|office|room)\b", re.I)


def hint_conflict(bundle, hint):
    """锁定词主张的环境和这个场景包是否明显打架。"""
    if not hint:
        return False
    env = " ".join(bundle.get("env") or [])
    season = " ".join(bundle.get("season") or [])
    blob = (env + " " + season).lower()
    if _HINT_WINTER.search(hint):
        # 要雪景却给了夏天/海边
        if not bundle.get("cold") and not _HINT_WINTER.search(blob):
            return True
    if _HINT_SPRING.search(hint):
        if bundle.get("cold") or _HINT_WINTER.search(blob):
            return True
    if _HINT_WATER.search(hint):
        if not bundle.get("water"):
            return True
    if _HINT_INDOOR.search(hint) and not bundle.get("indoor"):
        return True
    return False


_SPECIAL_CACHE = {}


def is_special_scene(bundle_id):
    """该场景是否属于「必须换装」的场景（服装由场景优先）。结果缓存，每轮都要调。"""
    key = str(bundle_id or "")
    if key in _SPECIAL_CACHE:
        return _SPECIAL_CACHE[key]
    if key in NOT_SPECIAL:
        _SPECIAL_CACHE[key] = False
        return False
    sc, _, _ = _load()
    b = next((x for x in sc["bundles"] if x["id"] == bundle_id), None)
    # 优先读数据标记：加新场景只要在 scenes.json 里写 needs_outfit，
    # 不用回来改正则（aquarium_day 那次误判就是猜出来的）。
    if b is not None and "needs_outfit" in b:
        val = bool(b["needs_outfit"])
    else:
        val = (bool(b.get("water")) or bool(SPECIAL_SCENE.search(key))) if b \
            else bool(SPECIAL_SCENE.search(key))
    _SPECIAL_CACHE[key] = val
    return val


def _load():
    global _SC, _LV, _CATS
    if _SC is None:
        with open(os.path.join(_DIR, "scenes.json"), encoding="utf-8") as f:
            _SC = json.load(f)
        with open(os.path.join(_DIR, "tags.json"), encoding="utf-8") as f:
            raw = json.load(f)
        lv, cats = {}, {}
        for c in raw["cats"]:
            cats[c["id"]] = [t for t in c["tags"] if not t.get("meta")]
            for t in c["tags"]:
                k = t["en"].lower()
                # 同名标签跨分类只认「排在前面的那个分类」。tags.json 里
                # clothing / body / pose 都在 nsfwbody / nsfwcloth 之前，所以
                # bikini 取 clothing 的档位，不会像以前那样被 min() 拉成 0
                # ——「sfw 抽出比基尼」就是这条 min 造成的（用户 2026-11-17 报）。
                lv.setdefault(k, int(t["lv"]))
        _LV, _CATS = lv, cats
    return _SC, _LV, _CATS


def level_of(en):
    _load()
    return _LV.get(str(en).lower(), 0)


class _Builder:
    def __init__(self, rng, cap, weights, base_prob):
        self.rng = rng
        self.cap = 99 if int(cap) >= 99 else int(cap)
        self.w = weights or {}
        try:
            self.scale = max(0.0, float(base_prob) / 0.65)
        except Exception:
            self.scale = 1.0
        self.items = []
        self.used = set()

    def weight(self, key, default=1.0):
        try:
            return float(self.w.get(key, default))
        except Exception:
            return default

    def on(self, key):
        return self.weight(key) > 0

    def pick(self, items, key=None):
        cand = [i for i in items if level_of(i) <= self.cap]
        if key is not None:
            cand = [i for i in cand if i.lower() not in {k.lower() for k in key}]
        return self.rng.choice(cand) if cand else None

    def add(self, slot, en):
        if not en:
            return False
        if slot in ("hair", "hair_color", "face", "eye_color", "body", "breast",
                    "clothing", "accessory", "pose", "expression", "camera",
                    "environment", "time", "lighting", "props", "artstyle", "theme",
                    "weather", "season", "composition") \
                and not self.on(slot):
            return False          # 权重 0 / 关槽位
        low = en.lower()
        if low in self.used or MALE.search(en):
            return False
        self.used.add(low)
        self.items.append((slot, en))
        return True

    def chance(self, p):
        return self.rng.random() < min(1.0, max(0.0, p * self.scale))

    def cat(self, name):
        _load()
        return [t["en"] for t in _CATS.get(name, []) if int(t["lv"]) <= self.cap]


def build(cap, rng, weights=None, base_prob=0.65, monster=False, has_character=False,
          hint=""):
    """拼一套；不合规返回 (None, None)，由调用方重试。

    `hint` 是锁定词原文：给了就优先挑不与之矛盾的场景包（挑不到就退回全集）。
    """
    sc, _, _ = _load()
    cap = 99 if int(cap) >= 99 else int(cap)
    bundles = [b for b in sc["bundles"]
               if cap <= 1 or (b["nsfw"] and (b["nsfw"].get(str(min(cap, 4))
                                ) or b["nsfw"].get("4")))]
    if monster:
        bundles = [b for b in bundles if b["id"] in sc["monster_bundles"]]
    if hint:
        keep = [b for b in bundles if not hint_conflict(b, hint)]
        if keep and len(keep) < len(bundles):
            bundles = keep          # 有更贴的候选就先缩小范围，但不强求
    if not bundles:
        return None, None

    b = _Builder(rng, cap, weights, base_prob)
    bundle = rng.choice(bundles)
    multi_ok = bundle["id"] in sc["multi_bundles"]

    # 主体 / 多人（多人 = 动作 + 身体姿态两条）
    posture = {"lying", "sitting", "standing", "kneeling", "sitting on bed",
               "sitting on chair", "sitting on floor", "on back", "on stomach", "on side"}
    pose = b.pick(bundle["poses"])
    action = None
    if multi_ok and rng.random() < 0.22:
        action = b.pick(sc["multi_pose"])
        if action:
            allowed = set(sc.get("action_posture", {}).get(action, posture))
            pose = (b.pick([p for p in bundle["poses"] if p in allowed])
                    or b.pick(sorted(allowed)) or pose)
    if action:
        b.add("subject", "2girls")
        b.add("composition", "duo")
    else:
        b.add("subject", "1girl")
        b.add("subject", "solo")

    # 外观（指定角色时交给角色自带外观，避免两套外观打架）
    if not has_character:
        short = ["bob cut", "pixie cut", "short twintails", "blunt bangs", "bangs"]
        long_ = [s for s in sc["hair_style"] if s not in short]
        length = b.pick(sc["hair_len"]) if rng.random() < 0.85 else None
        pool = (short + ["bangs", "sidelocks"]
                if length in ("short hair", "chin-length hair") else long_)
        style = b.pick(pool) if rng.random() < 0.8 else None
        if not length and not style:
            style = b.pick(sc["hair_style"])
        b.add("hair", length)
        b.add("hair", style)
        b.add("hair_color", b.pick(sc["hair_color"]))
        b.add("face", b.pick(sc["face_detail"]))
        b.add("eye_color", b.pick(sc["eye_color"]))
        body = b.pick(sc["body"])
        b.add("body", body)
        if body:
            b.add("breast", b.pick(sc["breast_matrix"].get(body, [])))

    # 服装：大件不叠穿
    full = set(sc["full_garment"])
    first = b.pick(bundle["cloth"])
    b.add("clothing", first)
    if b.chance(0.55):
        second = b.pick([c for c in bundle["cloth"]
                         if not (first in full and c in full)], key=b.used)
        b.add("clothing", second)
    b.add("clothing", b.pick(bundle["shoes"]))

    if b.on("accessory"):
        b.add("accessory", b.pick(bundle["acc"], key=b.used) or b.pick(bundle["acc"]))
    b.add("pose", pose)
    b.add("pose", action)
    b.add("expression", b.pick(b.cat("expression")))
    b.add("camera", b.pick(b.cat("camera")))
    comp_pool = [c for c in b.cat("composition") if c not in COMP_SKIP]
    b.add("composition", b.pick(comp_pool))

    b.add("environment", b.pick(bundle["env"]))
    for s in bundle["season"][:1]:
        b.add("season", s)
    if not bundle["season"]:
        b.add("season", b.pick(["spring", "summer", "autumn", "winter"]))
    if bundle["weather"]:
        b.add("weather", b.pick(bundle["weather"], key=b.used) or b.pick(bundle["weather"]))
    t = b.pick(bundle["time"], key=b.used) or b.pick(bundle["time"])
    # 场景名里带的时间词要自洽（bathroom_morning 不该配 night）
    hint = bundle["id"]
    if hint.endswith("_night"):
        t = b.pick(["night"], key=b.used) or b.pick(["night"]) or t
    elif hint.endswith("_morning"):
        t = b.pick(["morning", "dawn"], key=b.used) or b.pick(["morning", "dawn"]) or t
    elif hint.endswith("_sunset"):
        t = b.pick(["sunset", "dusk"], key=b.used) or b.pick(["sunset", "dusk"]) or t
    elif hint.endswith("_day"):
        t = b.pick(["day", "afternoon", "morning"], key=b.used) or t
    b.add("time", t)
    b.add("lighting", b.pick(bundle["light"], key=b.used) or b.pick(bundle["light"]))

    props = None
    for _ in range(6):
        props = b.pick(bundle["props"], key=b.used)
        if props:
            break
    b.add("props", props or b.pick(bundle["props"]))
    if b.chance(0.4):
        b.add("props", b.pick(bundle["props"], key=b.used))
    b.add("artstyle", b.pick(sc["style"], key=b.used) or b.pick(sc["style"]))
    b.add("theme", b.pick(sc["theme"], key=b.used) or b.pick(sc["theme"]))

    if monster and bundle["id"] in sc["monster_bundles"] and b.chance(0.5):
        b.add("monster", rng.choice(sc["monster_tags"]))

    # 成人向：数量按档位，且要求服装对得上
    n = sc["nsfw_count"].get(str(cap), 2) if cap != 99 else 2
    n = int(n)
    if n and b.weight("nsfw") <= 0:
        n = 0                  # slot_weights 里 nsfw:0 = 真的关掉成人向
    if n:
        key = str(cap if cap < 5 else 4)
        offer = sc.get("nsfw_offer", {}).get(bundle["id"], {})
        cand = list(offer.get(key, []) or bundle["nsfw"].get(key, []))
        cloth_text = " ".join(e for s, e in b.items if s == "clothing").lower()
        prereq = sc["nsfw_prereq"]
        solo_deny = set(sc.get("solo_nsfw_deny", []))
        posereq = sc.get("posereq", {})
        pose_tags = {pose} | ({action} if action else set())
        is_multi = bool(action)
        pair = set(sc.get("pair_nsfw", []))
        if is_multi:
            cand = cand + [t for t in pair if level_of(t) <= cap]
        deny = solo_deny - (pair if is_multi else set())
        cand = [t for t in cand
                if (t not in prereq or any(k in cloth_text for k in prereq[t]))
                and t not in deny
                and (t not in posereq or bool(set(posereq[t]) & pose_tags))]
        # 兜底：和服装撞了就换通用词
        have = sum(1 for s, _ in b.items if s == "nsfw")
        for t in rng.sample(cand, min(n, len(cand))) if cand else []:
            if b.add("nsfw", t):
                have += 1
        for t in ["cleavage", "sideboob", "thigh gap", "open clothes",
                  "underwear only", "no bra", "topless", "on bed"]:
            if have >= n:
                break
            if level_of(t) <= cap and t not in solo_deny \
                    and (t not in posereq or bool(set(posereq[t]) & pose_tags)) \
                    and b.add("nsfw", t):
                have += 1
        # 全裸就别再叠"掀衣服"
        if any(NUDE_RE.match(e) for _, e in b.items):
            clash = {"shirt lift", "skirt lift", "dress lift", "open clothes",
                     "clothing aside", "up skirt", "bra pull", "clothes lift",
                     "underwear only", "topless", "bottomless", "naked towel"}
            b.items = [(s, e) for s, e in b.items
                       if e not in clash and not CLOTH_STATE.search(e)]
            # 全裸时连衣服一起删：`completely nude` 与 `white nurse dress` 并存
            # 会让模型折中画一条布带（用户 2026-11-17 报的「胸前总被挡住」）。
            # 袜子与配饰保留 —— `only socks` 配全裸是合法画风。
            b.items = [(s, e) for s, e in b.items
                       if not (s in ("clothing", "accessory")
                               and GARMENT.search(e) and not HOSIERY.search(e))]
        # 去冲突后可能少了一条，用不带服装动作的通用词补回来
        have = sum(1 for s, _ in b.items if s == "nsfw")
        for t in ["cleavage", "sideboob", "thigh gap", "presenting", "arched back",
                  "sweat on body", "aroused", "panting"]:
            if have >= n:
                break
            if level_of(t) <= cap and t not in solo_deny \
                    and (t not in posereq or bool(set(posereq[t]) & pose_tags)) \
                    and b.add("nsfw", t):
                have += 1
    rating = {0: ["safe"], 1: ["sensitive"], 2: ["nsfw"], 3: ["nsfw", "explicit"],
              4: ["nsfw", "explicit"]}.get(cap, [])
    for r in rating:
        b.add("rating", r)

    items = b.items

    # 逻辑校验（不合规就重抽）
    text = ", ".join(en for _, en in items)
    if MALE.search(text):
        return None, None
    tagged = {en for _, en in items}
    if SWIM.search(text) and not bundle["water"]:
        return None, None
    if WINTER.search(text) and not bundle["cold"]:
        return None, None
    if RAIN.search(text) and bundle["indoor"]:
        return None, None
    if "night" in tagged and "sunny" in tagged:
        return None, None
    if cap <= 1 and any(s == "nsfw" for s, _ in items):
        return None, None
    for key in CORE:
        # 有角色时外观交给角色自带标签，这些槽位本来就该是空的（否则一定误判打架）
        if has_character and key in ("hair", "hair_color", "face", "eye_color", "body"):
            continue
        if b.on(key) and not any(s == key for s, _ in items):
            return None, None
    return items, bundle["id"]
