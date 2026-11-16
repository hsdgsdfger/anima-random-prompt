import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openPanel } from "./prompt_forge_core_v6.js";

window.__pfFetch = (url) => api.fetchApi(url);

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
};

function localize(node) {
  (node.widgets || []).forEach((w) => {
    if (w && LABELS[w.name]) w.label = LABELS[w.name];
  });
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "PromptForge.WorkbenchV6",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "PromptForgeRandom") return;

    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = origCreated ? origCreated.apply(this, arguments) : undefined;
      localize(this);
      const btn = this.addWidget("button", "⚙ 打开提示词工作台", null, () => openPanel(this));
      btn.serialize = false;
      this.setSize([Math.max(this.size[0], 320), (this.size[1] || 320) + 26]);
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
