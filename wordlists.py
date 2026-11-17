# -*- coding: utf-8 -*-
"""词表统一入口：engine.py 与 scenes.py 共用同一份正则，避免两边各写一遍漂移。

词表本身放在 `data/garment_words.json`，用户可以直接改（改完重启生效）。
这里只负责读文件 + 编译 + 缓存。
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "data", "garment_words.json")

# 文件缺失时的兜底（保证插件不会因为少一个 json 就崩）
_FALLBACK = {
    "garment": (r"\b(skirt|dress|shirt|blouse|sweater|hoodie|jacket|coat|uniform|"
                r"jeans|pants|trousers|shorts|slacks|leggings|kimono|yukata|"
                r"robe|bathrobe|pajamas|nightgown|leotard|bodysuit|swimsuit|"
                r"bikini|lingerie|underwear|bra|panties|camisole|cardigan|vest|"
                r"apron|cloak|cape|armor|serafuku|necktie|bowtie|scarf|muffler|"
                r"clothes|outfit|\w*suit|\w*sleeves?|\w*coat|knitwear|swimwear|wear)\b"),
    "hosiery": (r"\b(socks|thighhighs|stockings|pantyhose|kneehighs|leg warmers)\b"),
    "nude": r"^(completely nude|fully nude|nude|naked|nude with accessories only)$",
    "nsfw_cloth": (r"\b(bikini|swimsuit|micro bikini|sling|string bikini|lingerie|"
                   r"underwear|panties|bra|pasties|see-through|transparent|topless|"
                   r"nude|naked|sideboob|underboob|swimwear|leotard|bodysuit|"
                   r"garter straps?|garter belt|micro skirt)\b"),
    # 吊带 / 绑带 / 挂脖 / 露肩族：擦边档正常，全年龄档不该有
    "strap_cloth": (r"\b(camisole|suspenders?|suspender skirt|straps?|halter|halter top|"
                    r"tube top|tank top|muscle shirt|sleeveless shirt|spaghetti|"
                    r"detached sleeves|spaghetti strap|chest strap|single strap|"
                    r"multiple straps|arm strap|cross-laced clothes|cross-laced|"
                    r"shoulder cutout|off shoulder|bare shoulders|sleeveless|"
                    r"strapless|backless|see-through)\b"),
    "appear": (r"\b(hair|eyes|eyebrows|eyelashes|skin|breasts?|chest|waist|hips|"
               r"thighs|figure|freckles|mole|horn|ears|tail|wings|halo)\b"),
    "cloth_state": (r"\b(wet clothes|clothes lift|clothing aside|open clothes|"
                    r"dress lift|shirt lift|skirt lift|undressing|panties aside|"
                    r"bra pull|clothes pull)\b"),
    "special_scene": r"pool|beach|onsen|bath|shower|swim|sea_|ocean|lake|river|water",
    "not_special_scene": ["aquarium_day"],
}

_DATA = None


def _load():
    global _DATA
    if _DATA is None:
        try:
            with open(_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 兜底表先铺底，再用文件里的值覆盖；文件里新增的键（以后加词表）
            # 也要一起收进来，否则只在 json 里加键等于没加。
            data = dict(_FALLBACK)
            for k, v in raw.items():
                if k.startswith("_"):
                    continue
                if v:
                    data[k] = v
        except Exception:
            data = dict(_FALLBACK)
        _DATA = data
    return _DATA


def pattern(key):
    return _load().get(key) or _FALLBACK[key]


def regex(key, flags=re.I):
    """按名取编译好的正则（同一次进程内只编译一次）。

    值可以是正则字符串，也可以是字符串列表（列表会被拼成 ^(a|b|c)$）。
    """
    cache_key = "_re_" + key
    data = _load()
    if cache_key not in data:
        raw = data.get(key)
        if isinstance(raw, list):
            pat = "^(" + "|".join(re.escape(str(x)) for x in raw) + ")$"
        else:
            pat = str(raw or _FALLBACK[key])
        data[cache_key] = re.compile(pat, flags)
    return data[cache_key]


def words(key):
    """取列表型配置（目前只有 not_special_scene）。"""
    v = _load().get(key)
    if isinstance(v, list):
        return set(str(x) for x in v)
    return set()


def reload():
    """开发/调试用：丢掉缓存，下次重新读文件。"""
    global _DATA
    _DATA = None
