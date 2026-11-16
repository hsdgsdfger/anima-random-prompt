# -*- coding: utf-8 -*-
"""Comfyui-Prompt-Forge —— 独立的自定义节点，不依赖也不修改 Anima Wardrobe V6。

节点：PromptForge Random（随机生成一整段提示词，带档位 / 种子 / 槽位权重）
"""
import hashlib
import time

from .engine import (LEVEL_CHOICES, LEVEL_ZH, LEVEL_NUM, generate,
                     load_data, tag_level)

__version__ = "0.11.17"
SECTION_NAME = "AnimaDecouple/Prompt Forge"

_LEVEL_WITH_ZH = [f"{k} · {LEVEL_ZH[k]}" if k != "any" else "any · 不限" for k in LEVEL_CHOICES]
_KEY_OF_LABEL = {label: key for key, label in zip(LEVEL_CHOICES, _LEVEL_WITH_ZH)}
_ROLE_LABELS = ["不指定", "随机", "指定"]
_ROLE_KEYS = {"不指定": "none", "随机": "random", "指定": "specified"}
_SCENE_LABELS = ["场景成套 · 现实逻辑", "自由随机 · 全库乱抽"]
_SCENE_KEYS = {_SCENE_LABELS[0]: "scene", _SCENE_LABELS[1]: "free", "scene": "scene", "free": "free"}


class PromptForgeRandom:
    """按档位从 Forge 词库里随机拼一整段提示词（正向 + 负面 + 档位报告）。"""

    @classmethod
    def INPUT_TYPES(cls):
        # ⚠️ 控件顺序一旦发布就是契约：以后新增一律追加到末尾，
        #    否则已存盘工作流的 widgets_values 会整体错位。
        return {
            "required": {
                "level": (_LEVEL_WITH_ZH, {"default": _LEVEL_WITH_ZH[0],
                                           "tooltip": "档位：数值越大越露骨；any = 不设限"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647,
                                 "tooltip": "-1 = 每次运行重抽；>=0 = 可复现"}),
                "tag_cap": ("INT", {"default": 0, "min": 0, "max": 80, "step": 1,
                                    "tooltip": "总标签上限；0 = 自动（全年龄 26 / 成人 30）"}),
                "base_prob": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.05,
                                        "tooltip": "可选槽位的基准出现概率，1.0 = 各槽位都必出"}),
                "slot_weights": ("STRING", {"default": "",
                                            "multiline": False,
                                            "tooltip": '按槽位加权，JSON：{"clothing":1.5,"props":0}；0 = 关掉该槽位'}),
                "role_mode": (_ROLE_LABELS, {"default": "不指定"}),
                "role_name": ("STRING", {"default": "", "multiline": False,
                                         "tooltip": "role_mode=指定 时填角色名 / 中文名 / danbooru tag 片段"}),
                "role_works": ("STRING", {"default": "", "multiline": False,
                                          "tooltip": "按作品限定随机角色，可用 | 分隔，如 葬送的芙莉莲|原神"}),
                "quality_prefix": ("STRING", {"default": "masterpiece, best quality", "multiline": False}),
                "artist_on": ("BOOLEAN", {"default": False, "tooltip": "是否随机带一个画师标签"}),
                "negative_on": ("BOOLEAN", {"default": True, "tooltip": "是否同时输出负面提示词"}),
                "extra_body": ("STRING", {"default": "", "multiline": True,
                                          "tooltip": "手写补充，会拼在正向末尾"}),
            },
            "optional": {
                "quality_on": ("BOOLEAN", {"default": True, "tooltip": "是否加质量前缀"}),
                "scene_mode": (_SCENE_LABELS, {"default": _SCENE_LABELS[0],
                                               "tooltip": "场景成套 = 环境/服装/道具绑在一个场景里，出词讲究现实逻辑；自由随机 = 全库各抽各的（组合更多但容易矛盾）"}),
                "template_override": ("STRING", {"default": "", "multiline": True,
                                                 "tooltip": "面板里点“套用”会自动填这里；非空时直接用它当正向提示词（不再随机）"}),
                "random_each_run": ("BOOLEAN", {"default": True,
                                                "tooltip": "每次运行都重新随机：勾上后忽略固定种子，每跑一次换一份"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive", "negative", "level", "report")
    FUNCTION = "run"
    CATEGORY = SECTION_NAME

    @classmethod
    def IS_CHANGED(cls, level="sfw", seed=-1, tag_cap=0, base_prob=0.65, slot_weights="",
                   role_mode="不指定", role_name="", role_works="",
                   quality_prefix="", artist_on=False, negative_on=True, extra_body="",
                   quality_on=True, scene_mode=_SCENE_LABELS[0], template_override="",
                   random_each_run=True):
        if not str(template_override or "").strip() and (int(seed) < 0 or bool(random_each_run)):
            return f"rand:{time.time_ns()}"
        raw = "|".join(str(x) for x in (level, seed, tag_cap, base_prob, slot_weights,
                                        role_mode, role_name, role_works, quality_prefix,
                                        artist_on, negative_on, extra_body, quality_on,
                                        scene_mode, template_override, random_each_run))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def run(self, level, seed, tag_cap, base_prob, slot_weights, role_mode,
            role_name, role_works, quality_prefix, artist_on, negative_on, extra_body,
            quality_on=True, scene_mode=_SCENE_LABELS[0], template_override="",
            random_each_run=True):
        key = _KEY_OF_LABEL.get(level, level)
        if key not in LEVEL_NUM:
            key = "sfw"
        use_seed = -1 if (bool(random_each_run) and not str(template_override or "").strip()) else int(seed)
        res = generate(
            level=key,
            seed=use_seed,
            tag_cap=int(tag_cap),
            base_prob=float(base_prob),
            slot_weights=slot_weights,
            role_mode=_ROLE_KEYS.get(role_mode, "none"),
            role_name=role_name,
            role_works=role_works,
            quality_prefix=quality_prefix if quality_on else "",
            artist_on=bool(artist_on),
            extra_body=extra_body,
            negative_on=bool(negative_on),
            scene_mode=_SCENE_KEYS.get(scene_mode, "scene"),
            override_text=template_override,
        )
        return (res["positive"], res["negative"], res["level"], res["report"])


NODE_CLASS_MAPPINGS = {"PromptForgeRandom": PromptForgeRandom}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptForgeRandom": "Prompt Forge 随机提示词（中文）"}

WEB_DIRECTORY = "./web"

# 面板数据接口：把 1800 条成品模板按需返回给前端
try:
    from server import PromptServer
    import json
    import os

    _UI_CACHE = {}

    @PromptServer.instance.routes.get("/prompt_forge/library")
    async def _prompt_forge_library(request):
        from aiohttp import web
        cats = _UI_CACHE.get("lib")
        if cats is None:
            path = os.path.join(os.path.dirname(__file__), "data", "tags.json")
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cats = [{
                "id": c["id"],
                "name": c.get("name", c["id"]),
                "icon": c.get("icon", ""),
                "tags": [{"en": t["en"], "zh": t.get("zh", ""), "lv": int(t.get("lv", 0)),
                          "meta": bool(t.get("meta"))}
                         for t in c.get("tags", [])],
            } for c in raw.get("cats", [])]
            _UI_CACHE["lib"] = cats
        return web.json_response({"cats": cats})

    @PromptServer.instance.routes.get("/prompt_forge/scene_meta")
    async def _prompt_forge_scene_meta(request):
        from aiohttp import web
        meta = _UI_CACHE.get("scene_meta")
        if meta is None:
            path = os.path.join(os.path.dirname(__file__), "data", "scenes.json")
            with open(path, "r", encoding="utf-8") as f:
                sc = json.load(f)
            meta = {}
            for b in sc.get("bundles", []):
                night = "night" in (b.get("time") or [])
                meta[b["id"]] = {
                    "indoor": bool(b.get("indoor")),
                    "outdoor": not bool(b.get("indoor")),
                    "water": bool(b.get("water")),
                    "cold": bool(b.get("cold")),
                    "night": night,
                    "monster": b["id"] in (sc.get("monster_bundles") or []),
                }
            _UI_CACHE["scene_meta"] = meta
        return web.json_response(meta)

    @PromptServer.instance.routes.get("/prompt_forge/roll")
    async def _prompt_forge_roll(request):
        from aiohttp import web
        level = (request.query.get("level") or "sfw").strip().lower()
        seed = int(request.query.get("seed") or -1)
        res = generate(level=level if level in LEVEL_NUM else "sfw", seed=seed,
                       scene_mode="scene")
        return web.json_response({"positive": res["positive"],
                                  "negative": res["negative"],
                                  "level": res["level"]})

    @PromptServer.instance.routes.get("/prompt_forge/templates")
    async def _prompt_forge_templates(request):
        from aiohttp import web
        level = (request.query.get("level") or "").strip().lower()
        kind = (request.query.get("kind") or "").strip().lower()
        data = _UI_CACHE.get("data")
        if data is None:
            path = os.path.join(os.path.dirname(__file__), "data", "templates_ui.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
            _UI_CACHE["data"] = data
        items = data
        if level and level != "all":
            items = [x for x in items if x.get("level") == level]
        if kind and kind != "all":
            items = [x for x in items if x.get("kind") == kind]
        return web.json_response({"total": len(items), "items": items})
except Exception:  # 非 ComfyUI 环境（单元测试）下跳过路由注册
    pass

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__", "WEB_DIRECTORY"]


