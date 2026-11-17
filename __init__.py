# -*- coding: utf-8 -*-
"""Comfyui-Prompt-Forge —— 独立的自定义节点，不依赖也不修改 Anima Wardrobe V6。

两个节点：
  · PromptForgeRandom   随机生成一整段提示词（档位 / 种子 / 槽位权重 / 角色输入）
  · AnimaCharacterPicker 从 2432 条本地角色库里选人（身份 / 外观 / 服装三段）

角色库数据在 data/characters.json + thumbs/，由 tools/build_characters.py 从
Comfyui-Anima-Wardrobe-V6 构建而来；构建完成后本插件完全独立，装不装 V6 都能用。
"""
import base64
import hashlib
import json
import os
import time

from .engine import (LEVEL_CHOICES, LEVEL_ZH, LEVEL_NUM, generate,
                     load_data, tag_level)
from . import settings as _settings_mod
from . import char_state as _char_state
from . import picker as _char_picker

__version__ = "0.1.1"
SECTION_NAME = "AnimaDecouple/Prompt Forge"
CHAR_SECTION = "AnimaDecouple/Character"

_LEVEL_WITH_ZH = [f"{k} · {LEVEL_ZH[k]}" if k != "any" else "any · 不限" for k in LEVEL_CHOICES]
_KEY_OF_LABEL = {label: key for key, label in zip(LEVEL_CHOICES, _LEVEL_WITH_ZH)}
_ROLE_LABELS = ["不指定", "随机", "指定"]
_ROLE_KEYS = {"不指定": "none", "随机": "random", "指定": "specified"}
_SCENE_LABELS = ["场景成套 · 现实逻辑", "自由随机 · 全库乱抽"]
_SCENE_KEYS = {_SCENE_LABELS[0]: "scene", _SCENE_LABELS[1]: "free", "scene": "scene", "free": "free"}
_OVERRIDE_LABELS = ["直通", "混合"]
_OVERRIDE_KEYS = {"直通": "direct", "混合": "mixed", "direct": "direct", "mixed": "mixed"}


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
                                    "tooltip": "总标签上限；0 = 自动（全年龄 28 / 成人 32）"}),
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
                # 追加在末尾，遵守控件顺序契约（C-01）
                "override_mode": (_OVERRIDE_LABELS, {"default": "直通",
                                                     "tooltip": "直通 = 覆盖文本直接当正向（旧行为）；混合 = 覆盖文本当锁定词，其余槽位继续随机"}),
                "role_prompt": ("STRING", {"default": "", "forceInput": True,
                                           "tooltip": "从左侧连线接入的角色提示词（角色名 / tag / 外观）；优先级高于角色模式"}),
                # 追加在末尾：角色输入进来后，外观是否让位（v0.12.1）
                "appearance_follow": ("BOOLEAN", {"default": True,
                                                  "tooltip": "角色输入非空时，发型 / 发色 / 面部 / 瞳色 / 身材不再随机，交给角色输入。关掉则仍会随机抽，可能和角色官方设定打架"}),
                "outfit_follow": ("BOOLEAN", {"default": False,
                                              "tooltip": "角色输入非空时，服装与配饰也不再随机。角色节点勾了「输出服装」时打开它"}),
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
                   random_each_run=True, override_mode="直通", role_prompt="",
                   appearance_follow=True, outfit_follow=False):
        override = str(template_override or "").strip()
        direct = _OVERRIDE_KEYS.get(override_mode, "direct") == "direct"
        if not override and (int(seed) < 0 or bool(random_each_run)):
            return f"rand:{time.time_ns()}"
        raw = "|".join(str(x) for x in (level, seed, tag_cap, base_prob, slot_weights,
                                        role_mode, role_name, role_works, quality_prefix,
                                        artist_on, negative_on, extra_body, quality_on,
                                        scene_mode, template_override, random_each_run,
                                        override_mode, role_prompt,
                                        appearance_follow, outfit_follow))
        # 覆盖直通不读档位配置，配置版本无须纳入；其余情况必须纳入（REQ-109）
        if not (override and direct):
            _, version = _settings_mod.snapshot()
            raw = raw + "|" + version
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def run(self, level, seed, tag_cap, base_prob, slot_weights, role_mode,
            role_name, role_works, quality_prefix, artist_on, negative_on, extra_body,
            quality_on=True, scene_mode=_SCENE_LABELS[0], template_override="",
            random_each_run=True, override_mode="直通", role_prompt="",
            appearance_follow=True, outfit_follow=False):
        key = _KEY_OF_LABEL.get(level, level)
        if key not in LEVEL_NUM:
            key = "sfw"
        cfg, _ = _settings_mod.snapshot()
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
            override_mode=_OVERRIDE_KEYS.get(override_mode, "direct"),
            role_prompt=role_prompt,
            settings=cfg,
            appearance_follow=bool(appearance_follow),
            outfit_follow=bool(outfit_follow),
        )
        return (res["positive"], res["negative"], res["level"], res["report"])


CHAR_MODE_LABELS = ["随机", "指定", "收藏随机", "多选加权"]
CHAR_OUTFIT_LEVELS = ["全年龄", "擦边", "成人"]
CHAR_THUMB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thumbs")


class AnimaCharacterPicker:
    """从本地角色库里挑人，输出身份 / 外观 / 服装三段提示词。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (CHAR_MODE_LABELS, {"default": "随机",
                                            "tooltip": "随机 = 全库按人气抽取；指定 = 用下面的名字；收藏随机 = 只在收藏里抽；多选加权 = 只在面板勾选的里按权重抽"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647,
                                 "tooltip": "-1 = 每次运行重抽；>=0 = 可复现"}),
                "role_name": ("STRING", {"default": "", "multiline": False,
                                         "tooltip": "指定模式下填英文 tag / 英文名 / 中文名，面板点人会自动写这里"}),
                "work_filter": ("STRING", {"default": "", "multiline": False,
                                           "tooltip": "随机模式按作品限定，多个用 | 分隔，如 hololive|原神"}),
                "include_appearance": ("BOOLEAN", {"default": True,
                                                   "tooltip": "输出角色的官方外观（发色 / 发型 / 瞳色 / 面部 / 身材）"}),
                "include_outfit": ("BOOLEAN", {"default": False,
                                               "tooltip": "输出角色的服装预设。开了它，下游节点就别再出服装了"}),
            },
            "optional": {
                "outfit_level": (CHAR_OUTFIT_LEVELS, {"default": "全年龄",
                                                      "tooltip": "服装档位上限：擦边 / 成人会放开角色库里更高档的套装"}),
                "outfit_id": ("STRING", {"default": "", "multiline": False,
                                         "tooltip": "指定套装 id（面板选套装时自动填）；留空 = 取该档位第一套"}),
                "extra_prompt": ("STRING", {"default": "", "multiline": True,
                                            "tooltip": "手写补充，拼在 positive 末尾"}),
                "random_each_run": ("BOOLEAN", {"default": True,
                                                "tooltip": "每次运行都重新抽人（忽略固定种子）"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("character", "appearance", "outfit", "positive", "report")
    FUNCTION = "run"
    CATEGORY = CHAR_SECTION

    @classmethod
    def IS_CHANGED(cls, mode="随机", seed=-1, role_name="", work_filter="",
                   include_appearance=True, include_outfit=False,
                   outfit_level="全年龄", outfit_id="", extra_prompt="",
                   random_each_run=True):
        if int(seed) < 0 or bool(random_each_run):
            return f"rand:{time.time_ns()}"
        raw = "|".join(str(x) for x in (mode, seed, role_name, work_filter,
                                        include_appearance, include_outfit,
                                        outfit_level, outfit_id, extra_prompt))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def run(self, mode="随机", seed=-1, role_name="", work_filter="",
            include_appearance=True, include_outfit=False,
            outfit_level="全年龄", outfit_id="", extra_prompt="",
            random_each_run=True):
        use_seed = -1 if bool(random_each_run) else int(seed)
        st = _char_state.load_state()
        rec, why = _char_picker.select(mode=mode, seed=use_seed, role_name=role_name,
                                       work_filter=work_filter, st=st)
        if not rec:
            return ("", "", "", str(extra_prompt or "").strip(),
                    "\n".join([f"模式: {mode}", f"没挑到角色: {why}"]))

        seg = _char_picker.compose(rec, include_appearance=bool(include_appearance),
                                   include_outfit=bool(include_outfit),
                                   outfit_level=outfit_level, outfit_id=outfit_id)

        positive = seg["positive"]
        if str(extra_prompt or "").strip():
            positive = positive + ", " + str(extra_prompt).strip().strip(",")

        try:
            recent = [rec["tag"]] + [t for t in (st.get("recent") or []) if t != rec["tag"]]
            st["recent"] = recent[:24]
            _char_state.save_state(st)
        except Exception:
            pass

        lines = [
            f"模式: {why}",
            f"角色: {rec.get('zh') or rec.get('name')}（{rec['tag']}）",
            f"作品: {rec.get('work') or '未知'}",
            f"身份: {seg['character']}",
            f"外观: {seg['counts']['appearance']} 条" + ("" if include_appearance else "（已关闭）"),
            "服装: " + (f"{seg['counts']['outfit']} 条 · {seg['outfit_name']}"
                        if include_outfit else "已关闭"),
            f"种子: {use_seed}",
        ]
        return (seg["character"], seg["appearance"], seg["outfit"],
                positive, "\n".join(lines))


NODE_CLASS_MAPPINGS = {"PromptForgeRandom": PromptForgeRandom,
                       "AnimaCharacterPicker": AnimaCharacterPicker}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptForgeRandom": "Prompt Forge 随机提示词（中文）",
                              "AnimaCharacterPicker": "Anima 角色选择（中文）"}

WEB_DIRECTORY = "./web"

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 面板数据接口：把 1800 条成品模板按需返回给前端
try:
    from server import PromptServer

    _UI_CACHE = {}

    def _read_json(fname, default):
        try:
            with open(os.path.join(_DATA_DIR, fname), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @PromptServer.instance.routes.get("/prompt_forge/library")
    async def _prompt_forge_library(request):
        from aiohttp import web
        cats = _UI_CACHE.get("lib")
        if cats is None:
            raw = _read_json("tags.json", {"cats": []})
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
            sc = _read_json("scenes.json", {"bundles": []})
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

    @PromptServer.instance.routes.get("/prompt_forge/scenes")
    async def _prompt_forge_scenes(request):
        from aiohttp import web
        sc = _UI_CACHE.get("scenes")
        if sc is None:
            sc = _read_json("scenes.json", {"bundles": []})
            _UI_CACHE["scenes"] = sc
        return web.json_response(sc)

    @PromptServer.instance.routes.get("/prompt_forge/tag_flags")
    async def _prompt_forge_tag_flags(request):
        from aiohttp import web
        flags = _UI_CACHE.get("tag_flags")
        if flags is None:
            flags = _read_json("tag_flags.json", {})
            _UI_CACHE["tag_flags"] = flags
        return web.json_response(flags)

    def _roll_from(payload):
        """把前端传来的节点全参数 JSON 归一化后交给 generate。"""
        def _num(k, d, cast=float):
            try:
                return cast(payload.get(k, d))
            except (TypeError, ValueError):
                return d

        level = str(payload.get("level") or "sfw").strip().lower()
        if level not in LEVEL_NUM:
            level = "sfw"
        cfg, _ = _settings_mod.snapshot()
        return generate(
            level=level,
            seed=_num("seed", -1, int),
            tag_cap=_num("tag_cap", 0, int),
            base_prob=_num("base_prob", 0.65),
            slot_weights=str(payload.get("slot_weights") or ""),
            role_mode=str(payload.get("role_mode") or "none"),
            role_name=str(payload.get("role_name") or ""),
            role_works=str(payload.get("role_works") or ""),
            quality_prefix=str(payload.get("quality_prefix") or ""),
            artist_on=bool(payload.get("artist_on", False)),
            extra_body=str(payload.get("extra_body") or ""),
            negative_on=bool(payload.get("negative_on", True)),
            scene_mode=str(payload.get("scene_mode") or "scene"),
            override_text=str(payload.get("template_override") or ""),
            override_mode=str(payload.get("override_mode") or "direct"),
            role_prompt=str(payload.get("role_prompt") or ""),
            settings=cfg,
        )

    @PromptServer.instance.routes.get("/prompt_forge/roll")
    async def _prompt_forge_roll(request):
        """旧只读接口，保留兼容（deprecated）；新代码走 POST。"""
        from aiohttp import web
        level = (request.query.get("level") or "sfw").strip().lower()
        seed = int(request.query.get("seed") or -1)
        res = _roll_from({"level": level if level in LEVEL_NUM else "sfw", "seed": seed,
                          "scene_mode": "scene"})
        return web.json_response({"positive": res["positive"],
                                  "negative": res["negative"],
                                  "level": res["level"]})

    @PromptServer.instance.routes.post("/prompt_forge/roll")
    async def _prompt_forge_roll_post(request):
        from aiohttp import web
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "请求体必须是 JSON 对象"}, status=400)
        try:
            res = _roll_from(payload)
        except Exception as exc:
            return web.json_response({"error": f"生成失败: {exc}"}, status=500)
        return web.json_response({"positive": res["positive"],
                                  "negative": res["negative"],
                                  "level": res["level"],
                                  "report": res["report"],
                                  "target_level": res.get("target_level")})

    @PromptServer.instance.routes.get("/prompt_forge/templates")
    async def _prompt_forge_templates(request):
        from aiohttp import web
        level = (request.query.get("level") or "").strip().lower()
        kind = (request.query.get("kind") or "").strip().lower()
        data = _UI_CACHE.get("data")
        if data is None:
            data = _read_json("templates_ui.json", [])
            _UI_CACHE["data"] = data
        items = data
        if level and level != "all":
            items = [x for x in items if x.get("level") == level]
        if kind and kind != "all":
            items = [x for x in items if x.get("kind") == kind]
        return web.json_response({"total": len(items), "items": items})

    @PromptServer.instance.routes.get("/prompt_forge/userdata")
    async def _prompt_forge_userdata_get(request):
        from aiohttp import web
        return web.json_response(_settings_mod.read_userdata())

    @PromptServer.instance.routes.post("/prompt_forge/userdata")
    async def _prompt_forge_userdata_post(request):
        from aiohttp import web
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "请求体必须是 JSON"}, status=400)
        ok, err = _settings_mod.write_userdata(payload)
        if not ok:
            return web.json_response({"ok": False, "error": err}, status=400)
        return web.json_response({"ok": True})

    # ---------------------------------------------------- 角色库（/anima_char/）
    _CHAR_CACHE = {}

    def _char_library_payload():
        if "payload" not in _CHAR_CACHE:
            lib = _char_picker.library()
            chars = []
            for c in lib["characters"]:
                chars.append({
                    "tag": c["tag"],
                    "name": c.get("name") or c["tag"],
                    "zh": c.get("zh") or "",
                    "work": c.get("work") or "",
                    "trigger": c.get("trigger") or c["tag"],
                    "pop": int(c.get("pop") or 0),
                    "thumb": c.get("thumb") or "",
                    "custom": bool(c.get("custom")),
                    "appearance": c.get("appearance") or {},
                    "outfits": [{"id": o.get("id"), "zh": o.get("zh") or "",
                                 "level": int(o.get("level") or 0),
                                 "tags": o.get("tags") or []}
                                for o in (c.get("outfits") or [])],
                })
            _CHAR_CACHE["payload"] = {"works": _char_picker.works_payload(),
                                      "characters": chars}
        return _CHAR_CACHE["payload"]

    @PromptServer.instance.routes.get("/anima_char/library")
    async def _char_library(request):
        from aiohttp import web
        return web.json_response(_char_library_payload())

    @PromptServer.instance.routes.get("/anima_char/state")
    async def _char_state_get(request):
        from aiohttp import web
        return web.json_response(_char_state.load_state())

    @PromptServer.instance.routes.post("/anima_char/state")
    async def _char_state_post(request):
        from aiohttp import web
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "请求体必须是 JSON"}, status=400)
        ok, err = _char_state.save_state(payload)
        if not ok:
            return web.json_response({"ok": False, "error": err}, status=400)
        return web.json_response({"ok": True})

    @PromptServer.instance.routes.get("/anima_char/thumb/{tag}")
    async def _char_thumb(request):
        from aiohttp import web
        tag = request.match_info.get("tag", "")
        custom = _char_state.custom_thumb_path(tag)
        if custom and os.path.exists(custom):
            return web.FileResponse(custom)
        safe = "".join(ch for ch in str(tag).lower() if ch.isalnum() or ch in "_-")
        path = os.path.join(CHAR_THUMB_DIR, safe + ".webp")
        if safe and os.path.exists(path):
            return web.FileResponse(path)
        return web.json_response({"error": "没有预览图"}, status=404)

    @PromptServer.instance.routes.post("/anima_char/thumb/{tag}")
    async def _char_thumb_upload(request):
        from aiohttp import web
        tag = request.match_info.get("tag", "")
        path = _char_state.custom_thumb_path(tag)
        if not path:
            return web.json_response({"ok": False, "error": "tag 非法"}, status=400)
        try:
            payload = await request.json()
            raw = base64.b64decode(str(payload.get("data") or ""), validate=False)
        except Exception:
            return web.json_response({"ok": False, "error": "图片数据无法解析"}, status=400)
        if not raw or len(raw) > 4 * 1024 * 1024:
            return web.json_response({"ok": False, "error": "图片为空或超过 4 MB"}, status=400)
        if not raw[:4] == b"RIFF" or raw[8:12] != b"WEBP":
            return web.json_response({"ok": False, "error": "只接受 webp 格式"}, status=400)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(raw)
        return web.json_response({"ok": True})

    @PromptServer.instance.routes.post("/anima_char/char/save")
    async def _char_save(request):
        from aiohttp import web
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "请求体必须是 JSON"}, status=400)
        if not isinstance(payload, dict) or not str(payload.get("tag") or "").strip():
            return web.json_response({"ok": False, "error": "tag 不能为空"}, status=400)
        rec = {
            "tag": str(payload["tag"]).strip().lower(),
            "name": str(payload.get("name") or "").strip(),
            "zh": str(payload.get("zh") or "").strip(),
            "work": str(payload.get("work") or "").strip().lower(),
            "trigger": str(payload.get("trigger") or payload["tag"]).strip(),
            "pop": int(payload.get("pop") or 0),
            "thumb": "",
            "subject": ["1girl"],
            "appearance": payload.get("appearance") or {},
            "outfits": payload.get("outfits") or [],
        }
        ok, err = _char_state.upsert_custom(rec)
        if not ok:
            return web.json_response({"ok": False, "error": err}, status=400)
        _char_picker.invalidate()
        _CHAR_CACHE.pop("payload", None)
        return web.json_response({"ok": True})

    @PromptServer.instance.routes.post("/anima_char/char/delete")
    async def _char_delete(request):
        from aiohttp import web
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "请求体必须是 JSON"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"ok": False, "error": "请求体必须是 JSON 对象"}, status=400)
        ok, err = _char_state.delete_custom(payload.get("tag"))
        if not ok:
            return web.json_response({"ok": False, "error": err}, status=400)
        _char_picker.invalidate()
        _CHAR_CACHE.pop("payload", None)
        return web.json_response({"ok": True})
except Exception:  # 非 ComfyUI 环境（单元测试）下跳过路由注册
    pass

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__", "WEB_DIRECTORY"]
