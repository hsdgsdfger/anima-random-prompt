# Comfyui-Prompt-Forge

> ComfyUI 自定义节点 ｜ 版本 **v0.1.6** ｜ 独立于 Anima Wardrobe V6，不依赖任何第三方库

一个插件，两个节点：

| 节点 | 干什么 |
| --- | --- |
| **Prompt Forge 随机提示词（中文）** | 按档位随机拼一整段提示词（场景成套 / 自由随机），带可视化工作台 |
| **Anima 角色选择（中文）** | 从 2432 条本地角色库里选人，输出身份 / 外观 / 服装三段，带缩略图管理面板 |

两者配套：角色节点的 `positive` 接到提示词节点的 `role_prompt`，提示词节点开
`appearance_follow` 就让出外观槽位，角色外观不会被随机覆盖。

- 安装：**只能通过 git 命令安装**，仓库不提供 Release 包
- 适用：ComfyUI（Windows / Linux），Python 3.10+

---

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/hsdgsdfger/anima-random-prompt.git Comfyui-Prompt-Forge
```

重启后节点出现在：

```
添加节点 → AnimaDecouple / Prompt Forge  → Prompt Forge 随机提示词（中文）
添加节点 → AnimaDecouple / Character    → Anima 角色选择（中文）
```

升级：`git pull` 后重启。

> 仓库 30 MB，其中 29 MB 是角色预览图。只想要提示词节点也必须一起 clone。

---

## 快速开始

1. 只想要随机提示词：加节点 `Prompt Forge 随机提示词（中文）` → 直接排队。
2. 想手选词：点节点上 **「⚙ 打开提示词工作台」**，三个页签（自由选词 / 模板卡片 / 场景包）。
3. 想固定角色：加节点 `Anima 角色选择（中文）` → 点 **「🎭 打开角色库」** 选人 →
   把 `positive` 接到提示词节点的 `role_prompt`。

---

## 一、Prompt Forge 随机提示词

### 参数

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `level` | 下拉 | `sfw · 全年龄` | sfw / suggestive / explicit / hardcore / extreme / any |
| `seed` | INT | `-1` | `-1` 每次重抽；`>=0` 可复现 |
| `tag_cap` | INT | `0` | 总标签上限，`0` = 自动（Lv0–Lv1 28 / Lv2+ 32） |
| `base_prob` | FLOAT | `0.65` | 可选槽位的基准出现概率 |
| `slot_weights` | STRING | 空 | 槽位加权 JSON，0 = 关掉该槽位 |
| `role_mode` | 下拉 | `不指定` | 不指定 / 随机 / 指定 |
| `role_name` | STRING | 空 | 指定模式下的角色名或 danbooru tag 片段 |
| `role_works` | STRING | 空 | 按作品限定随机角色，`|` 分隔 |
| `quality_prefix` | STRING | `masterpiece, best quality` | 质量前缀 |
| `artist_on` | BOOLEAN | `false` | 随机带一个画师标签 |
| `negative_on` | BOOLEAN | `true` | 输出负面提示词 |
| `extra_body` | STRING | 空 | 手写补充，拼在正向末尾 |
| `quality_on` | BOOLEAN | `true` | 是否加质量前缀 |
| `scene_mode` | 下拉 | `场景成套` | 场景成套 / 自由随机 |
| `template_override` | STRING | 空 | 覆盖文本（工作台勾选即写这里） |
| `random_each_run` | BOOLEAN | `true` | 每次运行重抽 |
| `override_mode` | 下拉 | `直通` | 直通 / 混合 |
| **`role_prompt`** | **输入槽** | 空 | 左侧连线，接角色节点输出 |
| `appearance_follow` | BOOLEAN | `true` | 角色输入非空时，发型/发色/面部/瞳色/身材让位 |
| `outfit_follow` | BOOLEAN | `false` | 角色输入非空时，服装/配饰也让位 |

> `role_prompt` 是 `forceInput`，不出 widget；其余 19 个是控件，新参数一律追加在末尾。

### 输出（一正一负）

| 输出 | 内容 |
| --- | --- |
| `positive` | 整段拼好的正向提示词 |
| `negative` | 负向提示词（关掉 `negative_on` 时为空串） |

> 档位与抽样依据不再占输出口，改打到 ComfyUI 控制台日志（`[PromptForge] …`）。
> 鼠标悬浮输出口可看到中文说明。

### 工作台

**🎛 自由选词**：分类平铺、中文对照、收藏、最近、搜索、撤销重做（20 步）、
冲突检查（室内+室外 / 水域+寒冷 / 夜景+白天 / 异种+非异种）、Token 估算。

**🗂 模板卡片**：档位筛选、场景分类、滚动加载、标签懒加载并可直接点选、
换一套（同场景）、按已选反查、套用三态确认（替换/追加/取消）。

模板一共 **1937 套**：自产 1800 套（6 档 × 300）+ 从 Anima Wardrobe V6 搬来的
**137 套场景搭配**（跨槽位配方 55 + 姿势场景 82）。档位由节点的 `level` 参数与
设置页矩阵控制，模板页只管挑内容。V6 那批在场景分类里单独归到「V6 场景搭配」。

**🏞 场景包**：45 个场景包，六类筛选，整套套用。

**⚙ 设置**：5×5 档位矩阵、any 配比、试抽直方图、导入导出、恢复默认。

---

## 二、Anima 角色选择

### 参数

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `mode` | 下拉 | `随机` | 随机 / 指定 / 收藏随机 / 多选加权 |
| `seed` | INT | `-1` | `-1` 每次重抽 |
| `role_name` | STRING | 空 | 指定模式填 tag / 英文名 / 中文名；面板点人自动写 |
| `work_filter` | STRING | 空 | 随机模式按作品限定，`|` 分隔 |
| `include_appearance` | BOOLEAN | `true` | 输出官方外观 |
| `include_outfit` | BOOLEAN | `false` | 输出服装预设 |
| `outfit_id` | STRING | 空 | 用哪一套服装；面板点套装自动填。启用一套后其余套装自动失效 |
| `extra_prompt` | STRING | 空 | 手写补充 |
| `random_each_run` | BOOLEAN | `true` | 每次运行重抽 |

### 输出（一正一负）

| 输出 | 内容 |
| --- | --- |
| `positive` | 角色身份 + 官方外观 + 服装，按开关拼成一段 → 接 `role_prompt` |
| `negative` | 一段通用质量负面（角色本身不产生负面词），可以不用 |

> 抽到谁、外观几条、服装几套，改打到控制台日志（`[CharacterPicker] …`）。

### 角色库面板

点节点上 **「🎭 打开角色库」**。2432 个角色 / 287 个作品 / 2432 张预览图。

- **左侧栏**：五个分类（全部 / 收藏 / 勾选池 / 最近 / 排除）+ 287 个作品的筛选列表
- 缩略图墙 60 张一批滚动加载，搜中英文作品均可用
- **底部条**：当前角色的缩略图、身份、外观摘要、服装下拉、复制与应用按钮
- 卡片四键：`☆` 收藏、`＋` 进勾选池、`⊘` 拉黑（随机永不出现）、`✎` 编辑
- 点卡片本体 = 选人，节点自动切「指定」并写入 `role_name`
- 勾选池页签里每张卡带权重输入（0.1–20），配「多选加权」模式
- 面板记住上次的分类与作品筛选（存 `pf_char_ui_v1`）
- 可新建原创角色、改外观、写服装套装、上传自己的预览图（自动转 webp）
- 导入导出收藏与排除名单

### 接线

```
[Anima 角色选择] positive ──→ [Prompt Forge] role_prompt
  include_outfit = 关 → 服装交给 Prompt Forge 随机（默认）
  include_outfit = 开 → 把 Prompt Forge 的 outfit_follow 也打开
```

---

## 数据规模

| 文件 | 内容 |
| --- | --- |
| `data/tags.json` | 25 分类 / 2956 条词条（589 KB） |
| `data/scenes.json` | 45 个场景包 + 互斥标记（72 KB） |
| `data/templates_ui.json` | 1800 套自产模板（1.16 MB，序号 1–1800） |
| `data/templates_v6.json` | 137 套 V6 场景搭配（序号 1801–1937，可重建） |
| `data/characters_extra.json` | 39 个补充角色（米哈游补齐，可重建） |
| `data/work_zh.json` | 250 条作品名中文映射，覆盖 92% 角色 |
| `data/tag_flags.json` | 418 条 `tag → 场景标记` 索引（18 KB，可重建） |
| `data/characters.json` | 2432 个角色 / 287 作品（1.16 MB，可重建） |
| `thumbs/` | 2432 张角色预览图（29 MB，webp） |

---

## HTTP 接口

16 个方法，两套前缀：

### `/prompt_forge/`（9 个方法）

| 路由 | 方法 | 说明 |
| --- | --- | --- |
| `/library` | GET | 全量词库 |
| `/templates` | GET | 1800 套模板，支持 `?level=` `?kind=` |
| `/scene_meta` | GET | 45 包六个布尔标记 |
| `/scenes` | GET | 45 包完整内容 |
| `/tag_flags` | GET | 冲突检查索引 |
| `/roll` | GET | 弃用，保留兼容 |
| `/roll` | POST | 接收节点全参数，返回四段 |
| `/userdata` | GET | `favorites` + `settings` |
| `/userdata` | POST | 原子写，白名单，拒绝上三角非零矩阵 |

### `/anima_char/`（7 个方法）

| 路由 | 方法 | 说明 |
| --- | --- | --- |
| `/library` | GET | `{works, characters}` 全量角色库 |
| `/state` | GET | 收藏 / 排除 / 勾选 / 权重 |
| `/state` | POST | 整体覆盖写入（原子写） |
| `/thumb/{tag}` | GET | webp 预览图（先自定义后内置） |
| `/thumb/{tag}` | POST | 上传预览图（JSON base64，只收 webp，≤ 4 MB） |
| `/char/save` | POST | 新增 / 覆盖自定义角色 |
| `/char/delete` | POST | 删除自定义角色（内置拒绝） |

---

## 目录结构

```
Comfyui-Prompt-Forge/
├── __init__.py              两个节点 + 16 个路由方法
├── engine.py                提示词抽取引擎
├── scenes.py                场景成套拼装与互斥校验
├── settings.py              档位配置（userdata/prompt_forge.json）
├── picker.py                角色选择引擎
├── char_state.py            角色收藏 / 权重 / 排除（userdata/state.json）
├── data/                    词库、场景、模板、冲突索引、角色库
├── thumbs/                  角色预览图
├── custom_thumbs/           用户上传的预览图（gitignore）
├── userdata/                运行时生成（gitignore）
├── tools/
│   ├── build_tag_flags.py   由 scenes.json 生成冲突索引
│   ├── build_characters.py  由 V6 重建角色库
│   ├── validate_data.py     数据校验（提交前必跑）
│   ├── selftest_v012.py     提示词引擎回归
│   └── routes_smoke.py      全部接口冒烟（假 PromptServer）
├── web/
│   ├── prompt_forge_v6.js           提示词节点按钮 + 中文标签 + any 弹窗
│   ├── prompt_forge_core_v6.js      提示词工作台
│   ├── anima_char_v1.js             角色节点按钮 + 中文标签
│   ├── anima_char_panel_v1.js       角色库面板
│   ├── preview.html                 提示词工作台预览
│   └── preview_char.html            角色库面板预览
├── docs/技术文档.md
└── README.md
```

---

## 开发者自检

```bash
python tools/build_tag_flags.py    # 数据改动后重建冲突索引
python tools/validate_data.py      # 25 分类 / 2956 词条 / 45 场景包 / 1800 模板
python tools/selftest_v012.py      # 档位抽样 / 覆盖模式 / 角色合并 / 配置缓存
python tools/routes_smoke.py       # 16 个接口 + 两个节点
```

重建角色库（V6 更新角色后）：

```bash
python tools/build_characters.py --v6 "路径/Comfyui-Anima-Wardrobe-V6"
python tools/build_v6_templates.py --v6 "路径/Comfyui-Anima-Wardrobe-V6"
python tools/add_mihoyo.py
python tools/fetch_thumbs.py --only mihoyo
```

- `build_v6_templates.py` 只取 V6 的 `nsfw`（跨槽位配方）与 `pose`（姿势场景）两组，
  排除含男性词的条目；想连特写/构图/武器一起要，改 `KEEP_GROUPS`。
- `add_mihoyo.py` 补米哈游四款游戏缺的女性角色，已有 tag 自动跳过，可反复跑。
- `fetch_thumbs.py` 按 tag 去 safebooru 抓预览图（缩略图，jpg，不依赖 Pillow）。
  米哈游那批已抓到 30/39，剩下 9 个源站没收录，面板显示占位。
- `verify_triggers.py` 查每个角色的 trigger tag 在 safebooru 上是否真的存在。

### 数据分层（重要）

| 位置 | 归谁 | git pull 会覆盖吗 |
| --- | --- | --- |
| `data/*.json` | 出厂数据 | **会**，这是随版本更新的 |
| `userdata/characters_extra.json` | 你自己的补充角色 | 不会 |
| `userdata/work_zh.json` | 你改的作品中文名 | 不会 |
| `userdata/templates_extra.json` | 你自建的模板 | 不会 |
| `userdata/state.json` | 收藏 / 权重 / 排除 | 不会 |
| `userdata/prompt_forge.json` | 档位矩阵 / any 配比 | 不会 |

想改出厂数据：把它从 `data/` 复制到 `userdata/` 再改，同名条目你的优先。
- `fix_template_conflicts.py` 修穿衣逻辑：全裸不穿衣、上空不穿上装、裙裤不同穿。
  `validate_data.py` 会调同一套规则，重跑生成器后立刻能查出复发。

---

## 已知限制

- 角色库是构建时快照，V6 之后新增的角色要重跑 `build_characters.py`。
- 131 个角色源数据本身没有外观，`appearance` 为空。
- 角色面板一次把 2432 条数据（1.16 MB）读进内存，首次打开约 0.3 秒。
- 词条只有「选 / 不选」，没有权重输入。
- 两个标签页同时写 `userdata` 是后写覆盖先写。
- 模板 `index` 是页码（1–200），唯一键是 `id`。

## 许可

个人使用仓库，未附带开源许可证。角色数据与预览图源自
[Comfyui-Anima-Wardrobe-V6](https://github.com/lingdongbudong/Comfyui-Anima-Wardrobe-V6)，
版权归原项目与各作品方，详见 `NOTICE.md`。
