import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openPanel } from "./prompt_forge_core_v5.js";

window.__pfFetch = (url) => api.fetchApi(url);

app.registerExtension({
  name: "PromptForge.WorkbenchV5",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "PromptForgeRandom") return;
    const orig = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = orig ? orig.apply(this, arguments) : undefined;
      const btn = this.addWidget("button", "⚙ 打开工作台 v5", null, () => openPanel(this));
      btn.serialize = false;
      this.setSize([Math.max(this.size[0], 320), (this.size[1] || 320) + 26]);
      return r;
    };
  },
});
