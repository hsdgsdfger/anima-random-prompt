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

function localize(node) {
  (node.widgets || []).forEach((w) => {
    if (w && LABELS[w.name]) w.label = LABELS[w.name];
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
