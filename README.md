# anima 随机提示词 · Prompt Forge

> ComfyUI 自定义节点 ｜ 版本 **v0.11.16** ｜ 独立于 V6，不依赖任何第三方库

一个「随机出整段提示词 + 可视化工作台手选」的 ComfyUI 节点。自带分级词库、1800 套场景模板、场景逻辑互斥校验，以及一个仿 V6 风格的网页工作台（自由选词 / 模板卡片两个页签）。

- 安装方式：**只能通过 git 命令安装**，仓库不提供 Release 包
- 适用环境：ComfyUI（Windows / Linux 均可），Python 3.10+

---

## 安装

把仓库克隆到 ComfyUI 的 `custom_nodes` 目录，然后重启 ComfyUI：

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/hsdgsdfger/anima-random-prompt.git Comfyui-Prompt-Forge
```

重启后，节点出现在：

```
添加节点 → AnimaDecouple / Prompt Forge → Prompt Forge 随机提示词 v5 工作台
```

升级：

```bash
cd ComfyUI/custom_nodes/Comfyui-Prompt-Forge
git pull
```

> 仓库不含 Release 压缩包，也不提供 Manager 一键安装；只支持 `git clone` / `git pull`。

---

## 快速开始

1. 添加节点 `Prompt Forge 随机提示词 v5 工作台`。
2. 直接排队 → 每次运行随机生成一整段正向提示词 + 负向提示词。
3. 想自己挑词：点节点底部 **「⚙ 打开工作台 v5」**，在面板里勾选，勾选即实时写回节点的 `template_override`。
4. 想用现成模板：工作台切到 **「🗂 模板卡片」**，选场景分类 → 展开标签确认 → `套用到节点`。

---

## v0.11.16 功能概览

### 节点

| 项目 | 说明 |
| --- | --- |
| 节点类 | `PromptForgeRandom` |
| 显示名 | Prompt Forge 随机提示词 v5 工作台 |
| 分类 | `AnimaDecouple/Prompt Forge` |
| 输出 | `positive` / `negative` / `level` / `report`（4 个 STRING） |
| 覆盖输入 | `template_override`（可选，填入后直接使用这段文本，跳过随机） |

### 随机引擎

- **分级**：Lv0 全年龄 / Lv1 擦边 / Lv2 成人 / Lv3 过激 / Lv4 极端，档位可调。
- **人数分档**：默认 `1girl solo`；模板命中 `2girls` 时自动补多人标签，成人向词也按单人/多人分档。
- **场景逻辑**：45 个场景包带 indoor / outdoor / water / cold / night / monster 标记，冬天不会出泳衣、室内外/水域/夜景互斥，避免"冬天在户外穿泳衣"这类荒谬组合。
- **异种**：monster 独立模板线，900 套。
- **模板**：1800 套（sfw / explicit / hardcore 各 300，monster 900），全部可在工作台里浏览。

### 可视化工作台（v5）

两个页签，与 V6 面板同构：

**🎛 自由选词**

- 左侧单列分类：`全部` / `★ 收藏` / `◷ 最近`，下方按词库**原始顺序**列出全部 25 个分类及数量。
- 右侧按分类分段平铺全部标签胶囊块，英文 + 灰色中文对照。
- 顶部 `☑ 中文对照` 开关，关闭后只显示英文（状态会记住）。
- **不按档位屏蔽**：2956 条原始词条全部可选，没有折叠隐藏、没有 level 过滤。
- 勾选即写入节点，取消勾选同步从节点文本中删掉。
- 点词条右侧 ☆ 收藏；点过的词进入「最近」（本地保存最近 20 条）。
- 搜索框同时匹配英文与中文。

**🗂 模板卡片**

- 左侧场景分类单列：全部 / 室内 / 室外 / 夜景 / 寒冷 / 水域 / 异种。
- 卡片默认**折叠**：编号 + 场景名 + 档位徽章 + 类型/人数/标签数 + `▸ 展开 N 个标签`。
- 展开后标签平铺（可滚动、可再收起），底部 `复制` / `套用到节点`。
- 每页 9 条，1800 套共 200 页；支持收藏模板、只看我的收藏。
- 顶部类型筛选：全部 / 普通 / 异种。

### 本地存储键

| 键 | 内容 |
| --- | --- |
| `pf_fav_tags_v1` | 收藏的词条 |
| `pf_fav_templates_v1` | 收藏的模板 id |
| `pf_recent_tags_v1` | 最近点过的 20 条词 |
| `pf_zh_v1` | 中文对照开关状态 |

---

## 数据规模

| 文件 | 内容 |
| --- | --- |
| `data/tags.json` | 25 分类 / 2956 条原始词条（589 KB） |
| `data/scenes.json` | 45 个场景包 + 互斥标记（72 KB） |
| `data/templates_ui.json` | 1800 套模板的精简版，供工作台展示（1.16 MB） |

---

## HTTP 接口

节点启动时注册 4 条只读路由（前缀 `/prompt_forge/`）：

| 路由 | 说明 |
| --- | --- |
| `GET /prompt_forge/library` | 返回全量词库（25 分类 / 2956 条，含中文与分级） |
| `GET /prompt_forge/templates` | 返回 1800 套模板精简数据 |
| `GET /prompt_forge/scene_meta` | 返回 45 个场景包的 indoor/outdoor/water/cold/night/monster 标记 |
| `GET /prompt_forge/roll?level=sfw` | 按档位现场随机一份，返回正/负向提示词 |

---

## 目录结构

```
Comfyui-Prompt-Forge/
├── __init__.py          # 节点注册 + 4 条路由
├── engine.py            # 随机抽取引擎
├── scenes.py            # 场景拼装与互斥校验
├── data/                # 词库、场景、模板数据
├── web/
│   ├── prompt_forge_v5.js          # ComfyUI 扩展入口（按钮 + 注册）
│   ├── prompt_forge_core_v5.js     # 工作台 UI（可独立预览）
│   └── preview.html                # 不装节点也能看界面
├── docs/技术文档.md
└── README.md
```

详细实现、参数表、约束与开发说明见 [`docs/技术文档.md`](docs/技术文档.md)。

---

## 已知限制

- 收藏 / 最近记录存在浏览器 localStorage，换浏览器或清缓存会丢；暂未做成插件侧 JSON。
- 词条目前只有"选 / 不选"，没有权重输入。
- 工作台是网页弹层，不是 ComfyUI 原生节点内部控件。
- 模板与词库为随仓库分发的静态数据，更新需 `git pull`。

## 许可

个人使用仓库，未附带开源许可证；如需公开分发请先补充 LICENSE。
