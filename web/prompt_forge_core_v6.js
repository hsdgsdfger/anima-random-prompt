const pfFetch = (u, opt) => (globalThis.__pfFetch ? globalThis.__pfFetch(u, opt) : fetch(u, opt));
/* Prompt Forge 工作台 v7：
   自由选词（分批渲染 + 撤销 + 冲突检查 + Token 估算）
   模板卡片（档位筛选 + 滚动加载 + 懒建标签 + 反查 + 同场景换一套）
   场景包（45 包浏览与整套套用）
   设置（5×5 档位矩阵 + any 配比 + 试抽直方图 + 导入导出）
*/
const LEVELS = [
  ["sfw", "0 · 全年龄", "无任何裸露向标签"],
  ["suggestive", "1 · 擦边", "轻度暗示：露肩 / 短裙 / 内衣轮廓 / 材质诱惑"],
  ["explicit", "2 · 成人", "明显裸露或透视：全裸 / 性器官 / 乳头 / 内衣外露 / 半脱"],
  ["hardcore", "3 · 过激", "性行为 / 性道具 / 体液 / 束缚调教"],
  ["extreme", "4 · 极端", "极端插入扩张 / 拘束装置 / 极限体液 / 主奴标记"],
];
const LEVEL_KEYS = ["sfw", "suggestive", "explicit", "hardcore", "extreme"];
const SCENE_ZH = {
  bedroom_night: "卧室 · 夜", bedroom_morning: "卧室 · 晨", classroom_day: "教室 · 白天",
  library_day: "图书馆", cafe_day: "咖啡厅", kitchen_day: "厨房", bathroom_morning: "浴室 · 晨",
  onsen_winter: "温泉 · 冬", beach_summer_day: "海滩 · 夏", pool_summer_day: "泳池 · 夏",
  camp_winter: "冬营地", city_rain_night: "雨夜街道", city_day: "城市 · 白天",
  park_autumn: "公园 · 秋", flower_spring: "花园 · 春", shrine_spring: "神社 · 春",
  rooftop_sunset: "天台 · 黄昏", office_day: "办公室", hospital_day: "医院",
  gym_school: "学校体育馆", stage_night: "舞台 · 夜", festival_night: "夜市祭典",
  desert_day: "沙漠", underwater: "水下", aquarium_day: "水族馆",
  space_station: "空间站", castle_fantasy: "奇幻城堡", school_corridor: "校园走廊",
  subway_train: "地铁车厢", convenience_store: "便利店", gym_locker: "更衣室",
  hotel_room: "酒店房", dorm_room: "宿舍", cinema_dark: "电影院",
  greenhouse_day: "温室", riverside_summer: "河边 · 夏", snowy_street: "雪夜街道",
  mountain_hike: "登山", ruins_ancient: "古代遗迹", airship_deck: "飞艇甲板",
  sauna_bath: "澡堂", farm_day: "农场", temple_day: "神社 · 白天",
  pool_indoor: "室内泳池", museum_day: "博物馆",
};
const FAV_TAG_KEY = "pf_fav_tags_v1";
const FAV_TPL_KEY = "pf_fav_templates_v1";
const RECENT_KEY = "pf_recent_tags_v1";
const ZH_KEY = "pf_zh_v1";
const TPL_LEVEL_KEY = "pf_tpl_level_v1";

const DEFAULT_MATRIX = {
  sfw: { sfw: 1 },
  suggestive: { suggestive: 0.5, sfw: 0.5 },
  explicit: { explicit: 0.5, sfw: 0.25, suggestive: 0.25 },
  hardcore: { hardcore: 0.5, sfw: 0.1667, suggestive: 0.1667, explicit: 0.1666 },
  extreme: { extreme: 0.5, sfw: 0.125, suggestive: 0.125, explicit: 0.125, hardcore: 0.125 },
};
const DEFAULT_ANY = { sfw: 0.7, suggestive: 0.075, explicit: 0.075, hardcore: 0.075, extreme: 0.075 };
const MAX_SELECTED = 60;
const BATCH_FREE = 300;      // 「全部」分批渲染每批胶囊数
const BATCH_TPL = 24;        // 模板每次追加条数
const UNDO_STEPS = 20;

let lib = null, tpl = null, sceneMeta = null, scenes = null, tagFlags = null;
const st = {
  node: null, tab: "free", q: "",
  kind: "all", cat: "all", tplLevel: "all",
  fcat: null, zh: true,
  recent: [], selected: [], favTags: [], favTpl: [],
  onlyFav: false, tplSort: "default", tplShown: BATCH_TPL, freeShown: BATCH_FREE,
  sceneFilter: "all",
  undo: [], redo: [],
  cfg: null,
};
const ds = { lib: null, tpl: null, sceneMeta: null, scenes: null, flags: null, ud: null };
const dst = { lib: "idle", tpl: "idle", sceneMeta: "idle", scenes: "idle", flags: "idle", ud: "idle" };

/* ---------- 小工具 ---------- */
function toast(msg, ok = true) {
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.cssText = `position:fixed;left:50%;bottom:56px;transform:translateX(-50%);z-index:100001;
    background:${ok ? "#1f7a4d" : "#8a2b2b"};color:#fff;padding:9px 16px;border-radius:8px;
    font:13px/1.4 system-ui,'Microsoft YaHei',sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.4);
    opacity:0;transition:opacity .15s`;
  document.body.appendChild(t);
  requestAnimationFrame(() => (t.style.opacity = "1"));
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 200); }, 1500);
}
function copyText(text) {
  const done = () => toast("已复制");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, () => fallback());
  else fallback();
  function fallback() {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch { toast("复制失败", false); }
    ta.remove();
  }
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function lsGet(k, def) { try { return JSON.parse(localStorage.getItem(k)) || def; } catch { return def; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
function debounce(fn, ms) {
  let h = 0;
  return function () { clearTimeout(h); h = setTimeout(() => fn.apply(this, arguments), ms); };
}
function tagsOf(text) {
  return String(text || "").split(",").map((s) => s.trim()).filter(Boolean);
}
function keyOfLevel(label) {
  const s = String(label || "");
  for (const k of LEVEL_KEYS) if (s.startsWith(k)) return k;
  return s.startsWith("any") ? "any" : "sfw";
}

/* ---------- 数据请求（四路独立错误态，REQ-123） ---------- */
function fetchJson(url) {
  return pfFetch(url).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });
}
function loadInto(key, url, apply) {
  if (dst[key] === "done") return Promise.resolve();
  if (dst[key] === "loading") return ds[key] || Promise.resolve();
  dst[key] = "loading";
  ds[key] = fetchJson(url).then((j) => {
    apply(j);
    dst[key] = "done";
    return j;
  }).catch((e) => {
    dst[key] = "error";
    ds[key] = null;
    throw e;
  });
  return ds[key];
}
function retryData(key) {
  dst[key] = "idle";
  ds[key] = null;
  const map = {
    lib: () => loadInto("lib", "/prompt_forge/library", applyLib),
    tpl: () => loadInto("tpl", "/prompt_forge/templates", (j) => { tpl = j.items || []; }),
    sceneMeta: () => loadInto("sceneMeta", "/prompt_forge/scene_meta", (j) => { sceneMeta = j || {}; }),
    scenes: () => loadInto("scenes", "/prompt_forge/scenes", (j) => { scenes = j || { bundles: [] }; }),
    flags: () => loadInto("flags", "/prompt_forge/tag_flags", (j) => { tagFlags = j || {}; }),
  };
  const p = map[key]();
  return p.then(() => { rerenderTab(); }, () => { rerenderTab(); });
}
function applyLib(j) {
  libCats = (j.cats || []).map((c) => ({
    id: c.id, name: c.name, icon: c.icon || "",
    tags: c.tags.map((t) => ({ en: t.en, zh: t.zh, cat: c.name, lv: t.lv })),
  }));
  lib = libCats.flatMap((c) => c.tags);
  buildLvIndex();
}
let libCats = null;
let lvIndex = null;
let lvMin = null;
function buildLvIndex() {
  lvIndex = new Map();
  lvMin = new Map();
  for (const t of lib) {
    lvIndex.set(t.en, t.lv | 0);
    lvMin.set(t.en.toLowerCase(), Math.min(lvMin.get(t.en.toLowerCase()) ?? 9, t.lv | 0));
  }
}
function tagLvMin(en) { return lvMin ? (lvMin.get(String(en).toLowerCase()) ?? 0) : 0; }

/* ---------- 用户态（服务端持久化，REQ-103） ---------- */
function defaultCfg() {
  return {
    level_dist: false,
    level_matrix: JSON.parse(JSON.stringify(DEFAULT_MATRIX)),
    any_weights: { ...DEFAULT_ANY },
    auto_popup: true,
  };
}
function normalizeCfg(s) {
  const out = defaultCfg();
  if (!s || typeof s !== "object") return out;
  out.level_dist = !!s.level_dist;
  out.auto_popup = s.auto_popup !== false;
  if (s.level_matrix && typeof s.level_matrix === "object") {
    for (const row of LEVEL_KEYS) {
      const src = s.level_matrix[row];
      if (!src || typeof src !== "object") continue;
      const r = {};
      let sum = 0;
      for (const col of LEVEL_KEYS) {
        const v = Math.max(0, Number(src[col]) || 0);
        if (v > 0) { r[col] = v; sum += v; }
      }
      if (sum > 0) out.level_matrix[row] = r;
    }
  }
  if (s.any_weights && typeof s.any_weights === "object") {
    const w = {};
    let sum = 0;
    for (const k of LEVEL_KEYS) {
      const v = Math.max(0, Number(s.any_weights[k]) || 0);
      w[k] = v; sum += v;
    }
    if (sum > 0) out.any_weights = w;
  }
  return out;
}
function loadUserdata() {
  if (dst.ud === "done") return Promise.resolve();
  if (dst.ud === "loading" && ds.ud) return ds.ud;
  dst.ud = "loading";
  ds.ud = fetchJson("/prompt_forge/userdata").then((j) => {
    const fav = j.favorites || {};
    const remoteEmpty = !(fav.tags || []).length && !(fav.templates || []).length &&
      !(fav.recent || []).length;
    st.cfg = normalizeCfg(j.settings);
    if (remoteEmpty) {
      // 一次性迁移：服务端还是空的，但本机 localStorage 有值
      const lTags = lsGet(FAV_TAG_KEY, []);
      const lTpl = lsGet(FAV_TPL_KEY, []);
      const lRecent = lsGet(RECENT_KEY, []);
      if (lTags.length || lTpl.length || lRecent.length) {
        st.favTags = lTags; st.favTpl = lTpl; st.recent = lRecent;
        scheduleSave(0);
      } else {
        st.favTags = []; st.favTpl = []; st.recent = [];
      }
    } else {
      st.favTags = fav.tags || [];
      st.favTpl = fav.templates || [];
      st.recent = fav.recent || [];
      if (typeof fav.zh === "boolean") st.zh = fav.zh;
    }
    dst.ud = "done";
    return j;
  }).catch((e) => {
    dst.ud = "error";
    ds.ud = null;
    // 服务端不可用时退回本地缓存，至少工作台打得开
    st.cfg = st.cfg || defaultCfg();
    st.favTags = lsGet(FAV_TAG_KEY, []);
    st.favTpl = lsGet(FAV_TPL_KEY, []);
    st.recent = lsGet(RECENT_KEY, []);
    throw e;
  });
  return ds.ud;
}
let saveTimer = 0;
let pendingBody = null;
function scheduleSave(delay = 250) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, delay);
}
// 关 ComfyUI / 关标签页时把还没发出去的那一次立刻送出
function flushOnExit() {
  if (!pendingBody) return;
  const body = pendingBody;
  pendingBody = null;
  try {
    navigator.sendBeacon("/prompt_forge/userdata",
      new Blob([body], { type: "application/json" }));
  } catch {}
}
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", flushOnExit);
  window.addEventListener("beforeunload", flushOnExit);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushOnExit();
  });
}
function flushSave() {
  clearTimeout(saveTimer);
  lsSet(FAV_TAG_KEY, st.favTags);
  lsSet(FAV_TPL_KEY, st.favTpl);
  lsSet(RECENT_KEY, st.recent);
  // 用户态还没从服务端拉过就先拉一次，否则会把空收藏覆盖上去
  if (dst.ud !== "done") {
    if (dst.ud === "error") return;
    loadUserdata().then(() => flushSave()).catch(() => {});
    return;
  }
  const body = JSON.stringify({
    favorites: { tags: st.favTags, templates: st.favTpl, recent: st.recent, zh: st.zh },
    settings: st.cfg || defaultCfg(),
  });
  pendingBody = body;
  pfFetch("/prompt_forge/userdata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }).then((r) => {
    if (!r.ok) return r.json().then((j) => { throw new Error(j.error || r.status); });
  }).catch((e) => toast(`保存失败：${e.message || e}`, false))
    .finally(() => { if (pendingBody === body) pendingBody = null; });
}

/* ---------- 写回节点 ---------- */
function nodeText() { return st.selected.join(", "); }
function syncNode() {
  const text = nodeText();
  const node = st.node;
  if (node) {
    const w = node.widgets?.find((x) => x.name === "template_override");
    if (w) {
      w.value = text;
      if (w.inputEl) w.inputEl.value = text;
      node.setDirtyCanvas(true, true);
    }
  }
  if (panel?.out) panel.out.value = text;
  if (panel?.picked) renderPicked();
  renderStats();
}
function pushUndo() {
  const snap = st.selected.slice();
  st.undo.push(snap);
  if (st.undo.length > UNDO_STEPS) st.undo.shift();
  st.redo.length = 0;
}
function doUndo() {
  if (!st.undo.length) { toast("没有可撤销的操作", false); return; }
  st.redo.push(st.selected.slice());
  st.selected = st.undo.pop();
  syncNode();
  refreshChipStates();
  renderFreeList();
  renderConflict();
}
function doRedo() {
  if (!st.redo.length) { toast("没有可重做的操作", false); return; }
  st.undo.push(st.selected.slice());
  st.selected = st.redo.pop();
  syncNode();
  refreshChipStates();
  renderFreeList();
  renderConflict();
}
function setSelected(list, { undo = true } = {}) {
  if (undo) pushUndo();
  st.selected = list.slice(0, MAX_SELECTED);
  syncNode();
  if (panel) { refreshChipStates(); renderFreeList(); renderConflict(); }
}
function toggleTag(en) {
  pushUndo();
  const i = st.selected.indexOf(en);
  if (i >= 0) st.selected.splice(i, 1);
  else if (st.selected.length < MAX_SELECTED) { st.selected.push(en); pushRecent(en); }
  else { toast(`最多 ${MAX_SELECTED} 条，先去掉几条`, false); st.undo.pop(); return; }
  syncNode();
  if (panel) { refreshChipStates(); renderConflict(); }
}
function pushRecent(en) {
  const i = st.recent.indexOf(en);
  if (i >= 0) st.recent.splice(i, 1);
  st.recent.unshift(en);
  if (st.recent.length > 20) st.recent.length = 20;
  lsSet(RECENT_KEY, st.recent);
  scheduleSave();
  refreshSideCounts();
}
function refreshSideCounts() {
  if (!panel?.freeRows) return;
  for (const r of panel.freeRows) {
    if (r.key === "fav") r.n.textContent = String(st.favTags.length);
    if (r.key === "recent") r.n.textContent = String(st.recent.length);
  }
}

/* ---------- 冲突检查（REQ-114，只提示不阻止） ---------- */
const DAY_WORDS = /\b(day|daylight|sunny|clear sky|morning|noon|afternoon|dawn)\b/i;
function conflictOf(selected) {
  if (!tagFlags) return [];
  const flags = new Set();
  let hasMonsterTag = false, hasPlaceTag = false;
  for (const en of selected) {
    const f = tagFlags[en];
    if (!f) continue;
    for (const x of f) flags.add(x);
    if (f.includes("monster")) hasMonsterTag = true;
    if (f.includes("indoor") || f.includes("outdoor")) {
      if (!f.includes("monster")) hasPlaceTag = true;
    }
  }
  const out = [];
  if (flags.has("indoor") && flags.has("outdoor"))
    out.push("同时含室内与室外场景词，背景会打架");
  if (flags.has("water") && flags.has("cold"))
    out.push("同时含水域与寒冷场景词，等于冬天户外泳装");
  if (flags.has("night") && selected.some((s) => DAY_WORDS.test(s)))
    out.push("夜景词与白天词并存，时间不自洽");
  if (hasMonsterTag && hasPlaceTag)
    out.push("异种词与非异种场景词混用");
  return out;
}
function tokenEstimate() {
  const chars = nodeText().length;
  return Math.ceil(chars / 4);
}

/* ---------- 面板 ---------- */
let panel = null;
function closePanel() {
  if (!panel) return;
  if (panel.keyHandler) window.removeEventListener("keydown", panel.keyHandler, true);
  lsSet(FAV_TAG_KEY, st.favTags);
  lsSet(FAV_TPL_KEY, st.favTpl);
  lsSet(RECENT_KEY, st.recent);
  panel.root.remove();
  panel = null;
}

function renderPicked() {
  const box = panel?.picked;
  if (!box) return;
  box.innerHTML = "";
  st.selected.forEach((en) => {
    const chip = el("span", "pk", en);
    const x = el("i", null, "✕");
    x.onclick = () => { toggleTag(en); };
    chip.appendChild(x);
    box.appendChild(chip);
  });
}
function renderStats() {
  if (!panel) return;
  if (panel.cnt) panel.cnt.textContent = `${st.selected.length} / ${MAX_SELECTED}`;
  if (panel.stat) {
    const n = st.selected.length;
    const tk = tokenEstimate();
    panel.stat.textContent = `${n} 条 · 估算 ${tk} token`;
    panel.stat.className = "stat" + (tk > 150 ? " bad" : tk > 75 ? " warn" : "");
  }
  renderConflict();
}
function renderConflict() {
  if (!panel?.conflict) return;
  const list = conflictOf(st.selected);
  if (!list.length) { panel.conflict.style.display = "none"; panel.conflict.textContent = ""; return; }
  panel.conflict.style.display = "";
  panel.conflict.textContent = "⚠ " + list.join("；");
}

function chipOf(t, favSet, selSet) {
  const on = selSet ? selSet.has(t.en) : st.selected.includes(t.en);
  const chip = el("span", "fchip" + (on ? " on" : "") + (favSet.has(t.en) ? " fav" : ""));
  chip.dataset.en = t.en;
  chip.appendChild(el("span", "ck", "✓"));
  chip.appendChild(document.createTextNode(t.en));
  if (st.zh && t.zh) chip.appendChild(el("span", "zh", `（${t.zh}）`));
  const star = el("span", "star", favSet.has(t.en) ? "★" : "☆");
  star.onclick = (e) => {
    e.stopPropagation();
    const i = st.favTags.indexOf(t.en);
    if (i >= 0) st.favTags.splice(i, 1); else st.favTags.push(t.en);
    scheduleSave();
    refreshSideCounts();
    refreshChipStates();
    if (st.fcat === "fav") renderFreeList();
  };
  chip.appendChild(star);
  chip.onclick = () => {
    toggleTag(t.en);
    // 只重绘这一个胶囊，不重建全部 DOM
    chip.classList.toggle("on", st.selected.includes(t.en));
    refreshSideCounts();
  };
  return chip;
}

function refreshChipStates() {
  if (!panel?.freeMain) return;
  const favSet = new Set(st.favTags);
  const selSet = new Set(st.selected);      // 一次建 Set，避免每颗胶囊都做线性查找
  panel.freeMain.querySelectorAll(".fchip").forEach((c) => {
    const en = c.dataset.en;
    c.classList.toggle("on", selSet.has(en));
    const isFav = favSet.has(en);
    c.classList.toggle("fav", isFav);
    const star = c.querySelector(".star");
    if (star) star.textContent = isFav ? "★" : "☆";
  });
}

function renderFreeList() {
  if (!panel?.freeMain) return;
  const q = st.q.trim().toLowerCase();
  const hit = (t) => !q || t.en.toLowerCase().includes(q) || (t.zh || "").includes(q);
  const favSet = new Set(st.favTags);
  const selSet = new Set(st.selected);
  const box = panel.freeMain;
  const keepScroll = box.scrollTop;
  box.innerHTML = "";
  // tag -> 记录 的索引只在"收藏 / 最近"这两个页签需要，别每次重绘都建一遍
  let byEn = null;
  const lookup = (e) => {
    if (!byEn) byEn = new Map(lib.map((t) => [t.en, t]));
    return byEn.get(e);
  };

  const pushSec = (title, tags, limit) => {
    const shownAll = tags.filter(hit);
    const shown = limit ? shownAll.slice(0, limit) : shownAll;
    if (!shown.length && q) return 0;
    const sec = el("div", "f-sec");
    const h = el("div", "f-sec-h");
    h.appendChild(el("b", null, title));
    h.appendChild(el("span", "n", String(shownAll.length)));
    sec.appendChild(h);
    const wrap = el("div", "f-chips");
    shown.forEach((t) => wrap.appendChild(chipOf(t, favSet, selSet)));
    sec.appendChild(wrap);
    box.appendChild(sec);
    if (limit && shownAll.length > shown.length) {
      const more = el("div", "more", `还有 ${shownAll.length - shown.length} 条未渲染 · 点击继续加载`);
      more.onclick = () => { st.freeShown += BATCH_FREE; renderFreeList(); };
      sec.appendChild(more);
    }
    return shown.length;
  };

  let title = "全部", count = 0;
  if (st.fcat === "fav") {
    title = "收藏";
    count = pushSec("★ 我的收藏", st.favTags.map(lookup).filter(Boolean));
  } else if (st.fcat === "recent") {
    title = "最近";
    count = pushSec("◷ 最近点过", st.recent.map(lookup).filter(Boolean));
  } else if (st.fcat && st.fcat !== "all") {
    const c = libCats.find((x) => x.id === st.fcat);
    title = c ? c.name : "全部";
    count = c ? pushSec(c.name, c.tags, q ? 0 : st.freeShown) : 0;
  } else {
    title = "全部";
    // 「全部」分批渲染，避免一次创建 2956 个胶囊
    if (q) {
      libCats.forEach((c) => { count += pushSec(c.name, c.tags); });
    } else {
      for (const c of libCats) {
        if (count >= st.freeShown) break;
        count += pushSec(c.name, c.tags, st.freeShown - count);
      }
    }
  }
  if (!count) box.appendChild(el("div", "empty", q ? "没有匹配的词条" : "这里还是空的，去别的分类挑吧"));
  if (panel.freeTitle) panel.freeTitle.textContent = title;
  if (panel.freeCount) panel.freeCount.textContent = `${count} 个标签`;
  if (!q) box.scrollTop = keepScroll;
  renderConflict();
}

function buildFreeTab(container) {
  const wrap = el("div", "free-wrap");
  const side = el("div", "side");
  const sh = el("div", "side-h");
  sh.appendChild(el("b", null, "分类"));
  sh.appendChild(el("span", null, `${libCats.length} 类`));
  side.appendChild(sh);
  const list = el("div", "side-list");
  const rows = [];
  const mkRow = (key, ico, label, count) => {
    const row = el("div", "cat" + (st.fcat === key ? " on" : ""));
    row.appendChild(el("span", "ico", ico));
    row.appendChild(el("span", "nm", label));
    const n = el("span", "n", String(count));
    n.style.cssText = "color:#666c77;font-size:11px";
    row.appendChild(n);
    row.onclick = () => {
      if (st.fcat === key) return;
      st.fcat = key;
      st.freeShown = BATCH_FREE;
      rows.forEach((r) => r.row.classList.toggle("on", r.key === key));
      renderFreeList();
      panel.freeMain.scrollTop = 0;
    };
    rows.push({ key, row, n });
    list.appendChild(row);
  };
  mkRow("all", "▦", "全部", lib.length);
  mkRow("fav", "★", "收藏", st.favTags.length);
  mkRow("recent", "◷", "最近", st.recent.length);
  const hr = el("div", "hr");
  hr.style.cssText = "height:1px;background:#26282e;margin:8px 12px";
  list.appendChild(hr);
  libCats.forEach((c) => mkRow(c.id, c.icon || "•", c.name, c.tags.length));
  side.appendChild(list);
  wrap.appendChild(side);

  const main = el("div", "f-main");
  const mh = el("div", "f-mh");
  const title = el("b", null, "全部");
  const cnt = el("span", "n", "");
  mh.appendChild(title); mh.appendChild(cnt);
  const grow = el("div", "grow");
  mh.appendChild(grow);
  const zht = el("div", "zh-t" + (st.zh ? "" : " off"));
  const zbox = el("span", "box", st.zh ? "✓" : "");
  zht.appendChild(zbox);
  zht.appendChild(document.createTextNode("中文对照"));
  zht.onclick = () => {
    st.zh = !st.zh;
    lsSet(ZH_KEY, st.zh);
    scheduleSave();
    zht.classList.toggle("off", !st.zh);
    zbox.textContent = st.zh ? "✓" : "";
    renderFreeList();
  };
  mh.appendChild(zht);
  main.appendChild(mh);
  const scroll = el("div", "f-scroll");
  main.appendChild(scroll);
  wrap.appendChild(main);
  container.appendChild(wrap);

  panel.freeMain = scroll; panel.freeTitle = title; panel.freeCount = cnt; panel.freeRows = rows;
  renderFreeList();
}

/* ---------- 模板页（REQ-105 档位筛选 + REQ-106 滚动加载） ---------- */
function tplLevels() {
  const set = new Set();
  for (const x of tpl) set.add(x.level);
  return ["all", ...Array.from(set)];
}
function filteredTpl(skipLevel = false) {
  const q = st.q.trim().toLowerCase();
  const favSet = new Set(st.favTpl);
  let items = tpl.filter((x) => tplPass(x, skipLevel, q, favSet));
  if (st.tplSort === "match" && st.selected.length) {
    const want = new Set(st.selected.map((s) => s.toLowerCase()));
    items = items.map((x) => {
      const ts = tagsOf(x.prompt).map((t) => t.toLowerCase());
      let hit = 0;
      for (const t of ts) if (want.has(t)) hit++;
      return { x, hit };
    }).filter((r) => r.hit > 0)
      .sort((a, b) => b.hit - a.hit)
      .map((r) => ({ ...r.x, _hit: r.hit }));
  }
  return items;
}

// 一套模板是否通过当前筛选条件；filteredTpl 与档位计数共用同一份判断，
// 避免两处各写一套、改了一处另一处对不上。
function tplPass(x, skipLevel, q, favSet) {
  if (st.kind !== "all" && x.kind !== st.kind) return false;
  if (st.cat === "other") {
    if (x.bundle) return false;
  } else if (st.cat !== "all" && (sceneMeta?.[x.bundle]?.[st.cat] !== true)) return false;
  if (!skipLevel && st.tplLevel !== "all" && x.level !== st.tplLevel) return false;
  if (st.onlyFav && !favSet.has(x.id)) return false;
  if (q && !(x.prompt.toLowerCase().includes(q) || (SCENE_ZH[x.bundle] || "").includes(q))) return false;
  return true;
}

// 档位计数：一次遍历算出全部档位，按筛选条件签名缓存。
// 以前是每个档位跑一遍 filteredTpl(true)，6 个档位 = 6 次全表扫描。
let _lvSig = "";
let _lvMap = null;
function lvSignature() {
  return [st.kind, st.cat, st.q, st.onlyFav ? 1 : 0, st.favTpl.length,
          tpl ? tpl.length : -1, sceneMeta ? 1 : 0].join("|");
}
function levelCounts() {
  const sig = lvSignature();
  if (_lvMap && _lvSig === sig) return _lvMap;
  const q = st.q.trim().toLowerCase();
  const favSet = new Set(st.favTpl);
  const map = { all: 0 };
  for (const x of tpl || []) {
    if (!tplPass(x, true, q, favSet)) continue;
    map.all++;
    map[x.level] = (map[x.level] || 0) + 1;
  }
  _lvSig = sig;
  _lvMap = map;
  return map;
}
function levelCount(level) {
  const m = levelCounts();
  return level === "all" ? m.all : (m[level] || 0);
}

function cardOf(item) {
  const fav = st.favTpl.includes(item.id);
  const card = el("div", "card");
  card._item = item;
  const head = el("div", "card-h");
  head.appendChild(el("span", "no", `#${String(item.index).padStart(3, "0")}`));
  const title = item.bundle
    ? (SCENE_ZH[item.bundle] || item.bundle)
    : (item.zh || item.group_zh || "V6 场景搭配");
  head.appendChild(el("span", "nm", title + (item.kind === "monster" ? " · 异种" : "")));
  head.appendChild(el("span", "badge" + (item.kind === "monster" ? " mon" : ""), item.level));
  const star = el("span", "star" + (fav ? " on" : ""), fav ? "★" : "☆");
  star.onclick = () => {
    const i = st.favTpl.indexOf(item.id);
    if (i >= 0) st.favTpl.splice(i, 1); else st.favTpl.push(item.id);
    lsSet(FAV_TPL_KEY, st.favTpl);
    scheduleSave();
    star.textContent = st.favTpl.includes(item.id) ? "★" : "☆";
    star.classList.toggle("on", st.favTpl.includes(item.id));
    if (panel.favBar) panel.favBar.textContent = `★ 只看我的收藏 (${st.favTpl.length})`;
  };
  head.appendChild(star);
  card.appendChild(head);

  const tags = tagsOf(item.prompt);
  const meta = el("div", "card-meta");
  const srcLabel = item.bundle ? (SCENE_ZH[item.bundle] || item.bundle)
    : `${item.group_zh || "V6"} · V6`;
  const bits = [item.kind === "monster" ? "异种" : "普通",
    tags.includes("2girls") ? "2girls duo" : "1girl solo",
    `${tags.length} 标签`, srcLabel];
  if (item._hit !== undefined) bits.unshift(`重合 ${item._hit}`);
  bits.forEach((x) => meta.appendChild(el("span", null, x)));
  card.appendChild(meta);

  // 标签 DOM 延迟创建：首次展开才生成（REQ-106）
  let tagBox = null;
  const fold = el("div", "tag-fold", `▸ 展开 ${tags.length} 个标签`);
  fold.onclick = () => {
    const open = !!tagBox;
    if (open) { tagBox.remove(); tagBox = null; }
    else {
      tagBox = el("div", "card-tags");
      tags.forEach((t) => {
        const tg = el("span", "tg", t);
        tg.classList.toggle("on", st.selected.includes(t));
        tg.onclick = (e) => {                       // REQ-117 标签可点击加入/移出
          e.stopPropagation();
          toggleTag(t);
          tg.classList.toggle("on", st.selected.includes(t));
        };
        tagBox.appendChild(tg);
      });
      card.insertBefore(tagBox, fold);
    }
    fold.textContent = open ? `▸ 展开 ${tags.length} 个标签` : "▾ 收起标签";
    fold.classList.toggle("on", !open);
  };
  card.appendChild(fold);

  const btns = el("div", "card-btns");
  const b0 = el("div", "btn", "换一套");           // REQ-121 同场景换模板
  b0.style.flex = "0 0 auto";
  b0.onclick = () => {
    const pool = tpl.filter((x) => x.bundle === item.bundle && x.id !== item.id &&
      (x.level === item.level || LEVEL_KEYS.indexOf(x.level) <= LEVEL_KEYS.indexOf(item.level)));
    if (!pool.length) { toast("同场景没有别的模板了", false); return; }
    const next = pool[Math.floor(Math.random() * pool.length)];
    const fresh = cardOf(next);
    card.replaceWith(fresh);
  };
  const b1 = el("div", "btn", "复制");
  b1.onclick = () => copyText(item.prompt);
  const b2 = el("div", "btn gold", "套用到节点");
  b2.onclick = () => applyTemplate(item.prompt);
  btns.appendChild(b0); btns.appendChild(b1); btns.appendChild(b2);
  card.appendChild(btns);
  return card;
}

function applyTemplate(prompt, quiet) {
  const tags = tagsOf(prompt);
  if (!st.selected.length || quiet) {
    setSelected(tags);
    copyText(prompt);
    toast("已写入节点，排队即可出图");
    return;
  }
  // REQ-113 已选非空时三态确认
  confirmBox("套用模板会覆盖当前已选的 " + st.selected.length + " 条词条", [
    ["替换", () => { setSelected(tags); copyText(prompt); toast("已替换并写入节点"); }],
    ["追加", () => {
      const seen = new Set(st.selected.map((s) => s.toLowerCase()));
      const add = tags.filter((t) => !seen.has(t.toLowerCase()));
      setSelected(st.selected.concat(add));
      copyText(prompt);
      toast(`已追加 ${add.length} 条`);
    }],
    ["取消", null],
  ]);
}

function renderCards() {
  if (!panel?.cards) return;
  const wrap = panel.cards;
  const items = filteredTpl();
  const shown = items.slice(0, st.tplShown);
  wrap.innerHTML = "";
  if (!shown.length) {
    wrap.appendChild(el("div", "empty", st.tplSort === "match" && st.selected.length
      ? "已选词条与任何模板都没有重合" : "没有匹配的模板"));
  }
  shown.forEach((it) => wrap.appendChild(cardOf(it)));
  updateTplFoot(items.length, shown.length);
}
function updateTplFoot(total, shown) {
  if (!panel?.pageInfo) return;
  const done = shown >= total;
  panel.pageInfo.textContent = done
    ? `已全部加载 ${total} 套`
    : `已加载 ${shown} / ${total} 套 · 继续下滑加载更多`;
}
function appendCards() {
  if (!panel?.cards || panel.loading) return;
  const items = filteredTpl();
  if (st.tplShown >= items.length) { updateTplFoot(items.length, items.length); return; }
  panel.loading = true;
  const box = panel.cards;
  const end = Math.min(items.length, st.tplShown + BATCH_TPL);
  for (let i = st.tplShown; i < end; i++) box.appendChild(cardOf(items[i]));
  st.tplShown = end;
  panel.loading = false;
  updateTplFoot(items.length, st.tplShown);
}
function resetTplList() {
  st.tplShown = BATCH_TPL;
  if (panel?.cards) panel.cards.scrollTop = 0;
  renderCards();
}

function buildTplTab(container) {
  const side = el("div", "side");
  const sh = el("div", "side-h");
  sh.appendChild(el("b", null, "场景分类"));
  sh.appendChild(el("span", null, "45 包"));
  side.appendChild(sh);
  const list = el("div", "side-list");
  const cats = [["all", "全部", "🏷"], ["indoor", "室内", "🏠"], ["outdoor", "室外", "🌳"],
                ["night", "夜景", "🌙"], ["cold", "寒冷", "❄"], ["water", "水域", "💧"],
                ["monster", "异种", "🧬"], ["other", "V6 场景搭配", "🎬"]];
  cats.forEach(([key, label, ico]) => {
    const row = el("div", "cat" + (st.cat === key ? " on" : ""));
    row.appendChild(el("span", "ico", ico));
    row.appendChild(el("span", "nm", label));
    row.onclick = () => {
      st.cat = key;
      st.tplShown = BATCH_TPL;
      list.querySelectorAll(".cat").forEach((c) => c.classList.remove("on"));
      row.classList.add("on");
      resetTplList();
    };
    list.appendChild(row);
  });
  side.appendChild(list);
  const favbar = el("div", "favbar" + (st.onlyFav ? "" : " off"), `★ 只看我的收藏 (${st.favTpl.length})`);
  favbar.onclick = () => {
    st.onlyFav = !st.onlyFav;
    favbar.classList.toggle("off", !st.onlyFav);
    resetTplList();
  };
  side.appendChild(favbar);
  panel.favBar = favbar;
  container.appendChild(side);

  const main = el("div", "main");
  // 档位筛选条（REQ-105）
  const bar = el("div", "lvbar");
  main.appendChild(bar);
  const cards = el("div", "cards");
  main.appendChild(cards);
  cards.onscroll = () => {
    if (cards.scrollTop + cards.clientHeight >= cards.scrollHeight - 200) appendCards();
  };
  const foot = el("div", "foot");
  const info = el("div", null, "");
  info.style.cssText = "flex:1;text-align:center";
  foot.appendChild(info);
  main.appendChild(foot);
  container.appendChild(main);

  panel.cards = cards; panel.pageInfo = info; panel.lvbar = bar;
  buildLevelBar();
  renderCards();
}

function buildLevelBar() {
  const bar = panel.lvbar;
  if (!bar) return;
  bar.innerHTML = "";
  const label = el("span", "lb", "档位");
  bar.appendChild(label);
  tplLevels().forEach((lv) => {
    const n = levelCount(lv);
    const b = el("div", "lvpill" + (st.tplLevel === lv ? " on" : ""),
      `${lv === "all" ? "全部" : lv} ${n}`);
    b.onclick = () => {
      st.tplLevel = lv;
      lsSet(TPL_LEVEL_KEY, lv);
      st.tplShown = BATCH_TPL;
      buildLevelBar();
      renderCards();
    };
    bar.appendChild(b);
  });
  const grow = el("div", "grow");
  bar.appendChild(grow);
  const mk = el("div", "lvpill" + (st.tplSort === "match" ? " on" : ""), "🔍 按已选反查");
  mk.onclick = () => {
    if (!st.selected.length) { toast("先在自由选词里选几条词", false); return; }
    st.tplSort = st.tplSort === "match" ? "default" : "match";
    st.tplShown = BATCH_TPL;
    buildLevelBar();
    renderCards();
  };
  bar.appendChild(mk);
}

function rebuildTpl() {
  const box = panel.left;
  box.innerHTML = "";
  buildTplTab(box);
}

/* ---------- 场景包页签（REQ-116） ---------- */
const SCENE_FILTERS = [["all", "全部", "🏷"], ["indoor", "室内", "🏠"], ["outdoor", "室外", "🌳"],
                       ["night", "夜景", "🌙"], ["cold", "寒冷", "❄"], ["water", "水域", "💧"],
                       ["monster", "异种", "🧬"]];

function scenePackPrompt(b) {
  // 确定性拼装：每个槽位取第一条，已由 bundle 保证互斥
  const parts = ["1girl", "solo"];
  const push = (arr, n = 1) => {
    if (!arr) return;
    for (const t of arr.slice(0, n)) if (t) parts.push(t);
  };
  push(b.env, 1);
  push(b.season, 1);
  push(b.weather, 1);
  push(b.time, 1);
  push(b.light, 1);
  push(b.cloth, 2);
  push(b.shoes, 1);
  push(b.acc, 1);
  push(b.props, 1);
  push(b.poses, 1);
  const out = [];
  const seen = new Set();
  for (const p of parts) {
    const k = p.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(p);
  }
  return out.join(", ");
}

function sceneCardOf(b, meta) {
  const card = el("div", "scard");
  const h = el("div", "card-h");
  h.appendChild(el("span", "nm", SCENE_ZH[b.id] || b.id));
  if (meta?.monster) h.appendChild(el("span", "badge mon", "异种"));
  if (meta?.night) h.appendChild(el("span", "badge", "夜景"));
  if (meta?.water) h.appendChild(el("span", "badge", "水域"));
  if (meta?.cold) h.appendChild(el("span", "badge", "寒冷"));
  h.appendChild(el("span", "badge", meta?.indoor ? "室内" : "室外"));
  card.appendChild(h);

  const rows = [
    ["环境", b.env], ["服装", b.cloth], ["道具", b.props], ["姿势", b.poses],
    ["时间", b.time], ["光影", b.light],
  ];
  const box = el("div", "srows");
  rows.forEach(([k, arr]) => {
    if (!arr || !arr.length) return;
    const r = el("div", "srow");
    r.appendChild(el("span", "k", k));
    const v = el("span", "v", arr.slice(0, 4).join(" / ") + (arr.length > 4 ? " …" : ""));
    r.appendChild(v);
    box.appendChild(r);
  });
  card.appendChild(box);

  const btns = el("div", "card-btns");
  const b1 = el("div", "btn", "复制");
  b1.onclick = () => copyText(scenePackPrompt(b));
  const b2 = el("div", "btn gold", "整套套用");
  b2.onclick = () => {
    const p = scenePackPrompt(b);
    setSelected(tagsOf(p));
    copyText(p);
    toast("已按该场景包写入节点");
  };
  btns.appendChild(b1); btns.appendChild(b2);
  card.appendChild(btns);
  return card;
}

function buildSceneTab(container) {
  const side = el("div", "side");
  const sh = el("div", "side-h");
  sh.appendChild(el("b", null, "场景标记"));
  sh.appendChild(el("span", null, `${(scenes?.bundles || []).length} 包`));
  side.appendChild(sh);
  const list = el("div", "side-list");
  SCENE_FILTERS.forEach(([key, label, ico]) => {
    const row = el("div", "cat" + (st.sceneFilter === key ? " on" : ""));
    row.appendChild(el("span", "ico", ico));
    row.appendChild(el("span", "nm", label));
    row.onclick = () => {
      st.sceneFilter = key;
      list.querySelectorAll(".cat").forEach((c) => c.classList.remove("on"));
      row.classList.add("on");
      renderScenes();
    };
    list.appendChild(row);
  });
  side.appendChild(list);
  container.appendChild(side);

  const main = el("div", "main");
  const cards = el("div", "cards");
  main.appendChild(cards);
  const foot = el("div", "foot");
  const info = el("div", null, "");
  info.style.cssText = "flex:1;text-align:center";
  foot.appendChild(info);
  main.appendChild(foot);
  container.appendChild(main);
  panel.cards = cards; panel.pageInfo = info;
  renderScenes();
}

function renderScenes() {
  if (!panel?.cards) return;
  const box = panel.cards;
  const bundles = (scenes?.bundles || []).filter((b) => {
    if (st.sceneFilter === "all") return true;
    const m = sceneMeta?.[b.id] || {};
    return m[st.sceneFilter] === true;
  });
  box.innerHTML = "";
  if (!bundles.length) box.appendChild(el("div", "empty", "没有匹配的场景包"));
  bundles.forEach((b) => box.appendChild(sceneCardOf(b, sceneMeta?.[b.id])));
  if (panel.pageInfo) panel.pageInfo.textContent = `${bundles.length} 个场景包`;
}

/* ---------- 确认框 / 小弹层 ---------- */
function confirmBox(text, actions) {
  const mask = el("div", "pf-mini-mask");
  const win = el("div", "pf-mini");
  win.appendChild(el("div", "t", text));
  const row = el("div", "row");
  actions.forEach(([label, fn]) => {
    const b = el("div", "btn" + (fn ? "" : ""), label);
    b.onclick = () => { mask.remove(); if (fn) fn(); };
    row.appendChild(b);
  });
  win.appendChild(row);
  mask.appendChild(win);
  mask.addEventListener("mousedown", (e) => { if (e.target === mask) mask.remove(); });
  document.body.appendChild(mask);
}

/* ---------- 设置页（REQ-108） ---------- */
function applyCfg(next) {
  st.cfg = normalizeCfg(next);
  scheduleSave(0);
  if (window.__pfBridge) window.__pfBridge.cfg = st.cfg;
}
function cfgOrDefault() { return st.cfg || defaultCfg(); }

function normRow(row) {
  const sum = LEVEL_KEYS.reduce((a, k) => a + (Number(row[k]) || 0), 0);
  return sum > 0 ? sum : 0;
}

function openSettings() {
  if (!panel) return;
  if (panel.setMask) { panel.setMask.remove(); panel.setMask = null; }
  const cfg = cfgOrDefault();
  const mask = el("div", "pf-cover");
  const win = el("div", "pf-set");
  panel.setMask = mask;

  const head = el("div", "sh");
  head.appendChild(el("b", null, "⚙ Prompt Forge 设置"));
  const x = el("div", "x", "✕");
  x.onclick = () => { mask.remove(); panel.setMask = null; };
  head.appendChild(x);
  win.appendChild(head);

  const body = el("div", "sbody");

  // 1. 总开关
  const sw = el("div", "row");
  const cb = el("span", "box" + (cfg.level_dist ? " on" : ""), cfg.level_dist ? "✓" : "");
  const swLabel = el("span", "lb", "启用固定档位分布抽样");
  const swHint = el("span", "hint", "关闭 = 只按「不超过该档」上限过滤（旧行为）");
  const swWrap = el("div", "swrow");
  swWrap.appendChild(cb); swWrap.appendChild(swLabel); swWrap.appendChild(swHint);
  swWrap.onclick = () => {
    cfg.level_dist = !cfg.level_dist;
    cb.classList.toggle("on", cfg.level_dist);
    cb.textContent = cfg.level_dist ? "✓" : "";
    applyCfg(cfg);
  };
  body.appendChild(swWrap);
  body.appendChild(el("div", "note", "本档 50% = 每次运行有 50% 概率抽到该档，不是词条占比。"));

  // 2. 5×5 矩阵
  body.appendChild(el("div", "sec-t", "档位矩阵（行 = 你选的档位，列 = 本次目标档位）"));
  const table = el("table", "matrix");
  const thead = el("tr");
  thead.appendChild(el("th", null, "选择 \\ 目标"));
  LEVEL_KEYS.forEach((k) => thead.appendChild(el("th", null, k)));
  thead.appendChild(el("th", null, "合计"));
  table.appendChild(thead);
  const hosts = [];
  LEVEL_KEYS.forEach((rowKey) => {
    const tr = el("tr");
    tr.appendChild(el("th", null, rowKey));
    const rowW = { ...(cfg.level_matrix[rowKey] || {}) };
    const upd = () => {
      const cells = tr.querySelectorAll(".mi");
      const sum = cells.reduce((a, i) => a + (Number(i.value) || 0), 0);
      cells.forEach((i, idx) => {
        const v = Number(i.value) || 0;
        const sp = tr.querySelectorAll(".pct")[idx];
        if (sp) sp.textContent = sum > 0 ? `${Math.round((v / sum) * 100)}%` : "-";
      });
      const sumEl = tr.querySelector(".sum");
      if (sumEl) sumEl.textContent = String(sum);
      tr.classList.toggle("bad", sum <= 0);
    };
    LEVEL_KEYS.forEach((colKey) => {
      const td = el("td");
      const locked = LEVEL_KEYS.indexOf(colKey) > LEVEL_KEYS.indexOf(rowKey);
      const inp = el("input", "mi");
      inp.type = "number";
      inp.min = "0"; inp.max = "100"; inp.step = "1";
      inp.value = locked ? "0" : String(Math.round((rowW[colKey] || 0) * 100));
      if (locked) { inp.disabled = true; td.classList.add("locked"); }
      const pct = el("span", "pct", "");
      inp.oninput = upd;
      td.appendChild(inp);
      td.appendChild(pct);
      tr.appendChild(td);
      inp._col = colKey;
    });
    const sumTd = el("td");
    const sum = el("span", "sum", "");
    sumTd.appendChild(sum);
    const reset = el("span", "mini", "重置");
    reset.onclick = () => {
      const def = DEFAULT_MATRIX[rowKey];
      tr.querySelectorAll(".mi").forEach((i) => {
        if (i.disabled) return;
        i.value = String(Math.round(((def[i._col] || 0) * 100)));
      });
      upd();
    };
    sumTd.appendChild(reset);
    tr.appendChild(sumTd);
    tr._rowKey = rowKey;
    table.appendChild(tr);
    hosts.push(tr);
    setTimeout(upd, 0);
  });
  body.appendChild(table);

  // 3. any 配比
  body.appendChild(el("div", "sec-t", "any 配比（any 没有「不超过」约束，五档都可编辑）"));
  const anyRow = el("div", "anyrow");
  const anyInputs = {};
  LEVEL_KEYS.forEach((k) => {
    const cell = el("div", "acell");
    cell.appendChild(el("span", "lb", k));
    const inp = el("input", "mi");
    inp.type = "number";
    inp.min = "0"; inp.max = "100"; inp.step = "1";
    inp.value = String(Math.round((cfg.any_weights[k] || 0) * 100));
    const pct = el("span", "pct", "");
    anyInputs[k] = { inp, pct };
    const upd = () => {
      const sum = LEVEL_KEYS.reduce((a, kk) => a + (Number(anyInputs[kk].inp.value) || 0), 0);
      LEVEL_KEYS.forEach((kk) => {
        const v = Number(anyInputs[kk].inp.value) || 0;
        anyInputs[kk].pct.textContent = sum > 0 ? `${Math.round((v / sum) * 100)}%` : "-";
      });
    };
    inp.oninput = upd;
    cell.appendChild(inp);
    cell.appendChild(pct);
    anyRow.appendChild(cell);
    setTimeout(upd, 0);
  });
  body.appendChild(anyRow);

  // 4. 自动弹窗开关
  const autoWrap = el("div", "swrow");
  const acb = el("span", "box" + (cfg.auto_popup ? " on" : ""), cfg.auto_popup ? "✓" : "");
  autoWrap.appendChild(acb);
  autoWrap.appendChild(el("span", "lb", "选 any 时自动弹窗"));
  autoWrap.onclick = () => {
    cfg.auto_popup = !cfg.auto_popup;
    acb.classList.toggle("on", cfg.auto_popup);
    acb.textContent = cfg.auto_popup ? "✓" : "";
    applyCfg(cfg);
  };
  body.appendChild(autoWrap);

  // 5. 试抽直方图（REQ-119）
  body.appendChild(el("div", "sec-t", "试抽 200 次（按当前矩阵 / any 配比模拟，不写节点）"));
  const hist = el("div", "hist");
  body.appendChild(hist);
  const runSim = () => {
    const counts = LEVEL_KEYS.map(() => 0);
    const lv = keyOfLevel(st.node?.widgets?.find((w) => w.name === "level")?.value || "sfw");
    const weights = (() => {
      if (lv === "any") return LEVEL_KEYS.map((k) => Number(cfg.any_weights[k]) || 0);
      if (!cfg.level_dist) {
        const sel = LEVEL_KEYS.indexOf(lv);
        return LEVEL_KEYS.map((k, i) => (i === sel ? 1 : 0));
      }
      const row = cfg.level_matrix[lv] || {};
      const sel = LEVEL_KEYS.indexOf(lv);
      return LEVEL_KEYS.map((k, i) => (i > sel ? 0 : Number(row[k]) || 0));
    })();
    const total = weights.reduce((a, b) => a + b, 0) || 1;
    for (let n = 0; n < 200; n++) {
      let r = Math.random() * total, idx = 0;
      for (; idx < weights.length; idx++) { r -= weights[idx]; if (r < 0) break; }
      counts[Math.min(idx, weights.length - 1)]++;
    }
    hist.innerHTML = "";
    const max = Math.max(...counts, 1);
    LEVEL_KEYS.forEach((k, i) => {
      const col = el("div", "hcol");
      const bar = el("div", "hbar");
      bar.style.height = `${Math.max(2, (counts[i] / max) * 62)}px`;
      bar.title = `${k}: ${counts[i]}`;
      col.appendChild(el("span", "hv", String(counts[i])));
      col.appendChild(bar);
      col.appendChild(el("span", "hk", k));
      hist.appendChild(col);
    });
    const note = el("div", "note", `依据：当前档位 ${lv}${lv === "any" ? "（any 配比）" : cfg.level_dist ? "（矩阵）" : "（上限过滤）"}`);
    body.appendChild(note);
  };
  runSim();

  // 6. 导入导出（REQ-120）
  const io = el("div", "io");
  const exp = el("div", "btn", "导出收藏 + 设置");
  exp.onclick = () => {
    const data = {
      favorites: { tags: st.favTags, templates: st.favTpl, recent: st.recent, zh: st.zh },
      settings: cfgOrDefault(),
    };
    copyText(JSON.stringify(data, null, 2));
  };
  const imp = el("div", "btn", "导入 JSON");
  imp.onclick = () => importJson();
  io.appendChild(exp); io.appendChild(imp);
  body.appendChild(io);

  const foot = el("div", "sfoot");
  const resetAll = el("div", "btn", "全部恢复默认");
  resetAll.onclick = () => {
    st.cfg = defaultCfg();
    scheduleSave(0);
    if (window.__pfBridge) window.__pfBridge.cfg = st.cfg;
    mask.remove(); panel.setMask = null;
    toast("已恢复默认");
  };
  const save = el("div", "btn main", "保存");
  save.onclick = () => {
    const next = { ...cfg, level_matrix: {}, any_weights: {} };
    for (const tr of hosts) {
      const rowW = {};
      let sum = 0;
      tr.querySelectorAll(".mi").forEach((i) => {
        const v = Number(i.value) || 0;
        if (!i.disabled && v > 0) { rowW[i._col] = v / 100; sum += v; }
      });
      if (sum <= 0) { toast(`「${tr._rowKey}」行权重全为 0，无法保存`, false); return; }
      next.level_matrix[tr._rowKey] = rowW;
    }
    let anySum = 0;
    LEVEL_KEYS.forEach((k) => {
      const v = Number(anyInputs[k].inp.value) || 0;
      next.any_weights[k] = v / 100;
      anySum += v;
    });
    if (anySum <= 0) { toast("any 配比全为 0，无法保存", false); return; }
    applyCfg(next);
    mask.remove(); panel.setMask = null;
    toast("设置已保存");
    if (st.tab === "tpl") buildLevelBar();
  };
  foot.appendChild(resetAll); foot.appendChild(save);
  win.appendChild(body);
  win.appendChild(foot);
  mask.appendChild(win);
  panel.win.appendChild(mask);
}

function importJson() {
  const mask = el("div", "pf-mini-mask");
  const win = el("div", "pf-mini wide");
  win.appendChild(el("div", "t", "粘贴导出的 JSON（导入前会先备份当前数据）"));
  const ta = el("textarea", "imp");
  win.appendChild(ta);
  const row = el("div", "row");
  const ok = el("div", "btn main", "合并导入");
  const ov = el("div", "btn", "覆盖导入");
  const cc = el("div", "btn", "取消");
  const parse = () => {
    try { return JSON.parse(ta.value); } catch { toast("不是合法 JSON", false); return null; }
  };
  const backup = () => {
    lsSet("pf_backup_v1", {
      favorites: { tags: st.favTags, templates: st.favTpl, recent: st.recent, zh: st.zh },
      settings: cfgOrDefault(),
      at: Date.now(),
    });
  };
  const applyImport = (merge) => {
    const j = parse();
    if (!j) return;
    if (!j.favorites && !j.settings) { toast("文件里没有 favorites / settings", false); return; }
    backup();
    const fav = j.favorites || {};
    const arr = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === "string") : []);
    if (merge) {
      st.favTags = Array.from(new Set(st.favTags.concat(arr(fav.tags))));
      st.favTpl = Array.from(new Set(st.favTpl.concat(arr(fav.templates))));
      st.recent = Array.from(new Set(st.recent.concat(arr(fav.recent)))).slice(0, 20);
    } else {
      st.favTags = arr(fav.tags);
      st.favTpl = arr(fav.templates);
      st.recent = arr(fav.recent).slice(0, 20);
    }
    if (j.settings) st.cfg = normalizeCfg(j.settings);
    if (window.__pfBridge) window.__pfBridge.cfg = st.cfg;
    scheduleSave(0);
    mask.remove();
    toast("导入完成");
    rerenderTab();
  };
  ok.onclick = () => applyImport(true);
  ov.onclick = () => applyImport(false);
  cc.onclick = () => mask.remove();
  row.appendChild(ok); row.appendChild(ov); row.appendChild(cc);
  win.appendChild(row);
  mask.appendChild(win);
  document.body.appendChild(mask);
  ta.focus();
}

/* ---------- any 配比弹窗（REQ-107，节点切 any 时弹出） ---------- */
function anyPopup(node, widget, prevLabel) {
  // 配置还没拉过时先拉一次，避免用默认值覆盖服务端设置
  if (dst.ud !== "done" && dst.ud !== "error") {
    loadUserdata().catch(() => {}).then(() => anyPopup(node, widget, prevLabel));
    return;
  }
  const mask = el("div", "pf-mini-mask");
  const win = el("div", "pf-mini wide");
  win.appendChild(el("div", "t", "any = 不设限，需要一组配比才知道每次按哪档取词"));
  const cfg = JSON.parse(JSON.stringify(cfgOrDefault()));
  const row = el("div", "anyrow");
  const inputs = {};
  const upd = () => {
    const sum = LEVEL_KEYS.reduce((a, k) => a + (Number(inputs[k].inp.value) || 0), 0);
    LEVEL_KEYS.forEach((k) => {
      const v = Number(inputs[k].inp.value) || 0;
      inputs[k].pct.textContent = sum > 0 ? `${Math.round((v / sum) * 100)}%` : "-";
    });
  };
  LEVEL_KEYS.forEach((k) => {
    const cell = el("div", "acell");
    cell.appendChild(el("span", "lb", k));
    const inp = el("input", "mi");
    inp.type = "number"; inp.min = "0"; inp.max = "100"; inp.step = "1";
    inp.value = String(Math.round((cfg.any_weights[k] || 0) * 100));
    const pct = el("span", "pct", "");
    inputs[k] = { inp, pct };
    inp.oninput = upd;
    cell.appendChild(inp); cell.appendChild(pct);
    row.appendChild(cell);
  });
  win.appendChild(row);
  setTimeout(upd, 0);

  const tools = el("div", "row");
  const even = el("div", "btn", "均分");
  even.onclick = () => { LEVEL_KEYS.forEach((k) => (inputs[k].inp.value = "20")); upd(); };
  const def = el("div", "btn", "重置为默认");
  def.onclick = () => {
    LEVEL_KEYS.forEach((k) => (inputs[k].inp.value = String(Math.round(DEFAULT_ANY[k] * 100))));
    upd();
  };
  const only = el("div", "btn", "只用某档");
  only.onclick = () => {
    const pick = window.prompt(`只用哪一档？可选：${LEVEL_KEYS.join(" / ")}`, "sfw");
    if (!pick || !LEVEL_KEYS.includes(pick)) return;
    LEVEL_KEYS.forEach((k) => (inputs[k].inp.value = k === pick ? "100" : "0"));
    upd();
  };
  tools.appendChild(even); tools.appendChild(def); tools.appendChild(only);
  win.appendChild(tools);

  const autoWrap = el("div", "swrow");
  const cb = el("span", "box" + (cfg.auto_popup ? " on" : ""), cfg.auto_popup ? "✓" : "");
  autoWrap.appendChild(cb);
  autoWrap.appendChild(el("span", "lb", "不再自动弹出"));
  autoWrap.onclick = () => {
    cfg.auto_popup = !cfg.auto_popup;
    cb.classList.toggle("on", cfg.auto_popup);
    cb.textContent = cfg.auto_popup ? "✓" : "";
  };
  win.appendChild(autoWrap);

  const foot = el("div", "row");
  const cancel = el("div", "btn", "取消");
  cancel.onclick = () => {
    mask.remove();
    if (widget) {
      widget.value = prevLabel;
      node?.setDirtyCanvas?.(true, true);
    }
  };
  const save = el("div", "btn main", "保存");
  save.onclick = () => {
    let sum = 0;
    LEVEL_KEYS.forEach((k) => {
      const v = Number(inputs[k].inp.value) || 0;
      cfg.any_weights[k] = v / 100;
      sum += v;
    });
    if (sum <= 0) { toast("配比全为 0，请至少给一档权重", false); return; }
    applyCfg(cfg);
    mask.remove();
    toast("配比已保存");
  };
  foot.appendChild(cancel); foot.appendChild(save);
  win.appendChild(foot);
  mask.appendChild(win);
  document.body.appendChild(mask);
}

/* ---------- 面板骨架 ---------- */
function rerenderTab() {
  if (!panel) return;
  const kind = st.tab;
  panel.tFree?.classList.toggle("on", kind === "free");
  panel.tTpl?.classList.toggle("on", kind === "tpl");
  panel.tScene?.classList.toggle("on", kind === "scene");
  if (panel.kindSel) panel.kindSel.style.display = kind === "tpl" ? "" : "none";
  panel.left.innerHTML = "";
  if (kind === "free") {
    if (dst.lib === "error") { panel.left.appendChild(errBlock("词库", "lib")); return; }
    if (!lib) { panel.left.appendChild(el("div", "empty", "词库加载中…")); return; }
    buildFreeTab(panel.left);
  } else if (kind === "tpl") {
    if (dst.tpl === "error") { panel.left.appendChild(errBlock("模板", "tpl")); return; }
    if (dst.sceneMeta === "error") { panel.left.appendChild(errBlock("场景标记", "sceneMeta")); return; }
    if (!tpl || !sceneMeta) { panel.left.appendChild(el("div", "empty", "模板加载中…")); return; }
    buildTplTab(panel.left);
  } else {
    if (dst.scenes === "error") { panel.left.appendChild(errBlock("场景包", "scenes")); return; }
    if (dst.sceneMeta === "error") { panel.left.appendChild(errBlock("场景标记", "sceneMeta")); return; }
    if (!scenes || !sceneMeta) { panel.left.appendChild(el("div", "empty", "场景包加载中…")); return; }
    buildSceneTab(panel.left);
  }
  if (st.tab === "free") { panel.cards = null; panel.pageInfo = null; }
  if (dst.flags === "error" && panel.conflict) panel.conflict.title = "冲突索引未加载，无法检查冲突";
}

function errBlock(label, key) {
  const box = el("div", "errbox");
  box.appendChild(el("div", "em", `${label}加载失败`));
  box.appendChild(el("div", "eh", "后端没响应或路由不存在，确认 ComfyUI 已重启并加载本插件。"));
  const b = el("div", "btn main", "重试");
  b.style.flex = "0 0 90px";
  b.onclick = () => { box.innerHTML = ""; box.appendChild(el("div", "empty", "重试中…")); retryData(key); };
  box.appendChild(b);
  return box;
}

function openPanel(node) {
  closePanel();
  st.node = node;
  st.favTags = lsGet(FAV_TAG_KEY, []);
  st.favTpl = lsGet(FAV_TPL_KEY, []);
  st.recent = lsGet(RECENT_KEY, []);
  st.zh = lsGet(ZH_KEY, true);
  st.tplLevel = lsGet(TPL_LEVEL_KEY, "all");
  const cur = node?.widgets?.find((x) => x.name === "template_override")?.value || "";
  st.selected = tagsOf(cur);
  st.undo = []; st.redo = []; st.q = ""; st.tab = "free";

  const root = el("div", "pf-mask");
  const win = el("div", "pf-win");
  root.appendChild(win);

  const head = el("div", "head");
  const logo = el("div", "logo");
  logo.innerHTML = "⚙ Prompt Forge <small>提示词工作台 · v0.12</small>";
  head.appendChild(logo);

  const tabs = el("div", "tabs");
  const tFree = el("div", "tab on", "🎛 自由选词");
  const tTpl = el("div", "tab", "🗂 模板卡片");
  const tScene = el("div", "tab", "🏞 场景包");
  tFree.onclick = () => switchTab("free");
  tTpl.onclick = () => switchTab("tpl");
  tScene.onclick = () => switchTab("scene");
  tabs.appendChild(tFree); tabs.appendChild(tTpl); tabs.appendChild(tScene);
  head.appendChild(tabs);

  head.appendChild(el("div", "grow"));

  const kindSel = el("select", "sel");
  [["all", "全部类型"], ["normal", "普通"], ["monster", "异种"]].forEach(([v, t]) => {
    const o = el("option", null, t);
    o.value = v;
    kindSel.appendChild(o);
  });
  kindSel.onchange = () => { st.kind = kindSel.value; st.tplShown = BATCH_TPL; renderCards(); };
  kindSel.style.display = "none";
  head.appendChild(kindSel);

  const search = el("input", "search");
  search.placeholder = "搜索词条 / 场景，如 bikini、bedroom";
  const doSearch = debounce(() => {
    if (st.tab === "free") { st.freeShown = BATCH_FREE; renderFreeList(); }
    else if (st.tab === "tpl") { st.tplShown = BATCH_TPL; buildLevelBar(); renderCards(); }
  }, 150);
  search.oninput = () => { st.q = search.value; doSearch(); };
  head.appendChild(search);

  const undoBtn = el("div", "icobtn", "↶");
  undoBtn.title = "撤销（Ctrl+Z）";
  undoBtn.onclick = doUndo;
  const redoBtn = el("div", "icobtn", "↷");
  redoBtn.title = "重做（Ctrl+Shift+Z）";
  redoBtn.onclick = doRedo;
  head.appendChild(undoBtn); head.appendChild(redoBtn);

  const setBtn = el("div", "icobtn", "⚙");
  setBtn.title = "设置（档位分布 / any 配比 / 导入导出）";
  setBtn.onclick = openSettings;
  head.appendChild(setBtn);

  const x = el("div", "x", "✕");
  x.onclick = closePanel;
  head.appendChild(x);
  win.appendChild(head);

  const body = el("div", "body");
  win.appendChild(body);
  const left = el("div");
  left.style.cssText = "flex:1;display:flex;min-width:0;min-height:0";
  body.appendChild(left);

  panel = {
    root, win, body, left, out: null, picked: null, cnt: null, stat: null,
    conflict: null, freeRows: [], freeMain: null, cards: null, pageInfo: null,
    tFree, tTpl, tScene, kindSel, setMask: null, lvbar: null, favBar: null,
  };

  const right = el("div", "right");
  const rh = el("div", "r-h");
  rh.appendChild(el("b", null, "已选词条"));
  rh.appendChild(el("span", null, "按点击顺序"));
  const cnt = el("span", "cnt", `0 / ${MAX_SELECTED}`);
  rh.appendChild(cnt);
  right.appendChild(rh);
  const stat = el("div", "stat", "0 条 · 估算 0 token");
  right.appendChild(stat);
  const conflict = el("div", "conflict");
  conflict.style.display = "none";
  right.appendChild(conflict);
  const sync = el("div", "sync");
  sync.innerHTML = "<i></i>勾选即写回节点，取消勾选会一起删掉";
  right.appendChild(sync);
  const picked = el("div", "picked");
  right.appendChild(picked);
  const outwrap = el("div", "outwrap");
  const out = el("textarea", "out");
  out.placeholder = "这里是从节点读到的 / 手写的提示词";
  out.oninput = () => {
    st.selected = tagsOf(out.value);
    const nd = st.node;
    if (nd) {
      const w = nd.widgets?.find((xx) => xx.name === "template_override");
      if (w) { w.value = out.value; if (w.inputEl) w.inputEl.value = out.value; nd.setDirtyCanvas(true, true); }
    }
    renderPicked();
    renderStats();
  };
  outwrap.appendChild(out);
  const row = el("div");
  row.style.cssText = "display:flex;gap:8px";
  const rnd = el("div", "btn", "🎲 随机一份");
  rnd.onclick = () => rollFromNode();
  const clr = el("div", "btn", "🧹 清空");
  clr.onclick = () => { if (!st.selected.length) return; pushUndo(); st.selected = []; syncNode(); renderFreeList(); };
  row.appendChild(rnd); row.appendChild(clr);
  outwrap.appendChild(row);
  right.appendChild(outwrap);
  const btns = el("div", "btns");
  const cpy = el("div", "btn", "复制");
  cpy.onclick = () => copyText(nodeText());
  const wr = el("div", "btn main", "写回节点");
  wr.onclick = () => { syncNode(); toast("已写入节点"); };
  btns.appendChild(cpy); btns.appendChild(wr);
  right.appendChild(btns);
  body.appendChild(right);
  panel.out = out; panel.picked = picked; panel.cnt = cnt; panel.stat = stat;
  panel.conflict = conflict;
  renderPicked();
  renderStats();

  document.body.appendChild(root);
  root.addEventListener("mousedown", (e) => { if (e.target === root) closePanel(); });

  const keyHandler = (e) => {
    if (!panel) return;
    if (e.key === "Escape") {
      if (panel.setMask) { panel.setMask.remove(); panel.setMask = null; }
      else if (document.querySelector(".pf-mini-mask")) document.querySelector(".pf-mini-mask").remove();
      else closePanel();
      e.stopPropagation();
    } else if (e.key.toLowerCase() === "f" && (e.ctrlKey || e.metaKey)) {
      search.focus();
      search.select();
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === "Enter" && document.activeElement !== out) {
      syncNode();
      toast("已写入节点");
      e.stopPropagation();
    } else if (e.key.toLowerCase() === "z" && (e.ctrlKey || e.metaKey)) {
      if (e.shiftKey) doRedo(); else doUndo();
      e.preventDefault();
      e.stopPropagation();
    }
  };
  panel.keyHandler = keyHandler;
  window.addEventListener("keydown", keyHandler, true);

  Promise.allSettled([
    loadUserdata().then(() => { rerenderTab(); }),
    loadInto("lib", "/prompt_forge/library", applyLib),
    loadInto("tpl", "/prompt_forge/templates", (j) => { tpl = j.items || []; }),
    loadInto("sceneMeta", "/prompt_forge/scene_meta", (j) => { sceneMeta = j || {}; }),
    loadInto("scenes", "/prompt_forge/scenes", (j) => { scenes = j || { bundles: [] }; }),
    loadInto("flags", "/prompt_forge/tag_flags", (j) => { tagFlags = j || {}; }),
  ]).then(() => { if (panel) rerenderTab(); });

  function switchTab(kind) {
    st.tab = kind;
    rerenderTab();
  }
}

/* 用节点当前参数随机一份（REQ-110） */
function rollFromNode() {
  const node = st.node;
  const get = (n, d) => {
    const w = node?.widgets?.find((x) => x.name === n);
    return w ? w.value : d;
  };
  const payload = {
    level: keyOfLevel(get("level", "sfw")),
    seed: -1,
    tag_cap: Number(get("tag_cap", 0)) || 0,
    base_prob: Number(get("base_prob", 0.65)),
    slot_weights: get("slot_weights", "") || "",
    role_mode: { 不指定: "none", 随机: "random", 指定: "specified" }[get("role_mode", "不指定")] || "none",
    role_name: get("role_name", "") || "",
    role_works: get("role_works", "") || "",
    quality_prefix: get("quality_on", true) ? (get("quality_prefix", "") || "") : "",
    artist_on: !!get("artist_on", false),
    negative_on: !!get("negative_on", true),
    extra_body: get("extra_body", "") || "",
    scene_mode: String(get("scene_mode", "")).startsWith("场景成套") ? "scene" : "free",
    template_override: "",
    override_mode: get("override_mode", "直通") === "混合" ? "mixed" : "direct",
    role_prompt: node?.inputs?.find?.((i) => i.name === "role_prompt")?.link ? "__linked__" : "",
    // 这两个开关以前没传过去，导致面板"随机一份"和直接排队的结果不一致
    appearance_follow: get("appearance_follow", true) !== false,
    outfit_follow: !!get("outfit_follow", false),
  };
  // 角色输入若已连线，交给后端按节点输入取；前端拿不到上游值，只能不带
  if (payload.role_prompt === "__linked__") payload.role_prompt = "";
  pfFetch("/prompt_forge/roll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }).then((j) => {
    setSelected(tagsOf(j.positive || ""));
    renderFreeList();
    toast(`已随机一份（目标 Lv${j.target_level ?? "?"}）并写入节点`);
  }).catch((e) => toast(`随机失败：${e.message || e}`, false));
}

/* ---------- CSS ---------- */
const CSS = `
.pf-mask{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:99999;display:flex;align-items:center;justify-content:center}
.pf-win{width:min(1360px,95vw);height:min(820px,90vh);background:#1b1c21;border:1px solid #2e3037;border-radius:14px;
  display:flex;flex-direction:column;overflow:hidden;color:#e3e6ec;box-shadow:0 24px 80px rgba(0,0,0,.6);position:relative;
  font:13px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
.pf-win .head{display:flex;align-items:center;gap:10px;padding:0 16px;height:58px;border-bottom:1px solid #2e3037;flex:0 0 auto}
.pf-win .logo{font-weight:700;color:#e6b45c;white-space:nowrap}
.pf-win .logo small{color:#666c77;font-weight:400;margin-left:6px}
.pf-win .tabs{display:flex;gap:6px;margin-left:8px}
.pf-win .tab{padding:7px 15px;border-radius:9px;background:#22242a;color:#8d939e;cursor:pointer;border:1px solid transparent}
.pf-win .tab.on{background:linear-gradient(180deg,#2b2e36,#24262c);color:#fff;border-color:#e6b45c;box-shadow:inset 0 -2px 0 #e6b45c}
.pf-win .grow{flex:1}
.pf-win .sel{padding:6px 9px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec}
.pf-win .search{width:220px;padding:6px 11px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;outline:none}
.pf-win .search::placeholder{color:#666c77}
.pf-win .icobtn{width:30px;height:30px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#b9c1cd;
  display:grid;place-items:center;cursor:pointer;font-size:14px}
.pf-win .icobtn:hover{border-color:#4a4e59;color:#fff}
.pf-win .x{width:30px;height:30px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#8d939e;display:grid;place-items:center;cursor:pointer}
.pf-win .body{flex:1;display:flex;min-height:0}
.pf-win .free-wrap{flex:1;display:flex;min-width:0;min-height:0}
.pf-win .f-main{flex:1;display:flex;flex-direction:column;min-width:0}
.pf-win .f-mh{display:flex;align-items:center;gap:10px;padding:12px 16px 6px}
.pf-win .f-mh b{font-size:15px}
.pf-win .f-mh .n{color:#666c77;font-size:11.5px}
.pf-win .f-mh .grow{flex:1}
.pf-win .f-mh .zh-t{display:flex;align-items:center;gap:6px;color:#b9c1cd;font-size:12px;cursor:pointer}
.pf-win .f-mh .zh-t .box{width:15px;height:15px;border-radius:3px;background:#4f3cb8;display:grid;place-items:center;color:#fff;font-size:11px}
.pf-win .f-mh .zh-t.off .box{background:#262931;color:#666c77}
.pf-win .f-scroll{flex:1;overflow:auto;padding:0 16px 18px}
.pf-win .f-sec{margin-top:8px}
.pf-win .f-sec-h{display:flex;align-items:center;gap:8px;padding:7px 0;color:#8d939e;font-size:12.5px;border-bottom:1px solid #24262c}
.pf-win .f-sec-h b{color:#e3e6ec;font-size:13px}
.pf-win .f-sec-h .n{color:#666c77;font-size:11.5px}
.pf-win .f-chips{display:flex;flex-wrap:wrap;gap:8px 9px;padding:10px 0 2px}
.pf-win .more{margin:8px 0 2px;color:#e6b45c;font-size:11.5px;cursor:pointer}
.pf-win .fchip{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:99px;background:#24262c;border:1px solid #2f323a;color:#cfd5df;cursor:pointer;font-size:12.5px;white-space:nowrap}
.pf-win .fchip:hover{border-color:#4a4e59}
.pf-win .fchip.on{border-color:#3f8f6f;background:rgba(63,143,111,.12);color:#d6f2e5;box-shadow:0 0 0 1px rgba(63,143,111,.35) inset}
.pf-win .fchip .ck{display:none;width:13px;height:13px;border-radius:3px;background:#3f8f6f;place-items:center;font-size:10px;color:#fff}
.pf-win .fchip.on .ck{display:grid}
.pf-win .fchip .zh{color:#666c77;font-size:11.5px}
.pf-win .fchip.on .zh{color:#9ec9b4}
.pf-win .fchip .star{font-size:11px;color:#666c77}
.pf-win .fchip.fav .star{color:#e6b45c}
.pf-win .empty{color:#666c77;padding:6px 2px;font-size:12px}
.pf-win .errbox{margin:24px;padding:18px;border:1px solid #5a2f2f;background:rgba(138,43,43,.12);border-radius:10px;display:flex;flex-direction:column;gap:8px;align-items:flex-start}
.pf-win .errbox .em{color:#f0a9a9;font-weight:600}
.pf-win .errbox .eh{color:#8d939e;font-size:12px}
.pf-win .right{width:344px;border-left:1px solid #2e3037;display:flex;flex-direction:column;min-height:0;background:#191a1f}
.pf-win .r-h{padding:10px 14px;border-bottom:1px solid #2e3037;display:flex;align-items:center;gap:8px;color:#8d939e;font-size:12px}
.pf-win .r-h b{color:#e3e6ec;font-size:13px}
.pf-win .r-h .cnt{margin-left:auto;color:#666c77;font-size:11px}
.pf-win .stat{padding:5px 14px 7px;color:#666c77;font-size:11px;border-bottom:1px solid #2e3037}
.pf-win .stat.warn{color:#e6b45c}
.pf-win .stat.bad{color:#e08a8a}
.pf-win .conflict{padding:6px 14px;background:rgba(230,180,92,.1);color:#ecc98a;font-size:11.5px;border-bottom:1px solid #2e3037;line-height:1.45}
.pf-win .sync{display:flex;align-items:center;gap:6px;padding:7px 14px;color:#7fd0aa;font-size:11.5px;border-bottom:1px solid #2e3037;background:rgba(63,143,111,.08)}
.pf-win .sync i{width:7px;height:7px;border-radius:50%;background:#3f8f6f}
.pf-win .picked{max-height:150px;overflow:auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}
.pf-win .pk{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:7px;background:#262931;border:1px solid #343842;font-size:11.5px;color:#cfd5df}
.pf-win .pk i{font-style:normal;color:#666c77;cursor:pointer}
.pf-win .outwrap{flex:1;padding:8px 14px 0;display:flex;flex-direction:column;gap:8px;min-height:0}
.pf-win .out{flex:1;background:#202127;border:1px solid #383b43;border-radius:10px;padding:10px 12px;
  font:12px/1.7 Consolas,monospace;color:#b9c1cd;resize:none;outline:none}
.pf-win .btns{display:flex;gap:8px;padding:10px 14px 14px}
.pf-win .btn{flex:1;text-align:center;padding:8px 10px;border-radius:9px;background:#262931;border:1px solid #3a3e48;color:#dde2ea;cursor:pointer;font-size:12.5px}
.pf-win .btn:hover{border-color:#4a4e59}
.pf-win .btn.main{background:linear-gradient(180deg,#3f8f6f,#35795d);border-color:#4aa17c;color:#fff;font-weight:600}
.pf-win .btn.gold{background:rgba(230,180,92,.14);border-color:#6d5733;color:#ecc98a}
.pf-win .side{width:206px;border-right:1px solid #2e3037;display:flex;flex-direction:column;background:#191a1f}
.pf-win .side-h{padding:12px 14px 8px;color:#8d939e;font-size:12px;display:flex;justify-content:space-between;align-items:center}
.pf-win .side-h b{color:#e3e6ec;font-size:13px}
.pf-win .side-list{flex:1;overflow:auto;padding:0 8px 12px}
.pf-win .cat{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;color:#8d939e;cursor:pointer}
.pf-win .cat:hover{background:#212329;color:#e3e6ec}
.pf-win .cat.on{background:#262931;color:#fff}
.pf-win .cat .ico{width:18px;text-align:center}
.pf-win .cat .nm{flex:1;font-size:12.5px}
.pf-win .favbar{padding:9px 14px;border-top:1px solid #2e3037;color:#e6b45c;font-size:12px;cursor:pointer}
.pf-win .favbar.off{color:#666c77}
.pf-win .main{flex:1;display:flex;flex-direction:column;min-width:0}
.pf-win .lvbar{display:flex;align-items:center;gap:7px;padding:9px 15px;border-bottom:1px solid #2e3037;flex-wrap:wrap}
.pf-win .lvbar .lb{color:#666c77;font-size:11.5px;margin-right:2px}
.pf-win .lvbar .grow{flex:1}
.pf-win .lvpill{padding:4px 10px;border-radius:99px;background:#23252b;border:1px solid #33363e;color:#8d939e;font-size:11.5px;cursor:pointer}
.pf-win .lvpill:hover{border-color:#4a4e59;color:#dde2ea}
.pf-win .lvpill.on{background:rgba(230,180,92,.14);border-color:#6d5733;color:#ecc98a}
.pf-win .cards{flex:1;overflow:auto;padding:13px 15px;display:flex;flex-wrap:wrap;gap:12px;align-content:flex-start}
.pf-win .card{width:calc((100% - 24px)/3);box-sizing:border-box;background:#202127;border:1px solid #2e3037;border-radius:12px;display:flex;flex-direction:column;overflow:hidden}
.pf-win .card-h{display:flex;align-items:center;gap:7px;padding:9px 11px;border-bottom:1px solid #2e3037}
.pf-win .card-h .no{color:#666c77;font-size:11px}
.pf-win .card-h .nm{font-size:12.5px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-win .card-h .star{color:#666c77;cursor:pointer;font-size:13px}
.pf-win .card-h .star.on{color:#e6b45c}
.pf-win .card-h .badge{font-size:10.5px;padding:2px 7px;border-radius:99px;background:#262931;color:#8d939e}
.pf-win .badge.mon{background:rgba(138,90,208,.2);color:#c4a8f0}
.pf-win .card-meta{padding:7px 11px;color:#8d939e;font-size:11.5px;display:flex;flex-wrap:wrap;gap:5px 9px}
.pf-win .card-tags{display:flex;flex-wrap:wrap;gap:5px;padding:0 11px 9px;max-height:210px;overflow:auto}
.pf-win .card-tags .tg{font:11px/1.5 Consolas,monospace;padding:2px 6px;border-radius:6px;background:#262931;border:1px solid #31343d;color:#aeb6c2;cursor:pointer}
.pf-win .card-tags .tg:hover{border-color:#4a4e59;color:#e3e6ec}
.pf-win .card-tags .tg.on{background:rgba(63,143,111,.16);border-color:#3f8f6f;color:#d6f2e5}
.pf-win .tag-fold{padding:0 11px 9px;color:#8d939e;font-size:11.5px;cursor:pointer}
.pf-win .tag-fold:hover{color:#dde2ea}
.pf-win .tag-fold.on{color:#e6b45c}
.pf-win .card-btns{display:flex;gap:7px;padding:9px 11px;margin-top:auto;border-top:1px solid #2e3037}
.pf-win .card-btns .btn{padding:6px 8px;font-size:11.5px}
.pf-win .scard{width:calc((100% - 24px)/3);box-sizing:border-box;background:#202127;border:1px solid #2e3037;border-radius:12px;display:flex;flex-direction:column;overflow:hidden}
.pf-win .srows{padding:6px 11px 4px;display:flex;flex-direction:column;gap:3px}
.pf-win .srow{display:flex;gap:6px;font-size:11px;line-height:1.5}
.pf-win .srow .k{color:#666c77;flex:0 0 30px}
.pf-win .srow .v{color:#aeb6c2;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-win .foot{display:flex;align-items:center;gap:12px;padding:8px 15px;border-top:1px solid #2e3037;color:#666c77;font-size:11px;flex:0 0 auto}
.pf-cover{position:absolute;inset:0;background:rgba(10,11,14,.72);display:flex;align-items:center;justify-content:center;z-index:20}
.pf-set{width:min(760px,92%);max-height:88%;background:#1b1c21;border:1px solid #34373f;border-radius:12px;display:flex;flex-direction:column;overflow:hidden}
.pf-set .sh{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid #2e3037}
.pf-set .sh b{flex:1;font-size:13.5px;color:#e3e6ec}
.pf-set .x{width:26px;height:26px;border-radius:7px;background:#23252b;border:1px solid #383b43;color:#8d939e;display:grid;place-items:center;cursor:pointer}
.pf-set .sbody{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.pf-set .sec-t{color:#e3e6ec;font-size:12.5px;font-weight:600;margin-top:6px}
.pf-set .note{color:#666c77;font-size:11.5px;line-height:1.5}
.pf-set .swrow{display:flex;align-items:center;gap:9px;cursor:pointer;padding:6px 0}
.pf-set .swrow .box{width:16px;height:16px;border-radius:4px;background:#262931;display:grid;place-items:center;color:#666c77;font-size:11px}
.pf-set .swrow .box.on{background:#3f8f6f;color:#fff}
.pf-set .swrow .lb{color:#cfd5df;font-size:12.5px}
.pf-set .swrow .hint{color:#666c77;font-size:11.5px}
.pf-set table.matrix{border-collapse:collapse;font-size:11.5px}
.pf-set table.matrix th{color:#8d939e;font-weight:500;padding:4px 7px;text-align:center;white-space:nowrap}
.pf-set table.matrix td{padding:3px 5px;text-align:center}
.pf-set table.matrix tr.bad td{background:rgba(138,43,43,.14)}
.pf-set table.matrix td.locked{background:#17181c}
.pf-set .mi{width:52px;padding:3px 5px;border-radius:6px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;text-align:center;font-size:11.5px}
.pf-set .mi:disabled{color:#4a4e59;background:#1a1b20}
.pf-set .pct{display:block;color:#666c77;font-size:10px;margin-top:1px}
.pf-set .sum{color:#8d939e;margin-right:5px}
.pf-set .mini{color:#e6b45c;cursor:pointer;font-size:10.5px;border-bottom:1px dashed #6d5733}
.pf-set .anyrow{display:flex;gap:10px;flex-wrap:wrap}
.pf-set .acell{display:flex;flex-direction:column;gap:2px;align-items:center}
.pf-set .acell .lb{color:#8d939e;font-size:11px}
.pf-set .hist{display:flex;align-items:flex-end;gap:9px;height:96px;padding:6px 2px}
.pf-set .hcol{display:flex;flex-direction:column;align-items:center;gap:3px;flex:1}
.pf-set .hbar{width:100%;max-width:46px;background:linear-gradient(180deg,#5a9c7c,#356b52);border-radius:4px}
.pf-set .hv{color:#8d939e;font-size:10px}
.pf-set .hk{color:#666c77;font-size:10px}
.pf-set .io{display:flex;gap:8px}
.pf-set .io .btn{flex:0 0 auto;padding:6px 12px}
.pf-set .sfoot{display:flex;gap:8px;padding:12px 16px;border-top:1px solid #2e3037}
.pf-set .sfoot .btn{flex:0 0 auto;padding:7px 18px}
.pf-set .sfoot .btn.main{margin-left:auto}
.pf-mini-mask{position:fixed;inset:0;background:rgba(8,9,12,.66);z-index:100002;display:flex;align-items:center;justify-content:center}
.pf-mini{width:min(430px,92vw);background:#1b1c21;border:1px solid #34373f;border-radius:12px;padding:16px;
  display:flex;flex-direction:column;gap:12px;color:#e3e6ec;font:13px/1.6 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  box-shadow:0 20px 60px rgba(0,0,0,.6)}
.pf-mini.wide{width:min(620px,94vw)}
.pf-mini .t{color:#dde2ea;font-size:12.5px;line-height:1.55}
.pf-mini .row{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
.pf-mini .btn{flex:0 0 auto;padding:7px 16px;border-radius:9px;background:#262931;border:1px solid #3a3e48;color:#dde2ea;cursor:pointer;font-size:12.5px}
.pf-mini .btn:hover{border-color:#4a4e59}
.pf-mini .btn.main{background:linear-gradient(180deg,#3f8f6f,#35795d);border-color:#4aa17c;color:#fff;font-weight:600}
.pf-mini .anyrow{display:flex;gap:10px;flex-wrap:wrap}
.pf-mini .acell{display:flex;flex-direction:column;gap:2px;align-items:center}
.pf-mini .acell .lb{color:#8d939e;font-size:11px}
.pf-mini .mi{width:56px;padding:4px 6px;border-radius:6px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;text-align:center;font-size:12px}
.pf-mini .pct{display:block;color:#666c77;font-size:10px}
.pf-mini .swrow{display:flex;align-items:center;gap:9px;cursor:pointer}
.pf-mini .swrow .box{width:16px;height:16px;border-radius:4px;background:#262931;display:grid;place-items:center;color:#666c77;font-size:11px}
.pf-mini .swrow .box.on{background:#3f8f6f;color:#fff}
.pf-mini .swrow .lb{color:#b9c1cd;font-size:12px}
.pf-mini .imp{width:100%;height:150px;resize:vertical;background:#202127;border:1px solid #383b43;border-radius:8px;
  padding:8px 10px;color:#cfd5df;font:11.5px/1.6 Consolas,monospace;outline:none}
`;
if (!document.getElementById("pf-style")) {
  const s = document.createElement("style");
  s.id = "pf-style";
  s.textContent = CSS;
  document.head.appendChild(s);
}

/* 供 v6.js 使用的桥：档位切 any 时的配比弹窗与配置缓存 */
window.__pfBridge = {
  cfg: null,
  openAnyPopup: anyPopup,
  getCfg: () => cfgOrDefault(),
  reloadCfg: () => loadUserdata().then(() => { window.__pfBridge.cfg = st.cfg; return st.cfg; })
    .catch(() => cfgOrDefault()),
};

export { openPanel };
