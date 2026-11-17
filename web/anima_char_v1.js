import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openPanel } from "./anima_char_panel_v1.js";

window.__acFetch = (url, opt) => api.fetchApi(url, opt);

const LABELS = {
  mode: "选择模式",
  seed: "随机种子",
  role_name: "角色名",
  work_filter: "限定作品",
  include_appearance: "输出外观",
  include_outfit: "输出服装",
  outfit_level: "服装档位",
  outfit_id: "套装 id",
  extra_prompt: "补充描述",
  random_each_run: "每次运行重抽",
};

// 输出口中文说明（后端 OUTPUT_TOOLTIPS 已给一份，这里兜底老版本前端）
const OUTPUT_TIPS = {
  positive: "正向提示词：角色身份 + 官方外观 + 服装\n接 Prompt Forge 的 role_prompt，或直接接 CLIP 正向输入",
  negative: "负向提示词：通用质量负面，可以不用\n只为与图生节点的两个口对齐",
};

function localize(node) {
  (node.widgets || []).forEach((w) => {
    if (w && LABELS[w.name]) w.label = LABELS[w.name];
  });
  (node.outputs || []).forEach((o) => {
    if (o && OUTPUT_TIPS[o.name]) o.tooltip = OUTPUT_TIPS[o.name];
  });
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "AnimaCharacterPicker.Panel",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "AnimaCharacterPicker") return;

    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = origCreated ? origCreated.apply(this, arguments) : undefined;
      localize(this);
      const btn = this.addWidget("button", "🎭 打开角色库", null, () => openPanel(this));
      btn.serialize = false;
      this.setSize([Math.max(this.size[0], 340), (this.size[1] || 300) + 26]);
      return r;
    };

    const origConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = origConfigure ? origConfigure.apply(this, arguments) : undefined;
      localize(this);
      return r;
    };
  },
});
