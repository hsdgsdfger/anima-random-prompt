import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openPanel } from "./prompt_forge_core_v6.js";

window.__pfFetch = (url, opt) => api.fetchApi(url, opt);

// 节点控件中文名（专有名词保留英文：JSON / danbooru / sfw 等）
const LABELS = {
  level: "档位",
  seed: "随机种子",
  tag_cap: "标签上限",
  base_prob: "基础概率",
  slot_weights: "槽位权重（JSON）",
  role_mode: "角色模式",
  role_name: "角色名",
  role_works: "限定作品",
  quality_prefix: "质量前缀",
  artist_on: "加画师标签",
  negative_on: "输出负面词",
  extra_body: "补充描述",
  quality_on: "加质量前缀",
  scene_mode: "场景模式",
  template_override: "模板覆盖文本",
  random_each_run: "每次运行重抽",
  override_mode: "覆盖模式",
};

// 输入槽中文名（forceInput 不出 widget，靠 socket label 显示）
const INPUT_LABELS = { role_prompt: "角色提示词" };

function localize(node) {
  (node.widgets || []).forEach((w) => {
    if (w && LABELS[w.name]) w.label = LABELS[w.name];
  });
  (node.inputs || []).forEach((i) => {
    if (i && INPUT_LABELS[i.name]) i.label = INPUT_LABELS[i.name];
  });
  node.setDirtyCanvas?.(true, true);
}

const LEVEL_KEYS = ["sfw", "suggestive", "explicit", "hardcore", "extreme"];

function keyOfLevel(v) {
  const s = String(v || "");
  for (const k of LEVEL_KEYS) if (s.startsWith(k)) return k;
  return s.startsWith("any") ? "any" : "sfw";
}
function labelOfLevel(key) {
  const map = {
    sfw: "sfw · 全年龄",
    suggestive: "suggestive · 擦边",
    explicit: "explicit · 成人",
    hardcore: "hardcore · 过激",
    extreme: "extreme · 极端",
    any: "any · 不限",
  };
  return map[key] || map.sfw;
}

// 程序化设值（加载工作流 / onConfigure）时不弹窗
let suppress = false;

app.registerExtension({
  name: "PromptForge.WorkbenchV7",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "PromptForgeRandom") return;

    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = origCreated ? origCreated.apply(this, arguments) : undefined;
      localize(this);
      const btn = this.addWidget("button", "⚙ 打开提示词工作台", null, () => openPanel(this));
      btn.serialize = false;
      this.setSize([Math.max(this.size[0], 320), (this.size[1] || 320) + 26]);

      // 档位切到 any 时唤起配比弹窗（REQ-107）
      const lw = (this.widgets || []).find((w) => w.name === "level");
      if (lw) {
        const node = this;
        lw._pfPrev = lw.value;

        // 下拉菜单弹出前先记下当前值，取消时按它回退
        const origMouse = lw.mouse;
        lw.mouse = function (event) {
          if (event && event.type === "mousedown") lw._pfPrev = lw.value;
          return origMouse ? origMouse.apply(this, arguments) : undefined;
        };

        const origCb = lw.callback;
        lw.callback = function (value) {
          const res = origCb ? origCb.apply(this, arguments) : undefined;
          if (!suppress && keyOfLevel(value) === "any") {
            const bridge = window.__pfBridge;
            const cfg = bridge ? (bridge.cfg || bridge.getCfg()) : null;
            if (bridge && (!cfg || cfg.auto_popup !== false)) {
              const prev = keyOfLevel(lw._pfPrev) === "any" ? labelOfLevel("sfw") : lw._pfPrev;
              bridge.openAnyPopup(node, lw, prev);
            }
          }
          lw._pfPrev = value;
          return res;
        };
      }
      return r;
    };

    const origConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      suppress = true;
      let r;
      try {
        r = origConfigure ? origConfigure.apply(this, arguments) : undefined;
      } finally {
        setTimeout(() => { suppress = false; }, 0);
      }
      localize(this);
      return r;
    };
  },
});
