# -*- coding: utf-8 -*-
"""角色库状态持久化：收藏 / 排除名单 / 权重 / 面板选中集 / 自定义角色。

设计口径：
  · 状态文件在插件目录 userdata/ 下，前端传不了路径；
  · 写入走「临时文件 + 原子 rename」，两个标签页同时写不会截断文件；
  · 读失败一律回落空状态，绝不因为一个坏文件让节点报错。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(HERE, "userdata")
STATE_PATH = os.path.join(USER_DIR, "state.json")
CUSTOM_PATH = os.path.join(USER_DIR, "custom_characters.json")
CUSTOM_THUMB_DIR = os.path.join(HERE, "custom_thumbs")

LIST_KEYS = ("favorites", "excluded", "picked", "recent")


def _default_state():
    return {
        "favorites": [],
        "excluded": [],
        "picked": [],
        "recent": [],
        "weights": {},
        "settings": {"zh": True, "batch": 60},
    }


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def normalize_state(raw):
    st = _default_state()
    if not isinstance(raw, dict):
        return st
    for k in LIST_KEYS:
        v = raw.get(k)
        if isinstance(v, list):
            st[k] = [str(x) for x in v if str(x).strip()][:5000]
    w = raw.get("weights")
    if isinstance(w, dict):
        for k, v in list(w.items())[:5000]:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if 0 < fv <= 20:
                st["weights"][str(k)] = round(fv, 3)
    s = raw.get("settings")
    if isinstance(s, dict):
        st["settings"]["zh"] = bool(s.get("zh", True))
        try:
            st["settings"]["batch"] = max(20, min(400, int(s.get("batch", 60))))
        except (TypeError, ValueError):
            pass
    return st


def load_state():
    return normalize_state(_read(STATE_PATH, {}))


def save_state(raw):
    st = normalize_state(raw)
    try:
        _atomic_write(STATE_PATH, st)
    except Exception as exc:
        return False, f"写入失败: {exc}"
    return True, None


def load_custom():
    """自定义角色：结构同 characters.json 的条目，按 tag 覆盖内置。"""
    d = _read(CUSTOM_PATH, {})
    items = d.get("characters") if isinstance(d, dict) else d
    if not isinstance(items, list):
        return []
    out = []
    for c in items:
        if not isinstance(c, dict) or not str(c.get("tag") or "").strip():
            continue
        c = dict(c)
        c["tag"] = str(c["tag"]).strip().lower()
        c["custom"] = True
        c.setdefault("appearance", {})
        c.setdefault("outfits", [])
        c.setdefault("works", [])
        out.append(c)
    return out


def save_custom(items):
    try:
        _atomic_write(CUSTOM_PATH, {"characters": items})
    except Exception as exc:
        return False, f"写入失败: {exc}"
    return True, None


def upsert_custom(rec):
    items = load_custom()
    tag = str(rec.get("tag") or "").strip().lower()
    if not tag:
        return False, "角色 tag 不能为空"
    rec = dict(rec)
    rec["tag"] = tag
    rec["custom"] = True
    for i, c in enumerate(items):
        if c["tag"] == tag:
            items[i] = rec
            break
    else:
        items.append(rec)
    return save_custom(items)


def delete_custom(tag):
    tag = str(tag or "").strip().lower()
    items = load_custom()
    keep = [c for c in items if c["tag"] != tag]
    if len(keep) == len(items):
        return False, "这是内置角色，只能恢复不能删除"
    return save_custom(keep)


def custom_thumb_path(tag):
    """自定义缩略图路径：必须落在 custom_thumbs 内，杜绝路径穿越。"""
    safe = "".join(ch for ch in str(tag or "").lower() if ch.isalnum() or ch in "_-")
    if not safe:
        return None
    return os.path.join(CUSTOM_THUMB_DIR, safe + ".webp")
