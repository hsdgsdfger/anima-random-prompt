# -*- coding: utf-8 -*-
"""节点输入结构自检（v0.2.3）。

为什么需要：新版 ComfyUI 的 /object_info 会做

    info['input_order'] = {k: list(v.keys()) for k, v in obj_class.INPUT_TYPES().items()}

也就是**顶层每个键的值必须是 dict**。一旦把某个控件写到 required / optional 的
闭合括号外面（v0.2.0 的 char_outfit_id 就是这样），它就成了顶层第三个键、值是
tuple，服务器直接 AttributeError —— 节点在菜单里点不出来，日志里只有一行
`An error occurred while retrieving information for the 'XXX' node.`

这个脚本不需要 ComfyUI 环境，直接按包加载本插件，逐个节点跑同样三条检查：
  1. INPUT_TYPES() 顶层只能有 required / optional / hidden，且三个值都是 dict；
  2. required / optional 里每个控件的值必须是 tuple 或 list；
  3. RETURN_TYPES 与 RETURN_NAMES / OUTPUT_TOOLTIPS 数量一致。
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "pf_nodecheck"
TOP_OK = {"required", "optional", "hidden"}


def load():
    spec = importlib.util.spec_from_file_location(
        PKG, os.path.join(HERE, "__init__.py"), submodule_search_locations=[HERE])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    mod = load()
    bad = 0
    print(f"版本 {getattr(mod, '__version__', '?')} · 节点 {len(mod.NODE_CLASS_MAPPINGS)} 个")
    for name, cls in mod.NODE_CLASS_MAPPINGS.items():
        print(f"\n[{name}]  {mod.NODE_DISPLAY_NAME_MAPPINGS.get(name, '')}")
        try:
            d = cls.INPUT_TYPES()
        except Exception as e:
            print(f"  ✗ INPUT_TYPES() 抛异常：{type(e).__name__}: {e}")
            bad += 1
            continue
        if not isinstance(d, dict):
            print(f"  ✗ 顶层不是 dict，而是 {type(d).__name__}")
            bad += 1
            continue
        extra = [k for k in d if k not in TOP_OK]
        if extra:
            print(f"  ✗ 顶层出现非法键 {extra}（多半是写到了 required/optional 括号外面）")
            bad += 1
        for k in TOP_OK & set(d):
            if not isinstance(d[k], dict):
                print(f"  ✗ 顶层 {k} 的值是 {type(d[k]).__name__}，必须是 dict")
                bad += 1
        for k in ("required", "optional"):
            for field, val in (d.get(k) or {}).items():
                if not isinstance(val, (tuple, list)):
                    print(f"  ✗ {k}.{field} 是 {type(val).__name__}，必须是 tuple/list")
                    bad += 1
                elif not val:
                    print(f"  ✗ {k}.{field} 是空定义")
                    bad += 1
        try:
            order = {k: list(v.keys()) for k, v in d.items()}
            n_req, n_opt = len(order.get("required", [])), len(order.get("optional", []))
            print(f"  ✓ input_order 可计算（required {n_req} / optional {n_opt}）")
        except Exception as e:
            print(f"  ✗ 模拟 server 的 input_order 失败：{type(e).__name__}: {e}")
            bad += 1
        rt = getattr(cls, "RETURN_TYPES", ())
        names = getattr(cls, "RETURN_NAMES", ())
        tips = getattr(cls, "OUTPUT_TOOLTIPS", ())
        if names and len(names) != len(rt):
            print(f"  ✗ RETURN_NAMES {len(names)} 个 / RETURN_TYPES {len(rt)} 个，对不上")
            bad += 1
        if tips and len(tips) != len(rt):
            print(f"  ✗ OUTPUT_TOOLTIPS {len(tips)} 个 / RETURN_TYPES {len(rt)} 个，对不上")
            bad += 1
        for meth in ("IS_CHANGED", "run"):
            if not hasattr(cls, meth):
                print(f"  ✗ 缺方法 {meth}")
                bad += 1

    if bad:
        print(f"\n检查失败：{bad} 处问题")
        return 1
    print("\n检查通过：节点定义结构正常，ComfyUI 能取到 object_info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
