const acFetch = (u, opt) => (globalThis.__acFetch ? globalThis.__acFetch(u, opt) : fetch(u, opt));

/* Anima 角色库面板
   浏览（2432 角色缩略图墙）/ 搜索 / 按作品筛 / 收藏 / 排除 / 勾选加权
   选人写回节点 / 新增编辑删除角色 / 上传预览图 / 导入导出
*/
const BATCH = 60;
const UI_KEY = "pf_char_ui_v1";   // 记住上次的分类与作品筛选
const LEVEL_NAMES = ["全年龄", "擦边", "成人"];
const AP_KEYS = [
  ["hair_color", "发色"], ["hair_style", "发型"], ["eyes", "瞳色"],
  ["face", "面部"], ["body", "身材"], ["extras", "固定特征"],
];

const st = {
  node: null, tab: "all", q: "", wq: "", work: "all", shown: BATCH,
  lib: null, works: [], state: null, cur: null, editing: null,
};
const stt = { lib: "idle", state: "idle" };

/* ---------- 工具 ---------- */
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function toast(msg, ok = true) {
  const t = el("div");
  t.textContent = msg;
  t.style.cssText = `position:fixed;left:50%;bottom:56px;transform:translateX(-50%);z-index:100001;
    background:${ok ? "#1f7a4d" : "#8a2b2b"};color:#fff;padding:9px 16px;border-radius:8px;
    font:13px/1.4 system-ui,'Microsoft YaHei',sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.4);
    opacity:0;transition:opacity .15s`;
  document.body.appendChild(t);
  requestAnimationFrame(() => (t.style.opacity = "1"));
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 200); }, 1500);
}
function debounce(fn, ms) {
  let h = 0;
  return function () { clearTimeout(h); h = setTimeout(() => fn.apply(this, arguments), ms); };
}
function loadUi() {
  try { return JSON.parse(localStorage.getItem(UI_KEY)) || {}; } catch { return {}; }
}
function saveUi() {
  try {
    localStorage.setItem(UI_KEY, JSON.stringify({ tab: st.tab, work: st.work }));
  } catch {}
}
function thumbUrl(tag) {
  return `/anima_char/thumb/${encodeURIComponent(tag)}`;
}
function byTag() {
  if (!st._byTag) st._byTag = new Map((st.lib?.characters || []).map((c) => [c.tag, c]));
  return st._byTag;
}

/* ---------- 数据 ---------- */
function jfetch(url, opt) {
  return acFetch(url, opt).then((r) => {
    if (!r.ok) {
      return r.text().then((t) => { throw new Error(t.slice(0, 120) || `HTTP ${r.status}`); });
    }
    return r.json();
  });
}
function loadLib() {
  if (stt.lib === "done") return Promise.resolve();
  stt.lib = "loading";
  return jfetch("/anima_char/library").then((j) => {
    st.lib = { characters: j.characters || [] };
    st.works = j.works || [];
    st._byTag = null;
    stt.lib = "done";
  }).catch((e) => { stt.lib = "error"; throw e; });
}
function loadState() {
  if (stt.state === "done") return Promise.resolve();
  stt.state = "loading";
  return jfetch("/anima_char/state").then((j) => {
    st.state = {
      favorites: j.favorites || [], excluded: j.excluded || [],
      picked: j.picked || [], recent: j.recent || [],
      weights: j.weights || {}, settings: j.settings || { zh: true, batch: BATCH },
    };
    stt.state = "done";
  }).catch((e) => {
    stt.state = "error";
    st.state = { favorites: [], excluded: [], picked: [], recent: [], weights: {}, settings: {} };
    throw e;
  });
}
let saveTimer = 0;
let pendingBody = null;

function saveState(delay = 250) {
  if (stt.state !== "done") return;
  // 只发这一份自己负责的字段：集合已经走 toggle 逐条改了，
  // 整份 state 发上去会把别处刚改的收藏冲掉。
  pendingBody = JSON.stringify({ weights: st.state.weights, settings: st.state.settings });
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushState, delay);
}

function flushState() {
  clearTimeout(saveTimer);
  if (!pendingBody) return;
  const body = pendingBody;
  pendingBody = null;
  jfetch("/anima_char/state", {
    method: "POST", headers: { "Content-Type": "application/json" }, body,
  }).catch((e) => toast(`保存失败：${e.message || e}`, false))
    .finally(() => { if (pendingBody === body) pendingBody = null; });
}

// 关 ComfyUI / 关标签页时把还没发出去的那一次立刻送出，
// 否则防抖窗口内退出就丢收藏（用户 2026-11-17 报的「退出后数据没了」）
function flushOnExit() {
  if (!pendingBody) return;
  const body = pendingBody;
  pendingBody = null;
  try {
    navigator.sendBeacon("/anima_char/state",
      new Blob([body], { type: "application/json" }));
  } catch {
    try {
      jfetch("/anima_char/state", {
        method: "POST", headers: { "Content-Type": "application/json" }, body,
      });
    } catch {}
  }
}
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", flushOnExit);
  window.addEventListener("beforeunload", flushOnExit);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushOnExit();
  });
}

/* ---------- 写回节点 ---------- */
function widgetOf(name) {
  const real = (typeof isPromptForge === "function" && isPromptForge())
    ? (PF_WIDGET_ALIAS[name] || name) : name;
  return st.node?.widgets?.find((w) => w.name === real);
}
/* 合并后这个面板同时服务两个节点：
   AnimaCharacterPicker（mode / outfit_id / include_outfit）
   PromptForgeRandom（role_mode / char_outfit_id / outfit_follow）
   同一个动作要写到各自对应的控件上。 */
function isPromptForge() {
  return String(st.node?.type || "") === "PromptForgeRandom";
}

const PF_WIDGET_ALIAS = {
  mode: "role_mode",
  outfit_id: "char_outfit_id",
  include_outfit: "outfit_follow",
  include_appearance: "appearance_follow",
  work_filter: "role_works",
};

function setWidget(name, value) {
  const real = isPromptForge() ? (PF_WIDGET_ALIAS[name] || name) : name;
  const w = widgetOf(real);
  if (!w) return;
  w.value = value;
  if (w.inputEl) w.inputEl.value = value;
  // 合并后 role_mode 不在 required 前几位，触发一下回调让节点重算大小
  try { w.callback?.(value); } catch {}
  st.node.setDirtyCanvas?.(true, true);
}
function pickOne(tag) {
  const c = byTag().get(tag);
  if (!c) return;
  st.cur = c;
  setWidget("mode", "指定");
  setWidget("role_name", tag);
  const outs = c.outfits || [];
  setWidget("outfit_id", outs.length ? String(outs[0].id || "") : "");
  const rec = st.state.recent.filter((t) => t !== tag);
  rec.unshift(tag);
  st.state.recent = rec.slice(0, 24);
  saveState();
  renderInfo();
  renderCards();
  toast(`已选：${c.zh || c.name}`);
}
/* 集合的增删走 /anima_char/toggle：服务端读最新再改一条，
   不会被另一个标签页的旧快照整存覆盖（用户 2026-11-17 报收藏莫名少了）。
   ⚠️ jfetch 返回的已经是解析好的 JSON，不要再 .json() ——
      以前这里多写了一次 .then((r) => r.json())，于是每点一次收藏/勾选
      就弹「保存失败：r.json is not a function」（用户 2026-11-17 报）。 */
function pushToggle(key, tag, on) {
  return jfetch("/anima_char/toggle", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, tag, on }),
  }).then((j) => {
    if (j.ok && Array.isArray(j.value)) st.state[key] = j.value;
  }).catch((e) => toast(`保存失败：${e.message || e}`, false));
}

/* 批量版：把当前分类（含作品筛选与搜索词）一次性加入 / 移出勾选池。
   角色库有两千多个，逐个点不现实 —— 用户要的是「这一批里随便抽」。 */
function pushBulk(key, tags, on) {
  if (!tags.length) return Promise.resolve(0);
  return jfetch("/anima_char/bulk", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, tags, on }),
  }).then((j) => {
    if (j.ok && Array.isArray(j.value)) st.state[key] = j.value;
    return j.ok ? (j.changed ?? tags.length) : 0;
  }).catch((e) => { toast(`保存失败：${e.message || e}`, false); return 0; });
}

/* 当前筛选范围（页签 + 作品 + 搜索）的全部角色，不含被排除的 */
function scopeTags() {
  const ban = new Set(st.state.excluded || []);
  return currentList().map((c) => c.tag).filter((t) => !ban.has(t));
}

function addScopeToPool() {
  const tags = scopeTags();
  if (!tags.length) { toast("当前分类没有可加入的角色", false); return; }
  const have = new Set(st.state.picked || []);
  const add = tags.filter((t) => !have.has(t));
  if (!add.length) { toast(`当前分类的 ${tags.length} 个角色都已在勾选池里`); return; }
  pushBulk("picked", add, true).then((n) => {
    if (!n) return;
    // 勾选池有货就把节点模式切到「多选加权」，否则随机还是走全库，等于白加
    if (!(st.state.picked || []).length) return;
    setWidget("mode", "多选加权");
    renderTabs(); renderCards(); renderInfo();
    toast(`已把 ${n} 个角色加入勾选池（共 ${st.state.picked.length} 个），节点模式已切到「多选加权」`);
  });
}

function removeScopeFromPool() {
  const tags = scopeTags();
  const have = new Set(st.state.picked || []);
  const drop = tags.filter((t) => have.has(t));
  if (!drop.length) { toast("当前分类没有已勾选的角色", false); return; }
  pushBulk("picked", drop, false).then((n) => {
    if (!n) return;
    renderTabs(); renderCards(); renderInfo();
    toast(`已从勾选池移出 ${drop.length} 个角色`);
  });
}

function toggleFav(tag) {
  const on = !st.state.favorites.includes(tag);
  st.state.favorites = on
    ? [tag, ...st.state.favorites.filter((x) => x !== tag)]
    : st.state.favorites.filter((x) => x !== tag);
  pushToggle("favorites", tag, on);
  renderTabs();
  renderCards();
}
function toggleBan(tag) {
  const on = !st.state.excluded.includes(tag);
  st.state.excluded = on
    ? [tag, ...st.state.excluded.filter((x) => x !== tag)]
    : st.state.excluded.filter((x) => x !== tag);
  if (on) {
    st.state.picked = st.state.picked.filter((x) => x !== tag);
    pushToggle("picked", tag, false);
  }
  pushToggle("excluded", tag, on);
  renderTabs();
  renderCards();
  renderInfo();
}
function togglePick(tag) {
  const on = !st.state.picked.includes(tag);
  st.state.picked = on
    ? [tag, ...st.state.picked.filter((x) => x !== tag)]
    : st.state.picked.filter((x) => x !== tag);
  if (on) {
    st.state.weights[tag] = st.state.weights[tag] || 1;
  } else {
    delete st.state.weights[tag];
  }
  if (st.state.picked.length) setWidget("mode", "多选加权");
  pushToggle("picked", tag, on);
  saveState();          // weights 变了，单独存一次（只发 weights/settings）
  renderTabs();
  renderCards();
  renderInfo();
}

/* ---------- 面板 ---------- */
let panel = null;
function closePanel() {
  if (!panel) return;
  if (panel.keyHandler) window.removeEventListener("keydown", panel.keyHandler, true);
  panel.root.remove();
  panel = null;
  st.cur = null;
  st.editing = null;
}

/* 集合类页签：按「我自己挑的」定义的，不受作品筛选裁剪。
   以前收藏/勾选池会被上次记住的作品筛选再切一刀，6 个勾选只显示 3 个
   （用户 2026-11-17 报「勾选池只出来三个」），看起来就像数据丢了。 */
const COLLECTION_TABS = ["fav", "picked", "recent", "excluded"];

function currentList() {
  const q = st.q.trim().toLowerCase();
  let items = st.lib?.characters || [];
  if (st.tab === "fav") items = items.filter((c) => st.state.favorites.includes(c.tag));
  else if (st.tab === "picked") items = items.filter((c) => st.state.picked.includes(c.tag));
  else if (st.tab === "excluded") items = items.filter((c) => st.state.excluded.includes(c.tag));
  else if (st.tab === "recent") {
    const order = st.state.recent;
    items = order.map((t) => byTag().get(t)).filter(Boolean);
  }
  if (st.work !== "all" && !COLLECTION_TABS.includes(st.tab)) {
    items = items.filter((c) => c.work === st.work);
  }
  if (q) {
    items = items.filter((c) =>
      c.tag.includes(q) || (c.name || "").toLowerCase().includes(q) ||
      (c.zh || "").includes(q) || (c.trigger || "").toLowerCase().includes(q) ||
      (c.work || "").includes(q));
  }
  return items;
}

function cardOf(c) {
  const fav = st.state.favorites.includes(c.tag);
  const ban = st.state.excluded.includes(c.tag);
  const picked = st.state.picked.includes(c.tag);
  const card = el("div", "ccard" + (ban ? " ban" : "") + (st.cur && st.cur.tag === c.tag ? " cur" : ""));
  card.dataset.tag = c.tag;

  const box = el("div", "cthumb");
  const img = el("img");
  img.loading = "lazy";
  img.src = thumbUrl(c.tag);
  img.onerror = () => { img.style.display = "none"; box.classList.add("noimg"); };
  box.appendChild(img);
  if (c.custom) box.appendChild(el("span", "ctag", "自定"));
  card.appendChild(box);

  const nm = el("div", "cname", c.zh || c.name || c.tag);
  card.appendChild(nm);
  const wk = el("div", "cwork", c.work || "—");
  card.appendChild(wk);

  // 勾选池页签里每张卡带权重输入（多选加权模式用）
  if (st.tab === "picked") {
    const wrow = el("div", "wrow");
    wrow.appendChild(el("span", "wl", "权重"));
    const wi = el("input", "winput");
    wi.type = "number";
    wi.min = "0.1"; wi.max = "20"; wi.step = "0.1";
    wi.value = String(st.state.weights[c.tag] ?? 1);
    wi.onclick = (e) => e.stopPropagation();
    wi.onchange = () => {
      const v = Math.max(0.1, Math.min(20, Number(wi.value) || 1));
      st.state.weights[c.tag] = Math.round(v * 10) / 10;
      wi.value = String(st.state.weights[c.tag]);
      saveState();
    };
    wrow.appendChild(wi);
    card.appendChild(wrow);
  }

  const ops = el("div", "cops");
  const bFav = el("span", "op" + (fav ? " on" : ""), fav ? "★" : "☆");
  bFav.title = "收藏";
  bFav.onclick = (e) => { e.stopPropagation(); toggleFav(c.tag); };
  const bPick = el("span", "op" + (picked ? " on" : ""), picked ? "✓" : "＋");
  bPick.title = "加入勾选池（多选加权）";
  bPick.onclick = (e) => { e.stopPropagation(); togglePick(c.tag); };
  const bBan = el("span", "op" + (ban ? " on" : ""), "⊘");
  bBan.title = ban ? "取消排除" : "排除（随机时不再出现）";
  bBan.onclick = (e) => { e.stopPropagation(); toggleBan(c.tag); };
  const bEdit = el("span", "op", "✎");
  bEdit.title = "编辑 / 上传预览图";
  bEdit.onclick = (e) => { e.stopPropagation(); openEditor(c); };
  ops.appendChild(bFav); ops.appendChild(bPick); ops.appendChild(bBan); ops.appendChild(bEdit);
  card.appendChild(ops);

  card.onclick = () => pickOne(c.tag);
  return card;
}

function renderCards() {
  if (!panel?.cards) return;
  const items = currentList();
  const shown = items.slice(0, st.shown);
  panel.cards.innerHTML = "";
  if (!items.length) {
    panel.cards.appendChild(el("div", "empty",
      st.tab === "fav" ? "收藏夹是空的，点卡片右上角 ☆ 收藏"
        : st.tab === "picked" ? "勾选池是空的，点 ＋ 加入"
          : st.tab === "excluded" ? "还没有排除任何角色"
            : "没有匹配的角色"));
  }
  shown.forEach((c) => panel.cards.appendChild(cardOf(c)));
  if (panel.footInfo) {
    panel.footInfo.textContent = items.length > shown.length
      ? `已显示 ${shown.length} / ${items.length} · 继续下滑加载`
      : `共 ${items.length} 个角色`;
  }
}
function appendCards() {
  const items = currentList();
  if (st.shown >= items.length) return;
  const end = Math.min(items.length, st.shown + BATCH);
  for (let i = st.shown; i < end; i++) panel.cards.appendChild(cardOf(items[i]));
  st.shown = end;
  renderCardsFootOnly(items.length);
}
function renderCardsFootOnly(total) {
  if (panel?.footInfo) {
    panel.footInfo.textContent = total > st.shown
      ? `已显示 ${st.shown} / ${total} · 继续下滑加载`
      : `共 ${total} 个角色`;
  }
}
function resetList() {
  st.shown = BATCH;
  if (panel?.cards) panel.cards.scrollTop = 0;
  refreshWorkHl();
  renderCards();
}

/* 只切作品行的选中态，不重建整个列表（288 行，切页签时重建太浪费） */
function refreshWorkHl() {
  if (!panel?.workList) return;
  const isColl = COLLECTION_TABS.includes(st.tab);
  panel.workList.querySelectorAll(".workrow").forEach((row) => {
    const on = isColl ? row.dataset.wid === "all" : row.dataset.wid === st.work;
    row.classList.toggle("on", on);
  });
}

function renderTabs() {
  if (!panel?.nav) return;
  const s = st.state || {};
  const counts = {
    all: st.lib?.characters.length || 0,
    fav: (s.favorites || []).length,
    picked: (s.picked || []).length,
    excluded: (s.excluded || []).length,
    recent: (s.recent || []).length,
  };
  panel.nav.querySelectorAll(".nav").forEach((t) => {
    const k = t.dataset.k;
    t.classList.toggle("on", st.tab === k);
    const n = t.querySelector(".n");
    if (n) n.textContent = String(counts[k] ?? 0);
  });
}

function renderWorks() {
  if (!panel?.workList) return;
  const box = panel.workList;
  const q = st.wq.trim().toLowerCase();
  const list = (st.works || []).filter((w) =>
    !q || w.id.includes(q) || (w.name || "").toLowerCase().includes(q) || (w.zh || "").includes(q));
  box.innerHTML = "";
  // 集合类页签不按作品筛，左侧就高亮「全部作品」，避免以为筛选还生效
  const isColl = COLLECTION_TABS.includes(st.tab);
  const mk = (id, label, count) => {
    const row = el("div", "workrow" + ((isColl ? id === "all" : st.work === id) ? " on" : ""));
    row.dataset.wid = id;
    row.appendChild(el("span", "wn", label));
    row.appendChild(el("span", "wc", String(count)));
    // 集合页签下点作品：自动回到「全部」再按该作品筛，否则点了没反应
    row.onclick = () => {
      st.work = id;
      st.shown = BATCH;
      if (id !== "all" && COLLECTION_TABS.includes(st.tab)) st.tab = "all";
      saveUi(); renderTabs(); renderWorks(); renderCards();
    };
    box.appendChild(row);
  };
  const total = (st.lib?.characters || []).length;
  mk("all", "全部作品", total);
  list.forEach((w) => mk(w.id, w.zh || w.name || w.id, w.count));
}

function renderInfo() {
  if (!panel?.info) return;
  const box = panel.info;
  box.innerHTML = "";
  const cur = st.cur;
  if (!cur) {
    const n = (st.state && st.state.picked) ? st.state.picked.length : 0;
    box.appendChild(el("span", "hint-inline",
      n ? `勾选池 ${n} 个 · 切到「勾选池」页签可逐个调权重，节点模式选「多选加权」`
        : "点卡片选人；选完节点自动切「指定」模式"));
    return;
  }
  const img = el("img", "ifo-thumb");
  img.src = thumbUrl(cur.tag);
  img.onerror = () => { img.style.visibility = "hidden"; };
  box.appendChild(img);

  const meta = el("div", "ifo-meta");
  meta.appendChild(el("b", null, cur.zh || cur.name || cur.tag));
  meta.appendChild(el("span", "ifo-sub",
    `${cur.tag} · ${cur.work || "—"}`));
  box.appendChild(meta);

  const ap = [];
  const A = AP_KEYS.map(([k]) => k);
  A.forEach((k) => { const v = (cur.appearance || {})[k]; if (v && v.length) ap.push(...v); });
  const apSpan = el("span", "ifo-ap", ap.length ? ap.join(", ") : "无外观数据");
  box.appendChild(apSpan);

  const outs = cur.outfits || [];
  if (outs.length) {
    const sel = el("select", "ifo-sel");
    const curId = String(widgetOf("outfit_id")?.value || "");
    outs.forEach((o) => {
      const op = el("option", null, o.zh || o.id);
      op.value = String(o.id || "");
      if (op.value === curId) op.selected = true;
      sel.appendChild(op);
    });
    sel.onchange = () => {
      setWidget("outfit_id", sel.value);
      setWidget("include_outfit", true);
      toast("已启用这套服装，其余套装自动失效");
    };
    box.appendChild(sel);
  }

  const b1 = el("span", "ifo-btn", "复制");
  b1.onclick = () => copyText(cur.trigger);
  const b2 = el("span", "ifo-btn main", "应用到节点");
  b2.onclick = () => pickOne(cur.tag);
  box.appendChild(b1); box.appendChild(b2);
}


function copyText(text) {
  const done = () => toast("已复制");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, () => {});
  else toast("复制失败", false);
}

/* ---------- 编辑弹窗 ---------- */
function openEditor(c) {
  const rec = JSON.parse(JSON.stringify(c || {
    tag: "", name: "", zh: "", work: "", trigger: "", pop: 0,
    appearance: {}, outfits: [],
  }));
  st.editing = rec;
  const isNew = !c;
  const mask = el("div", "ac-mask2");
  const win = el("div", "ac-edit");

  const h = el("div", "eh");
  h.appendChild(el("b", null, isNew ? "新建角色" : `编辑：${rec.zh || rec.name || rec.tag}`));
  const x = el("span", "x", "✕");
  x.onclick = () => mask.remove();
  h.appendChild(x);
  win.appendChild(h);

  const body = el("div", "ebody");
  const field = (label, key, ph = "") => {
    const row = el("div", "frow");
    row.appendChild(el("span", "fl", label));
    const inp = el("input", "fi");
    inp.value = rec[key] || "";
    inp.placeholder = ph;
    inp.oninput = () => { rec[key] = inp.value; };
    row.appendChild(inp);
    body.appendChild(row);
    return inp;
  };
  const tagInput = field("tag（英文唯一键）", "tag", "如 my_original_girl");
  field("英文名", "name", "my original girl");
  field("中文名", "zh", "我的原创角色");
  field("作品", "work", "original");
  field("触发词（输出用）", "trigger", "my original girl");

  body.appendChild(el("div", "sub-t", "官方外观（英文 tag，逗号分隔）"));
  const apInputs = {};
  AP_KEYS.forEach(([k, label]) => {
    const row = el("div", "frow");
    row.appendChild(el("span", "fl", label));
    const inp = el("input", "fi");
    inp.value = ((rec.appearance || {})[k] || []).join(", ");
    inp.oninput = () => {
      const arr = inp.value.split(",").map((s) => s.trim()).filter(Boolean);
      rec.appearance = rec.appearance || {};
      if (arr.length) rec.appearance[k] = arr; else delete rec.appearance[k];
    };
    row.appendChild(inp);
    body.appendChild(row);
    apInputs[k] = inp;
  });

  body.appendChild(el("div", "sub-t", "服装套装（一套一行：id|中文名|档位0-2|tag1, tag2）"));
  const ofArea = el("textarea", "fta");
  ofArea.value = (rec.outfits || [])
    .map((o) => [o.id || "default", o.zh || "", String(o.level ?? 0), (o.tags || []).join(", ")].join("|"))
    .join("\n");
  body.appendChild(ofArea);

  const up = el("div", "urow");
  up.appendChild(el("span", "fl", "预览图"));
  const file = el("input");
  file.type = "file";
  file.accept = "image/*";
  up.appendChild(file);
  const upHint = el("span", "hint", "选图后自动转成 webp 上传");
  up.appendChild(upHint);
  body.appendChild(up);

  file.onchange = () => {
    const f = file.files && file.files[0];
    if (!f) return;
    if (!rec.tag) { toast("先填 tag 再上传预览图", false); return; }
    upHint.textContent = "转换中…";
    toWebp(f).then((b64) => jfetch(`/anima_char/thumb/${encodeURIComponent(rec.tag)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: b64 }),
    })).then(() => { upHint.textContent = "已上传"; toast("预览图已更新"); })
      .catch((e) => { upHint.textContent = "上传失败"; toast(String(e.message || e), false); });
  };

  const foot = el("div", "efoot");
  if (!isNew) {
    const del = el("div", "btn danger", "删除这个自定义角色");
    del.onclick = () => {
      jfetch("/anima_char/char/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag: rec.tag }),
      }).then(() => {
        toast("已删除");
        mask.remove();
        refreshLibrary();
      }).catch((e) => toast(String(e.message || e), false));
    };
    foot.appendChild(del);
  }
  const cancel = el("div", "btn", "取消");
  cancel.onclick = () => mask.remove();
  const save = el("div", "btn main", "保存");
  save.onclick = () => {
    if (!tagInput.value.trim()) { toast("tag 不能为空", false); return; }
    rec.outfits = ofArea.value.split("\n").map((line) => {
      const parts = line.split("|");
      if (parts.length < 4) return null;
      const tags = parts.slice(3).join("|").split(",").map((s) => s.trim()).filter(Boolean);
      if (!tags.length) return null;
      return { id: parts[0].trim() || "default", zh: parts[1].trim(),
               level: Math.max(0, Math.min(2, parseInt(parts[2], 10) || 0)), tags };
    }).filter(Boolean);
    jfetch("/anima_char/char/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rec),
    }).then(() => {
      toast("已保存");
      mask.remove();
      refreshLibrary();
    }).catch((e) => toast(String(e.message || e), false));
  };
  foot.appendChild(cancel); foot.appendChild(save);
  win.appendChild(body);
  win.appendChild(foot);
  mask.appendChild(win);
  mask.addEventListener("mousedown", (e) => { if (e.target === mask) mask.remove(); });
  document.body.appendChild(mask);
  tagInput.focus();
}

function toWebp(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const max = 320;
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const cv = document.createElement("canvas");
      cv.width = w; cv.height = h;
      cv.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      const data = cv.toDataURL("image/webp", 0.86).split(",")[1];
      if (!data) reject(new Error("这个浏览器不支持转 webp"));
      else resolve(data);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("图片读不出来")); };
    img.src = url;
  });
}

function refreshLibrary() {
  stt.lib = "idle";
  stt.state = "idle";
  Promise.all([loadLib(), loadState()]).then(() => {
    renderTabs(); renderCards(); renderInfo();
  }).catch((e) => toast(`刷新失败：${e.message || e}`, false));
}

/* ---------- 导入导出 ---------- */
function openIo() {
  const mask = el("div", "ac-mask2");
  const win = el("div", "ac-edit");
  const h = el("div", "eh");
  h.appendChild(el("b", null, "导入 / 导出"));
  const x = el("span", "x", "✕");
  x.onclick = () => mask.remove();
  h.appendChild(x);
  win.appendChild(h);

  const body = el("div", "ebody");
  body.appendChild(el("div", "hint", "导出的内容：收藏 / 排除名单 / 勾选池 / 权重。自定义角色在保存时已写入插件目录。"));
  const ta = el("textarea", "fta big");
  win.appendChild(body);
  body.appendChild(ta);

  const foot = el("div", "efoot");
  const ex = el("div", "btn", "导出到剪贴板");
  ex.onclick = () => {
    ta.value = JSON.stringify(st.state, null, 2);
    copyText(ta.value);
  };
  const im = el("div", "btn main", "导入上面的内容");
  im.onclick = () => {
    try {
      const j = JSON.parse(ta.value);
      st.state = {
        favorites: j.favorites || [], excluded: j.excluded || [],
        picked: j.picked || [], recent: j.recent || [],
        weights: j.weights || {}, settings: j.settings || {},
      };
      saveState(0);
      renderTabs(); renderCards(); renderInfo();
      mask.remove();
      toast("已导入");
    } catch {
      toast("不是合法 JSON", false);
    }
  };
  const cc = el("div", "btn", "关闭");
  cc.onclick = () => mask.remove();
  foot.appendChild(ex); foot.appendChild(im); foot.appendChild(cc);
  win.appendChild(foot);
  mask.appendChild(win);
  mask.addEventListener("mousedown", (e) => { if (e.target === mask) mask.remove(); });
  document.body.appendChild(mask);
}

/* ---------- 骨架 ---------- */
function errBlock(label, retry) {
  const box = el("div", "errbox");
  box.appendChild(el("div", "em", `${label}加载失败`));
  box.appendChild(el("div", "eh", "后端没响应，确认 ComfyUI 已重启并加载本插件。"));
  const b = el("div", "btn main", "重试");
  b.style.flex = "0 0 90px";
  b.onclick = () => { box.innerHTML = ""; box.appendChild(el("div", "empty", "重试中…")); retry(); };
  box.appendChild(b);
  return box;
}

function openPanel(node) {
  closePanel();
  st.node = node;
  if (!st.state) {
    st.state = { favorites: [], excluded: [], picked: [], recent: [], weights: {}, settings: {} };
  }
  const curName = String(widgetOf("role_name")?.value || "");
  st.cur = byTag().get(curName) || null;
  st.tab = "all"; st.q = ""; st.work = "all"; st.shown = BATCH;

  const root = el("div", "ac-mask");
  const win = el("div", "ac-win");
  root.appendChild(win);

  const head = el("div", "ac-head");
  const logo = el("div", "logo");
  logo.innerHTML = "🎭 角色库 <small>点卡片即选人</small>";
  head.appendChild(logo);
  head.appendChild(el("div", "grow"));

  const search = el("input", "search");
  search.placeholder = "搜名字 / tag / 作品";
  const doSearch = debounce(() => { st.shown = BATCH; renderCards(); }, 150);
  search.oninput = () => { st.q = search.value; doSearch(); };
  head.appendChild(search);

  const ioBtn = el("span", "icobtn", "⇄");
  ioBtn.title = "导入 / 导出";
  ioBtn.onclick = openIo;
  head.appendChild(ioBtn);

  const newBtn = el("span", "icobtn", "＋");
  newBtn.title = "新建角色";
  newBtn.onclick = () => openEditor(null);
  head.appendChild(newBtn);

  const x = el("span", "x", "✕");
  x.onclick = closePanel;
  head.appendChild(x);
  win.appendChild(head);

  const body = el("div", "ac-body");

  // 左侧栏：分类 + 作品
  const side = el("div", "ac-side");
  const nav = el("div", "ac-nav");
  [["all", "全部"], ["fav", "收藏"], ["picked", "勾选池"], ["recent", "最近"], ["excluded", "排除"]]
    .forEach(([k, label]) => {
      const t = el("div", "nav" + (k === "all" ? " on" : ""));
      t.dataset.k = k;
      t.appendChild(el("span", "nn", label));
      t.appendChild(el("span", "n", "0"));
      t.onclick = () => { st.tab = k; saveUi(); renderTabs(); resetList(); };
      nav.appendChild(t);
    });
  side.appendChild(nav);

  const wq = el("input", "wq");
  wq.placeholder = "筛作品…";
  wq.oninput = () => { st.wq = wq.value; renderWorks(); };
  side.appendChild(wq);
  const workList = el("div", "worklist");
  side.appendChild(workList);

  // 当前分类批量入池：两千多个角色逐个点 ＋ 不现实，
  // 「这一批里随便抽」才是多选加权真正好用的地方。
  const sideOps = el("div", "side-ops");
  const addBtn = el("div", "sbtn main", "＋ 当前分类全加入勾选池");
  addBtn.title = "把当前页签 + 作品筛选 + 搜索范围内的全部角色一次性加入勾选池（排除名单里的跳过）；加入后节点模式自动切「多选加权」";
  addBtn.onclick = addScopeToPool;
  const rmBtn = el("div", "sbtn", "－ 从勾选池移出当前分类");
  rmBtn.title = "把当前筛选范围内的角色从勾选池里移出（误点全加的撤销）";
  rmBtn.onclick = removeScopeFromPool;
  const hint = el("div", "shint", "范围 = 当前页签 + 作品 + 搜索词");
  sideOps.appendChild(addBtn);
  sideOps.appendChild(rmBtn);
  sideOps.appendChild(hint);
  side.appendChild(sideOps);
  body.appendChild(side);

  const cards = el("div", "cards");
  cards.onscroll = () => {
    if (cards.scrollTop + cards.clientHeight >= cards.scrollHeight - 240) appendCards();
  };
  body.appendChild(cards);
  win.appendChild(body);

  const foot = el("div", "ac-foot");
  const info = el("div", "ac-info");
  const footInfo = el("div", "ac-count");
  foot.appendChild(info);
  foot.appendChild(footInfo);
  win.appendChild(foot);

  panel = { root, win, cards, nav, workList, info, footInfo, tabs: nav, keyHandler: null };
  renderTabs();
  renderInfo();

  document.body.appendChild(root);
  root.addEventListener("mousedown", (e) => { if (e.target === root) closePanel(); });

  const keyHandler = (e) => {
    if (!panel) return;
    if (e.key === "Escape") {
      const m = document.querySelector(".ac-mask2");
      if (m) m.remove(); else closePanel();
      e.stopPropagation();
    } else if (e.key.toLowerCase() === "f" && (e.ctrlKey || e.metaKey)) {
      search.focus(); search.select();
      e.preventDefault(); e.stopPropagation();
    }
  };
  panel.keyHandler = keyHandler;
  window.addEventListener("keydown", keyHandler, true);

  const fillWorks = () => {
    // 记住的作品可能已经不在了（用户删了自定义角色），回落到「全部」
    if (st.work !== "all" && !(st.works || []).some((w) => w.id === st.work)) {
      st.work = "all";
      saveUi();
    }
    renderWorks();
  };

  Promise.all([loadLib(), loadState()]).then(() => {
    if (!panel) return;
    fillWorks();
    renderTabs();
    renderCards();
    if (!st.cur) {
      const curName2 = String(widgetOf("role_name")?.value || "");
      st.cur = byTag().get(curName2) || null;
    }
    renderInfo();
  }).catch((e) => {
    if (!panel) return;
    cards.innerHTML = "";
    cards.appendChild(errBlock("角色库", () => { stt.lib = "idle"; stt.state = "idle"; refreshLibrary(); }));
    void e;
  });
}

/* ---------- CSS ---------- */
const CSS = `
.ac-mask{position:fixed;inset:0;background:rgba(0,0,0,.58);z-index:99999;display:flex;align-items:center;justify-content:center}
.ac-win{width:min(1420px,96vw);height:min(860px,92vh);background:#1b1c21;border:1px solid #2e3037;border-radius:14px;
  display:flex;flex-direction:column;overflow:hidden;color:#e3e6ec;box-shadow:0 24px 80px rgba(0,0,0,.65);
  font:13px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
.ac-win .ac-head{display:flex;align-items:center;gap:10px;padding:0 16px;height:58px;border-bottom:1px solid #2e3037;flex:0 0 auto}
.ac-win .logo{font-weight:700;color:#e6b45c;white-space:nowrap}
.ac-win .logo small{color:#666c77;font-weight:400;margin-left:6px}
.ac-win .tabs{display:flex;gap:5px;margin-left:8px}
.ac-win .tab{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:9px;background:#22242a;
  color:#8d939e;cursor:pointer;border:1px solid transparent;font-size:12.5px}
.ac-win .tab .n{color:#666c77;font-size:11px}
.ac-win .tab.on{background:linear-gradient(180deg,#2b2e36,#24262c);color:#fff;border-color:#e6b45c;box-shadow:inset 0 -2px 0 #e6b45c}
.ac-win .grow{flex:1}
.ac-win .sel{padding:6px 9px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;max-width:200px}
.ac-win .search{width:210px;padding:6px 11px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;outline:none}
.ac-win .search::placeholder{color:#666c77}
.ac-win .icobtn{width:30px;height:30px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#b9c1cd;
  display:grid;place-items:center;cursor:pointer;font-size:15px}
.ac-win .icobtn:hover{border-color:#4a4e59;color:#fff}
.ac-win .x{width:30px;height:30px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#8d939e;
  display:grid;place-items:center;cursor:pointer}
.ac-win .ac-body{flex:1;display:flex;min-height:0}
.ac-win .cards{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-wrap:wrap;gap:11px;align-content:flex-start}
.ac-win .ccard{width:132px;background:#202127;border:1px solid #2e3037;border-radius:11px;overflow:hidden;
  cursor:pointer;display:flex;flex-direction:column;position:relative}
.ac-win .ccard:hover{border-color:#4a4e59}
.ac-win .ccard.cur{border-color:#3f8f6f;box-shadow:0 0 0 1px rgba(63,143,111,.45) inset}
.ac-win .ccard.ban{opacity:.4}
.ac-win .cthumb{width:100%;aspect-ratio:1/1;background:#16171b;display:flex;align-items:center;justify-content:center;position:relative}
.ac-win .cthumb img{width:100%;height:100%;object-fit:cover;display:block}
.ac-win .cthumb.noimg::after{content:"无预览";color:#4a4e59;font-size:11px}
.ac-win .ctag{position:absolute;left:5px;top:5px;background:rgba(79,60,184,.85);color:#fff;font-size:9.5px;
  padding:1px 5px;border-radius:4px}
.ac-win .cname{font-size:12px;color:#e3e6ec;padding:6px 8px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ac-win .cwork{font-size:10.5px;color:#666c77;padding:1px 8px 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ac-win .cops{display:flex;gap:2px;padding:0 6px 7px;margin-top:auto}
.ac-win .cops .op{width:22px;height:22px;border-radius:6px;display:grid;place-items:center;font-size:12px;
  color:#666c77;background:#23252b;border:1px solid #2f323a}
.ac-win .cops .op:hover{color:#e3e6ec;border-color:#4a4e59}
.ac-win .cops .op.on{color:#e6b45c;border-color:#6d5733;background:rgba(230,180,92,.12)}
.ac-win .right{width:320px;border-left:1px solid #2e3037;background:#191a1f;display:flex;flex-direction:column;
  overflow:auto;padding:0 0 12px}
.ac-win .r-h{display:flex;align-items:center;gap:8px;padding:11px 14px;border-bottom:1px solid #2e3037;font-size:13px}
.ac-win .r-h b{color:#e3e6ec}
.ac-win .r-h .grow{flex:1}
.ac-win .mini{color:#e6b45c;font-size:11px;cursor:pointer}
.ac-win .rthumb{margin:12px 14px 0;border-radius:10px;overflow:hidden;background:#16171b;aspect-ratio:1/1;
  display:flex;align-items:center;justify-content:center}
.ac-win .rthumb img{width:100%;height:100%;object-fit:cover}
.ac-win .rmeta{padding:10px 14px 4px;font-size:11.5px;color:#8d939e;display:flex;flex-direction:column;gap:3px}
.ac-win .rsec{padding:8px 14px 0}
.ac-win .sub-t{color:#b9c1cd;font-size:11.5px;font-weight:600;margin-bottom:5px}
.ac-win .aprow{display:flex;gap:6px;font-size:11px;line-height:1.55}
.ac-win .aprow .k{flex:0 0 44px;color:#666c77}
.ac-win .aprow .v{color:#aeb6c2}
.ac-win .orow{display:flex;align-items:center;gap:7px;padding:4px 6px;border-radius:7px;cursor:pointer;font-size:11.5px}
.ac-win .orow:hover{background:#212329}
.ac-win .opick{color:#666c77;font-size:10px}
.ac-win .orow:hover .opick{color:#e6b45c}
.ac-win .onm{color:#cfd5df}
.ac-win .hint{color:#666c77;font-size:11.5px;padding:8px 14px;line-height:1.6}
.ac-win .picked-list{padding:4px 14px}
.ac-win .prow{display:flex;align-items:center;gap:7px;padding:3px 0;font-size:11.5px}
.ac-win .prow .pn{flex:1;color:#cfd5df;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ac-win .winput{width:54px;padding:2px 5px;border-radius:6px;background:#23252b;border:1px solid #383b43;
  color:#e3e6ec;font-size:11px;text-align:center}
.ac-win .rbtns{display:flex;gap:8px;padding:12px 14px 0;margin-top:auto}
.ac-win .btn{flex:1;text-align:center;padding:7px 10px;border-radius:9px;background:#262931;border:1px solid #3a3e48;
  color:#dde2ea;cursor:pointer;font-size:12px}
.ac-win .btn:hover{border-color:#4a4e59}
.ac-win .btn.main{background:linear-gradient(180deg,#3f8f6f,#35795d);border-color:#4aa17c;color:#fff;font-weight:600}
.ac-win .ac-foot{padding:8px 16px;border-top:1px solid #2e3037;color:#666c77;font-size:11px;flex:0 0 auto}
.ac-win .empty{color:#666c77;padding:24px;font-size:12px}
.ac-win .errbox{margin:24px;padding:18px;border:1px solid #5a2f2f;background:rgba(138,43,43,.12);border-radius:10px;
  display:flex;flex-direction:column;gap:10px;align-items:flex-start}
.ac-win .errbox .em{color:#f0a9a9;font-weight:600}
.ac-win .errbox .eh{color:#8d939e;font-size:12px}

.ac-win .ac-side{width:212px;border-right:1px solid #2e3037;background:#191a1f;display:flex;flex-direction:column;flex:0 0 auto}
.ac-win .ac-nav{padding:8px 8px 4px;display:flex;flex-direction:column;gap:2px}
.ac-win .nav{display:flex;align-items:center;gap:7px;padding:7px 10px;border-radius:8px;color:#8d939e;cursor:pointer;font-size:12.5px}
.ac-win .nav:hover{background:#212329;color:#e3e6ec}
.ac-win .nav.on{background:#262931;color:#fff;box-shadow:inset 2px 0 0 #e6b45c}
.ac-win .nav .nn{flex:1}
.ac-win .nav .n{color:#666c77;font-size:11px}
.ac-win .wq{margin:6px 10px 4px;padding:5px 9px;border-radius:7px;background:#23252b;border:1px solid #383b43;
  color:#e3e6ec;font-size:11.5px;outline:none}
.ac-win .worklist{flex:1;overflow:auto;padding:0 8px 10px}
.ac-win .workrow{display:flex;align-items:center;gap:6px;padding:5px 9px;border-radius:7px;cursor:pointer;
  color:#8d939e;font-size:11.5px}
.ac-win .workrow:hover{background:#212329;color:#e3e6ec}
.ac-win .workrow.on{background:#262931;color:#e6b45c}
.ac-win .workrow .wn{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ac-win .workrow .wc{color:#666c77;font-size:10.5px}
.ac-win .side-ops{flex:0 0 auto;padding:8px;border-top:1px solid #2e3037;display:flex;flex-direction:column;gap:6px}
.ac-win .side-ops .sbtn{padding:7px 9px;border-radius:8px;background:#262931;border:1px solid #3a3e48;
  color:#cfd5df;cursor:pointer;font-size:11.5px;text-align:center;line-height:1.3}
.ac-win .side-ops .sbtn:hover{border-color:#e6b45c;color:#fff}
.ac-win .side-ops .sbtn.main{background:linear-gradient(180deg,#3a3126,#2b2620);border-color:#6b5330;color:#f0d3a0}
.ac-win .side-ops .sbtn.main:hover{color:#fff5e0;border-color:#e6b45c}
.ac-win .side-ops .shint{color:#666c77;font-size:10.5px;text-align:center;line-height:1.4}
.ac-win .ac-foot{display:flex;align-items:center;gap:12px;padding:8px 14px;border-top:1px solid #2e3037;
  flex:0 0 auto;min-height:56px}
.ac-win .ac-info{flex:1;display:flex;align-items:center;gap:10px;min-width:0}
.ac-win .ifo-thumb{width:38px;height:38px;border-radius:7px;object-fit:cover;background:#16171b;flex:0 0 auto}
.ac-win .ifo-meta{display:flex;flex-direction:column;line-height:1.35;flex:0 0 auto}
.ac-win .ifo-meta b{font-size:12.5px;color:#e3e6ec}
.ac-win .ifo-sub{font-size:10.5px;color:#666c77}
.ac-win .ifo-ap{flex:1;min-width:0;color:#8d939e;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ac-win .ifo-sel{padding:4px 8px;border-radius:7px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;
  font-size:11.5px;max-width:150px;flex:0 0 auto}
.ac-win .ifo-btn{padding:5px 13px;border-radius:8px;background:#262931;border:1px solid #3a3e48;color:#dde2ea;
  cursor:pointer;font-size:11.5px;flex:0 0 auto}
.ac-win .ifo-btn:hover{border-color:#4a4e59}
.ac-win .ifo-btn.main{background:linear-gradient(180deg,#3f8f6f,#35795d);border-color:#4aa17c;color:#fff;font-weight:600}
.ac-win .hint-inline{color:#666c77;font-size:11.5px}
.ac-win .ac-count{color:#666c77;font-size:11px;flex:0 0 auto}
.ac-win .wrow{display:flex;align-items:center;gap:5px;padding:0 8px 7px}
.ac-win .wrow .wl{color:#666c77;font-size:10.5px;flex:0 0 auto}
.ac-win .wrow .winput{width:52px;padding:2px 5px;border-radius:5px;background:#23252b;
  border:1px solid #383b43;color:#e6b45c;font-size:11px;text-align:center}
.ac-mask2{position:fixed;inset:0;background:rgba(8,9,12,.7);z-index:100005;display:flex;align-items:center;justify-content:center}
.ac-edit{width:min(700px,94vw);max-height:90vh;background:#1b1c21;border:1px solid #34373f;border-radius:12px;
  display:flex;flex-direction:column;overflow:hidden;color:#e3e6ec;
  font:13px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.ac-edit .eh{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid #2e3037}
.ac-edit .eh b{flex:1;font-size:13.5px}
.ac-edit .x{width:26px;height:26px;border-radius:7px;background:#23252b;border:1px solid #383b43;color:#8d939e;
  display:grid;place-items:center;cursor:pointer}
.ac-edit .ebody{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.ac-edit .sub-t{color:#b9c1cd;font-size:11.5px;font-weight:600;margin-top:6px}
.ac-edit .frow{display:flex;align-items:center;gap:8px}
.ac-edit .fl{flex:0 0 96px;color:#8d939e;font-size:11.5px}
.ac-edit .fi{flex:1;padding:5px 9px;border-radius:7px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;
  font-size:12px;outline:none}
.ac-edit .fta{width:100%;height:90px;resize:vertical;background:#202127;border:1px solid #383b43;border-radius:8px;
  padding:8px 10px;color:#cfd5df;font:11.5px/1.6 Consolas,monospace;outline:none}
.ac-edit .fta.big{height:220px}
.ac-edit .urow{display:flex;align-items:center;gap:8px;font-size:11.5px}
.ac-edit .hint{color:#666c77;font-size:11.5px;line-height:1.6}
.ac-edit .efoot{display:flex;gap:8px;padding:12px 16px;border-top:1px solid #2e3037}
.ac-edit .efoot .btn{flex:0 0 auto;padding:7px 16px;border-radius:9px;background:#262931;border:1px solid #3a3e48;
  color:#dde2ea;cursor:pointer;font-size:12.5px}
.ac-edit .efoot .btn.main{background:linear-gradient(180deg,#3f8f6f,#35795d);border-color:#4aa17c;color:#fff;font-weight:600;margin-left:auto}
.ac-edit .efoot .btn.danger{color:#e08a8a;border-color:#5a2f2f}
`;
if (!document.getElementById("ac-style")) {
  const s = document.createElement("style");
  s.id = "ac-style";
  s.textContent = CSS;
  document.head.appendChild(s);
}

export { openPanel };
