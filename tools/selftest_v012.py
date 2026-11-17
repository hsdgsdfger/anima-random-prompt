# -*- coding: utf-8 -*-
"""v0.12.0 回归自检（不依赖 ComfyUI）。

覆盖：覆盖直通 / 混合模式 / 角色输入 / 档位抽样比例 / 不越档 / 缓存哈希 /
配置读写与上三角校验 / 用户态文件原子写。

用法：python tools/selftest_v012.py
"""
import importlib.util
import json
import re
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

spec = importlib.util.spec_from_file_location(
    "pf", os.path.join(ROOT, "__init__.py"),
    submodule_search_locations=[ROOT])
pf = importlib.util.module_from_spec(spec)
sys.modules["pf"] = pf
spec.loader.exec_module(pf)

engine = sys.modules["pf.engine"]
settings = sys.modules["pf.settings"]

import importlib
scenes = importlib.import_module("pf.scenes")

fails = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name} {extra}")
        fails.append(name)


def tags_of(pos):
    return [x.strip() for x in pos.split(",") if x.strip()]


print("\n[T-05] 覆盖直通")
res = engine.generate(level="sfw", override_text="test")
check("positive 恰为 test", res["positive"] == "test", res["positive"])

print("\n[REQ-102] 混合模式")
locked = "red dress, night, smile"
for i in range(10):
    r = engine.generate(level="sfw", seed=i, override_text=locked, override_mode="mixed",
                        quality_prefix="")
    ts = [t.lower() for t in tags_of(r["positive"])]
    if not all(x.strip().lower() in ts for x in locked.split(",")):
        check(f"第 {i} 次锁定词丢失", False, r["positive"])
        break
else:
    check("锁定 3 词 10 次全在", True)

rs = [engine.generate(level="sfw", seed=i, override_text=locked, override_mode="mixed",
                      quality_prefix="")["positive"] for i in range(10)]
check("其余槽位有变化（>=8 次不同）", len(set(rs)) >= 8, f"{len(set(rs))}/10")

r = engine.generate(level="sfw", seed=1, override_text=locked, override_mode="mixed",
                    quality_prefix="")
ts = [t.lower() for t in tags_of(r["positive"])]
check("锁定词与随机词无重复", len(ts) == len(set(ts)), r["positive"])

many = ", ".join(f"lock{i}" for i in range(30))
r = engine.generate(level="sfw", seed=1, override_text=many, override_mode="mixed",
                    tag_cap=26, quality_prefix="")
check("锁定 30 词 + tag_cap=26 不追加随机", len(tags_of(r["positive"])) <= 30,
      str(len(tags_of(r["positive"]))))

print("\n[REQ-104] 角色输入")
r = engine.generate(level="sfw", seed=7, role_prompt="hatsune miku", quality_prefix="")
ts = [t.lower() for t in tags_of(r["positive"])]
check("角色词出现", "hatsune miku" in ts, r["positive"])
check("角色词在主体之后", ts.index("hatsune miku") > ts.index("1girl") if "1girl" in ts else True)
check("report 标外部输入", "外部输入" in r["report"])
check("report 标服装按档位过滤", "服装按档位过滤" in r["report"])

r = engine.generate(level="sfw", seed=7, role_prompt="1girl, solo, long hair", quality_prefix="")
ts = [t.lower() for t in tags_of(r["positive"])]
check("1girl 不重复", ts.count("1girl") == 1, r["positive"])
check("solo 不重复", ts.count("solo") == 1, r["positive"])

r = engine.generate(level="sfw", seed=7, role_prompt="1boy, penis, long hair", quality_prefix="")
ts = [t.lower() for t in tags_of(r["positive"])]
check("男性词被丢弃", "1boy" not in ts and "penis" not in ts, r["positive"])
check("不出现 1girl+1boy 并存", not ("1boy" in ts and "1girl" in ts))
check("report 标注剔除数", "已剔除" in r["report"], r["report"])

r = engine.generate(level="sfw", seed=7, scene_mode="scene", role_prompt="hatsune miku")
check("场景路径含角色词", "hatsune miku" in r["positive"], r["positive"][:120])
check("场景路径有 bundle", bool(r.get("bundle")), str(r.get("bundle")))

r = engine.generate(level="sfw", seed=7, override_text="xx", role_prompt="hatsune miku")
check("直通下角色不生效", "hatsune miku" not in r["positive"], r["positive"])
check("直通下 report 提示未生效", "未生效" in r["report"], r["report"])

print("\n[REQ-107/108] 档位抽样")
base_off = settings.default_settings()
base_off["level_dist"] = False


def dist(level, n=400, cfg=None):
    c = dict(settings.default_settings())
    if cfg:
        c.update(cfg)
    cnt = [0] * 5
    for i in range(n):
        r = engine.generate(level=level, seed=1000 + i, settings=c)
        cnt[r["target_level"]] += 1
    return cnt


c = dist("explicit", 400, {"level_dist": True})
check(f"explicit 开启分布 Lv2≈50% -> {c[2]}/400", 160 <= c[2] <= 240, str(c))
check(f"explicit 开启分布 Lv0+Lv1≈50% -> {c[0]}+{c[1]}", 160 <= c[0] + c[1] <= 240, str(c))

c = dist("explicit", 200, {"level_dist": False})
check("explicit 关闭分布全部 Lv2", c[2] == 200, str(c))

c = dist("any", 400)
check(f"any 默认 sfw≈70% -> {c[0]}/400", 240 <= c[0] <= 320, str(c))
check(f"any 默认其余四档 ≈30% -> {sum(c[1:])}/400", 70 <= sum(c[1:]) <= 140, str(c))

cfg_any = {"any_weights": {"sfw": 0, "suggestive": 0, "explicit": 1, "hardcore": 0, "extreme": 0}}
c = dist("any", 20, cfg_any)
check("any 自定义 sfw=0/explicit=100 全落 Lv2", c[2] == 20, str(c))

cfg_row = {"level_dist": True,
           "level_matrix": {"sfw": {"sfw": 1}, "suggestive": {"suggestive": 1},
                            "explicit": {"explicit": 1}, "hardcore": {"hardcore": 1},
                            "extreme": {"extreme": 1}}}
c = dist("explicit", 20, cfg_row)
check("explicit 行 100% 全落 Lv2", c[2] == 20, str(c))

# 不越档：explicit 的输出里不得出现 lv>=3 的词
# （同名 tag 在不同分类有不同 lv，取跨分类最小值才是它真正的下限）
_raw = engine.load_data()
_min_lv = {}
for _c in _raw["cats"]:
    for _t in _c["tags"]:
        _k = _t["en"].lower()
        _min_lv[_k] = min(_min_lv.get(_k, 9), int(_t["lv"]))


def min_level(tag):
    return _min_lv.get(tag.lower(), 0)


bad = 0
for i in range(60):
    r = engine.generate(level="explicit", seed=5000 + i, settings=cfg_row)
    for t in tags_of(r["positive"]):
        if min_level(t) > 2:
            bad += 1
            print("     越档:", t, min_level(t))
check("explicit 输出无 lv>=3 词", bad == 0, f"{bad} 处")

r1 = engine.generate(level="any", seed=42, settings=cfg_any)
r2 = engine.generate(level="any", seed=42, settings=cfg_any)
check("固定 seed 目标档位可复现", r1["target_level"] == r2["target_level"])
check("固定 seed 输出一致", r1["positive"] == r2["positive"])

print("\n[REQ-109] config_version")
d = tempfile.mkdtemp(prefix="pf_cfg_")
old_dir, old_path = settings.USERDATA_DIR, settings.USERDATA_PATH
try:
    settings.USERDATA_DIR = d
    settings.USERDATA_PATH = os.path.join(d, "prompt_forge.json")
    v0 = settings.snapshot()[1]
    check("默认 config_version = default", v0 == "default", v0)

    ok, e = settings.write_userdata({"favorites": {"tags": ["a"]},
                                     "settings": settings.default_settings()})
    check("写入成功", ok, str(e))
    v1 = settings.snapshot()[1]
    check("写入默认 settings 后版本变化", v1 != "default", v1)

    ok, e = settings.write_userdata({"favorites": {"tags": ["a", "b"]},
                                     "settings": settings.default_settings()})
    v2 = settings.snapshot()[1]
    check("只改收藏不改版本", v1 == v2, f"{v1} vs {v2}")

    s = settings.default_settings()
    s["level_dist"] = True
    ok, e = settings.write_userdata({"favorites": {"tags": ["a"]}, "settings": s})
    v3 = settings.snapshot()[1]
    check("改 settings 后版本变化", v3 != v2, f"{v3} vs {v2}")

    bad = settings.default_settings()
    bad["level_matrix"]["explicit"]["hardcore"] = 0.3
    ok, e = settings.write_userdata({"favorites": {}, "settings": bad})
    check("上三角非零被拒", not ok and "不超过该档" in str(e), str(e))

    bad2 = settings.default_settings()
    bad2["level_matrix"]["explicit"] = {"explicit": 0, "sfw": 0}
    ok, e = settings.write_userdata({"favorites": {}, "settings": bad2})
    check("行内全 0 被拒", not ok, str(e))

    ok, e = settings.write_userdata({"favorites": {}, "settings": None, "evil": 1})
    check("白名单键被拒", not ok, str(e))

    with open(settings.USERDATA_PATH, "w", encoding="utf-8") as f:
        f.write("{broken json")
    settings._CACHE["key"] = None
    snap = settings.snapshot()
    check("损坏文件回落默认", snap[1] == "default", snap[1])
    check("损坏文件可读空结构", settings.read_userdata()["favorites"]["tags"] == [])
finally:
    settings.USERDATA_DIR, settings.USERDATA_PATH = old_dir, old_path
    settings._CACHE["key"] = None
    shutil.rmtree(d, ignore_errors=True)

print("\n[IS_CHANGED]")
node = pf.PromptForgeRandom
h1 = node.IS_CHANGED(seed=42, random_each_run=False, template_override="")
h2 = node.IS_CHANGED(seed=42, random_each_run=False, template_override="")
check("固定 seed 关闭重抽：哈希稳定", h1 == h2)
h3 = node.IS_CHANGED(seed=42, random_each_run=False, template_override="", role_prompt="a")
check("改 role_prompt 哈希变化", h1 != h3)
h4 = node.IS_CHANGED(seed=42, random_each_run=False, template_override="t")
h5 = node.IS_CHANGED(seed=42, random_each_run=False, template_override="t", level="explicit")
check("覆盖直通仍随参数变化", h4 != h5)
h6 = node.IS_CHANGED(seed=42, random_each_run=True)
h7 = node.IS_CHANGED(seed=42, random_each_run=True)
check("开启重抽：每次不同", h6 != h7 and h6.startswith("rand:"))

print("\n[输出口兼容]")
r = engine.generate(level="any", seed=3)
check("any 的 level 输出保持 'any · 不限'", r["level"] == "any · 不限", r["level"])
r = engine.generate(level="sfw", seed=3)
check("sfw 的 level 输出保持 '0 · 全年龄'", r["level"] == "0 · 全年龄", r["level"])

print("\n[全档位 100 次不报错]")
for lv in ("sfw", "suggestive", "explicit", "hardcore", "extreme", "any"):
    okc = 0
    for i in range(50):
        r = engine.generate(level=lv, seed=i)
        if r["positive"]:
            okc += 1
    check(f"{lv} 50 次全部有输出", okc == 50, str(okc))

# ---------------------------------------------------------------- 服装与场景
# 2026-11-17 用户报「sfw 出泳装」「胸前总被挡住」，下面是那两次的回归。
GAR = engine._GARMENT
SWIM = engine._NSFW_CLOTH

# ① 角色带服装 + 普通场景 → 必须穿角色的那套
role_cloth = ("firefly (honkai: star rail), silver hair, purple eyes, "
              "white shirt, skirt, school uniform")
kept = total = 0
for i in range(20):
    r = engine.generate(level="sfw", seed=6000 + i, scene_mode="scene",
                        role_prompt=role_cloth, appearance_follow=True,
                        outfit_follow=True, quality_prefix="", settings={})
    ms = re.search(r"场景: ([^（]+)", r["report"])
    bid = ms.group(1).strip() if ms else ""
    if scenes.is_special_scene(bid):
        continue
    total += 1
    if "white shirt" in r["positive"].lower():
        kept += 1
check("普通场景保留角色服装", total > 0 and kept == total, f"{kept}/{total}")

# ② 角色 outfit 是泳装时，sfw 档必须剔除
role_swim = "bay (nikke), long hair, blue eyes, white bikini, bikini, swimsuit"
leak = 0
for i in range(15):
    r = engine.generate(level="sfw", seed=6100 + i, scene_mode="scene",
                        role_prompt=role_swim, appearance_follow=True,
                        outfit_follow=True, quality_prefix="", settings={})
    if SWIM.search(r["positive"]):
        leak += 1
check("sfw 档剔除角色泳装", leak == 0, f"{leak}/15")

# ③ 全裸时不能同时穿着整套衣服
nude_bad = 0
for i in range(20):
    r = engine.generate(level="extreme", seed=6200 + i, scene_mode="scene",
                        role_prompt=role_cloth, appearance_follow=True,
                        outfit_follow=True, quality_prefix="", settings={})
    ts = [t.strip().lower() for t in r["positive"].split(",")]
    if any(engine._NUDE_RE.match(t) for t in ts):
        if any(GAR.search(t) and not engine._HOSIERY.search(t) for t in ts):
            nude_bad += 1
check("全裸时清空服装", nude_bad == 0, f"{nude_bad}/20")

# ④ 锁定词主张的环境和场景不一致时，应该优先挑贴的
conflict = 0
for i in range(12):
    r = engine.generate(level="sfw", seed=6300 + i, scene_mode="scene",
                        override_text="1girl, solo, snowing, winter, snow",
                        override_mode="mixed", role_prompt="", quality_prefix="",
                        settings={})
    if re.search(r"\b(beach|ocean|summer|swimsuit)\b", r["positive"], re.I):
        conflict += 1
check("雪景锁定词不会抽到海边", conflict == 0, f"{conflict}/12")

print()
if fails:
    print(f"失败 {len(fails)} 项: {fails}")
    sys.exit(1)
print("全部通过")
