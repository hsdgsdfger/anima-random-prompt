# -*- coding: utf-8 -*-
"""Prompt Forge 全局配置：userdata/prompt_forge.json 的读写、校验与版本号。

设计口径（对应 REQ-103 / REQ-108 / REQ-109）：
  · 文件在插件目录内，服务端固定路径，绝不接受客户端传路径；
  · 写入用「临时文件 + 原子 rename」，并发写最多后写覆盖先写，不会损坏；
  · 解析结果按 (mtime_ns, size) 缓存，避免每次排队都重新解析 JSON；
  · config_version = SHA1(规范化 settings)，只覆盖 settings 段，收藏变化不参与；
  · 文件缺失或损坏时回落到内置默认，config_version = "default"。

只依赖标准库；不反向 import engine，避免循环导入。
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
USERDATA_DIR = os.path.join(HERE, "userdata")
USERDATA_PATH = os.path.join(USERDATA_DIR, "prompt_forge.json")

LEVEL_ORDER = ["sfw", "suggestive", "explicit", "hardcore", "extreme"]

DEFAULT_LEVEL_MATRIX = {
    "sfw": {"sfw": 1.0},
    "suggestive": {"suggestive": 0.5, "sfw": 0.5},
    "explicit": {"explicit": 0.5, "sfw": 0.25, "suggestive": 0.25},
    "hardcore": {"hardcore": 0.5, "sfw": 0.1667, "suggestive": 0.1667, "explicit": 0.1666},
    "extreme": {"extreme": 0.5, "sfw": 0.125, "suggestive": 0.125,
                "explicit": 0.125, "hardcore": 0.125},
}
DEFAULT_ANY_WEIGHTS = {"sfw": 0.7, "suggestive": 0.075, "explicit": 0.075,
                       "hardcore": 0.075, "extreme": 0.075}

FAVORITE_KEYS = ("tags", "templates", "recent", "zh")


def default_settings():
    return {
        "level_dist": False,
        "level_matrix": {k: dict(v) for k, v in DEFAULT_LEVEL_MATRIX.items()},
        "any_weights": dict(DEFAULT_ANY_WEIGHTS),
        "auto_popup": True,
    }


def empty_favorites():
    return {"tags": [], "templates": [], "recent": [], "zh": True}


def empty_userdata():
    return {"favorites": empty_favorites(), "settings": default_settings()}


def _num(v):
    """把任意值转成 0~1 的非负浮点；非法值当 0。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):   # NaN / inf
        return 0.0
    return max(0.0, min(1.0, f))


def _check_weights(d, keys, label, upper=None):
    """校验一组「档位 -> 权重」：键必须在 keys 内，值 0~1，和 > 0。

    upper 给定时，键在 keys 中的序号不得大于 upper（保证「不超过该档」）。
    """
    if not isinstance(d, dict) or not d:
        return None, f"{label}缺失或不是对象"
    out = {}
    total = 0.0
    for k, v in d.items():
        if k not in keys:
            return None, f"{label}含未知档位 {k}"
        if upper is not None and keys.index(k) > upper:
            return None, "该配置违反不超过该档"
        out[k] = _num(v)
        total += out[k]
    if total <= 0:
        return None, f"{label}权重全为 0"
    return out, None


def normalize_settings(raw):
    """校验并规范化 settings；返回 (settings, error)。error 非 None 时不可写入。"""
    if raw is None:
        return default_settings(), None
    if not isinstance(raw, dict):
        return None, "settings 必须是对象"

    matrix_raw = raw.get("level_matrix")
    matrix = {}
    if matrix_raw is None:
        matrix = {k: dict(v) for k, v in DEFAULT_LEVEL_MATRIX.items()}
    else:
        if not isinstance(matrix_raw, dict):
            return None, "level_matrix 必须是对象"
        for row_key in LEVEL_ORDER:
            if row_key not in matrix_raw:
                return None, f"level_matrix 缺行 {row_key}"
            row, err = _check_weights(matrix_raw[row_key], LEVEL_ORDER,
                                      f"level_matrix.{row_key}",
                                      upper=LEVEL_ORDER.index(row_key))
            if err:
                return None, err
            matrix[row_key] = row

    any_raw = raw.get("any_weights")
    if any_raw is None:
        any_w = dict(DEFAULT_ANY_WEIGHTS)
    else:
        any_w, err = _check_weights(any_raw, LEVEL_ORDER, "any_weights")
        if err:
            return None, err

    return {
        "level_dist": bool(raw.get("level_dist", False)),
        "level_matrix": matrix,
        "any_weights": any_w,
        "auto_popup": bool(raw.get("auto_popup", True)),
    }, None


def _canonical(settings):
    return json.dumps(settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_version(settings):
    return hashlib.sha1(_canonical(settings).encode("utf-8")).hexdigest()


# (mtime_ns, size) -> 解析结果；键不变就复用，避免每次排队都读盘解析
_CACHE = {"key": None, "favorites": None, "settings": None, "version": "default"}


def _file_key():
    try:
        st = os.stat(USERDATA_PATH)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _load():
    key = _file_key()
    if key is not None and _CACHE["key"] == key:
        return _CACHE

    fav = empty_favorites()
    settings = default_settings()
    version = "default"

    if key is not None:
        try:
            with open(USERDATA_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            settings, err = normalize_settings(raw.get("settings"))
            if err:
                settings = default_settings()
                version = "default"
            else:
                version = config_version(settings)
            f_raw = raw.get("favorites")
            if isinstance(f_raw, dict):
                for k in FAVORITE_KEYS:
                    if k == "zh":
                        fav["zh"] = bool(f_raw.get("zh", True))
                    elif isinstance(f_raw.get(k), list):
                        fav[k] = [str(x) for x in f_raw[k]]
            else:
                # 只有 settings 段的文件也算正常，但 config_version 已由 settings 决定
                pass
        except Exception:
            fav = empty_favorites()
            settings = default_settings()
            version = "default"

    _CACHE.update({"key": key, "favorites": fav, "settings": settings,
                   "version": version})
    return _CACHE


def snapshot():
    """返回 (settings, config_version) 的同一份快照；IS_CHANGED 与 run 共用。"""
    c = _load()
    return c["settings"], c["version"]


def read_userdata():
    c = _load()
    return {"favorites": dict(c["favorites"]), "settings": c["settings"]}


def _atomic_write(data):
    os.makedirs(USERDATA_DIR, exist_ok=True)
    tmp = USERDATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, USERDATA_PATH)


def write_userdata(payload):
    """整体覆盖写入；返回 (ok, error)。键名白名单 + 结构校验。"""
    if not isinstance(payload, dict):
        return False, "请求体必须是对象"
    for k in payload:
        if k not in ("favorites", "settings"):
            return False, f"不接受的键 {k}"

    fav_raw = payload.get("favorites")
    if fav_raw is None:
        fav_raw = empty_favorites()
    if not isinstance(fav_raw, dict):
        return False, "favorites 必须是对象"
    fav = {}
    for k in FAVORITE_KEYS:
        v = fav_raw.get(k)
        if k == "zh":
            fav["zh"] = bool(v) if isinstance(v, bool) else True
        elif isinstance(v, list):
            fav[k] = [str(x) for x in v]
        elif v is None:
            fav[k] = []
        else:
            return False, f"favorites.{k} 必须是数组"

    settings, err = normalize_settings(payload.get("settings"))
    if err:
        return False, err

    try:
        _atomic_write({"favorites": fav, "settings": settings})
    except Exception as exc:
        return False, f"写入失败: {exc}"

    _CACHE["key"] = None          # 强制下次重读
    return True, None
