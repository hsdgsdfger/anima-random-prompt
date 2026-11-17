# -*- coding: utf-8 -*-
"""合并版插件的路由冒烟：用假的 PromptServer / aiohttp 跑一遍全部 18 个接口方法。

不启动 ComfyUI，也不依赖 torch —— 只验证注册、参数、路径安全、写盘。
用法：python tools/routes_smoke.py
"""
import asyncio
import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------- 假 aiohttp.web ----------
aiohttp = types.ModuleType("aiohttp")
web = types.ModuleType("aiohttp.web")


class _Resp:
    def __init__(self, payload=None, status=200, body=None, content_type=None,
                 headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = headers or {}
        self.payload = payload
        if self.payload is None and body is not None:
            try:
                raw = body.decode("utf-8") if isinstance(body, bytes) else body
                self.payload = json.loads(raw)
            except Exception:
                self.payload = None


class _File:
    def __init__(self, path, headers=None):
        self.path = path
        self.headers = headers or {}
        self.status = 200


web.json_response = lambda obj, status=200: _Resp(obj, status)
web.Response = lambda body=None, status=200, content_type=None, headers=None: \
    _Resp(None, status, body, content_type, headers)
web.FileResponse = lambda path, headers=None: _File(path, headers)
aiohttp.web = web
sys.modules["aiohttp"] = aiohttp
sys.modules["aiohttp.web"] = web

# ---------- 假 PromptServer ----------
routes = {}


class _R:
    def get(self, path):
        def deco(fn):
            routes[("GET", path)] = fn
            return fn
        return deco

    def post(self, path):
        def deco(fn):
            routes[("POST", path)] = fn
            return fn
        return deco


class _Inst:
    routes = _R()


server = types.ModuleType("server")
server.PromptServer = type("PromptServer", (), {"instance": _Inst()})
sys.modules["server"] = server

# ---------- 导入插件 ----------
spec = importlib.util.spec_from_file_location(
    "pf", os.path.join(ROOT, "__init__.py"), submodule_search_locations=[ROOT])
m = importlib.util.module_from_spec(spec)
sys.modules["pf"] = m
spec.loader.exec_module(m)

fails = []


def ok(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        fails.append(name)


class Req:
    def __init__(self, body=None, query=None, match=None, headers=None):
        self._body = body
        self.query = query or {}
        self.match_info = match or {}
        self.headers = headers or {}

    async def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def call(method, path, req=None):
    return asyncio.run(routes[(method, path)](req or Req()))


print("\n[节点注册]")
ok("两个节点都在", set(m.NODE_CLASS_MAPPINGS) == {"PromptForgeRandom", "AnimaCharacterPicker"},
   str(list(m.NODE_CLASS_MAPPINGS)))
_ver_file = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
ok(f"版本与 VERSION 一致（{m.__version__}）", m.__version__ == _ver_file,
   f"{m.__version__} vs {_ver_file}")
ok("显示名齐全", len(m.NODE_DISPLAY_NAME_MAPPINGS) == 2)

print("\n[路由注册]")
pf = {"GET": ["/prompt_forge/library", "/prompt_forge/scene_meta", "/prompt_forge/scenes",
              "/prompt_forge/tag_flags", "/prompt_forge/roll", "/prompt_forge/templates",
              "/prompt_forge/userdata"],
      "POST": ["/prompt_forge/roll", "/prompt_forge/userdata"]}
cc = {"GET": ["/anima_char/library", "/anima_char/index", "/anima_char/char/{tag}",
               "/anima_char/state", "/anima_char/thumb/{tag}"],
      "POST": ["/anima_char/state", "/anima_char/toggle", "/anima_char/thumb/{tag}",
               "/anima_char/char/save", "/anima_char/char/delete"]}
want = {(k, p) for k, ps in pf.items() for p in ps} | {(k, p) for k, ps in cc.items() for p in ps}
ok(f"共 {len(want)} 个方法全部注册（实际 {len(routes)}）", set(routes) == want,
   str(sorted(set(routes) ^ want)))

print("\n[角色库 /library]")
r = call("GET", "/anima_char/library")
ok("返回 works + characters", "works" in r.payload and "characters" in r.payload)
ok(f"角色数 {len(r.payload['characters'])}（2432 内置 + 39 补充）",
   len(r.payload["characters"]) == 2471, str(len(r.payload["characters"])))
ok(f"作品数 {len(r.payload['works'])}（287 + 埃洛伊带出的地平线）",
   len(r.payload["works"]) == 288, str(len(r.payload["works"])))

print("\n[角色库 /state]")
body = {"favorites": ["hatsune_miku"], "excluded": [], "picked": [],
        "recent": [], "weights": {"hatsune_miku": 2.5}, "settings": {"zh": True}}
r = call("POST", "/anima_char/state", Req(body))
ok("写入成功", r.payload.get("ok") is True, str(r.payload))
r = call("GET", "/anima_char/state")
ok("读回收藏", r.payload["favorites"] == ["hatsune_miku"], str(r.payload["favorites"]))
ok("读回权重", r.payload["weights"].get("hatsune_miku") == 2.5)

print("\n[角色库 /thumb]")
r = call("GET", "/anima_char/thumb/{tag}", Req(match={"tag": "hatsune_miku"}))
ok("内置图命中", isinstance(r, _File) and os.path.exists(r.path), str(getattr(r, "path", r)))
r = call("GET", "/anima_char/thumb/{tag}", Req(match={"tag": "no_such_char_xx"}))
ok("缺图返回 404", isinstance(r, _Resp) and r.status == 404)
r = call("GET", "/anima_char/thumb/{tag}", Req(match={"tag": "../../__init__"}))
ok("路径穿越被挡", isinstance(r, _Resp) and r.status == 404)

print("\n[角色库 /char 增删]")
rec = {"tag": "test_orig", "name": "test orig", "zh": "测试角色", "work": "original",
       "trigger": "test orig", "appearance": {"hair_color": ["pink hair"]},
       "outfits": [{"id": "default", "zh": "默认", "level": 0, "tags": ["hoodie"]}]}
r = call("POST", "/anima_char/char/save", Req(rec))
ok("新增成功", r.payload.get("ok") is True, str(r.payload))
r = call("GET", "/anima_char/library")
ok("新角色进了库", any(c["tag"] == "test_orig" and c["custom"] for c in r.payload["characters"]))
r = call("POST", "/anima_char/char/save", Req({"tag": ""}))
ok("空 tag 被拒", r.status == 400)
r = call("POST", "/anima_char/char/delete", Req({"tag": "hatsune_miku"}))
ok("内置角色不能删", r.status == 400, str(r.payload))
r = call("POST", "/anima_char/char/delete", Req({"tag": "test_orig"}))
ok("自定义角色可删", r.payload.get("ok") is True)

print("\n[角色库 /thumb 上传]")
r = call("POST", "/anima_char/thumb/{tag}", Req({"data": "aGVsbG8="}, match={"tag": "test_orig"}))
ok("非 webp 被拒", r.status == 400)
r = call("POST", "/anima_char/thumb/{tag}", Req({"data": ""}, match={"tag": "x"}))
ok("空图被拒", r.status == 400)

print("\n[提示词 /userdata]")
r = call("GET", "/prompt_forge/userdata")
ok("返回 favorites + settings", "favorites" in r.payload and "settings" in r.payload)

print("\n[两个节点]")
pf_node = m.PromptForgeRandom()
out = pf_node.run("sfw · 全年龄", 5, 0, 0.65, "", "不指定", "", "",
                  "masterpiece, best quality", False, True, "",
                  True, "场景成套 · 现实逻辑", "", False, "直通",
                  "hatsune miku, aqua hair, twintails", True, False)
ok("提示词节点出词", bool(out[0]), out[0][:60])
ok("负向非空", bool(out[1]), out[1][:40])
body_only = out[0].replace("aqua hair", "").replace("twintails", "")
ok("外观让位生效（没混进随机发型发色）",
   not any(x in body_only for x in ("black hair", "blonde hair", "long hair", "bob cut")),
   out[0][:140])

cc_node = m.AnimaCharacterPicker()
out = cc_node.run(mode="指定", seed=1, role_name="初音未来", work_filter="",
                  include_appearance=True, include_outfit=True,
                  outfit_id="", extra_prompt="", random_each_run=False)
ok("角色节点出人", out[0].startswith("hatsune miku"), out[0])
ok("角色节点一正一负", len(out) == 2, str(len(out)))
ok("服装已拼进正向", "necktie" in out[0], out[0][-80:])

out = m.AnimaCharacterPicker().run(mode="随机", seed=7, role_name="", work_filter="touhou",
                                   include_appearance=True, include_outfit=False,
                                   outfit_id="", extra_prompt="", random_each_run=False)
ok("按作品限定生效", "touhou" in out[0], out[0])

print()
if fails:
    print("失败:", fails)
    sys.exit(1)
print("合并版路由与节点冒烟全部通过")
