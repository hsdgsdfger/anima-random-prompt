const pfFetch = (u) => (globalThis.__pfFetch ? globalThis.__pfFetch(u) : fetch(u));
/* Prompt Forge 工作台：自由选词（按档位折叠 + 收藏 + 实时写回节点） + 模板卡片 */
const LEVELS = [
  ["sfw", "0 · 全年龄", "无任何裸露向标签"],
  ["suggestive", "1 · 擦边", "轻度暗示：露肩 / 短裙 / 内衣轮廓 / 材质诱惑"],
  ["explicit", "2 · 成人", "明显裸露或透视：全裸 / 性器官 / 乳头 / 内衣外露 / 半脱"],
  ["hardcore", "3 · 过激", "性行为 / 性道具 / 体液 / 束缚调教"],
  ["extreme", "4 · 极端", "极端插入扩张 / 拘束装置 / 极限体液 / 主奴标记"],
];
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

let lib = null, tpl = null, sceneMeta = null;
const st = {
  node: null, tab: "free", q: "", kind: "all", cat: "all", fcat: "all",
  zh: true, recent: [], page: 0, onlyFav: false, selected: [], favTags: [], favTpl: [],
};

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

/* ---------- 数据 ---------- */
let libCats = null;
function loadLib() {
  if (lib) return Promise.resolve(lib);
  return pfFetch("/prompt_forge/library").then((r) => r.json()).then((j) => {
    libCats = (j.cats || []).map((c) => ({
      id: c.id, name: c.name, icon: c.icon || "",
      tags: c.tags.map((t) => ({ en: t.en, zh: t.zh, cat: c.name })),
    }));
    lib = libCats.flatMap((c) => c.tags);
    return lib;
  });
}
function loadTpl() {
  if (tpl) return Promise.resolve(tpl);
  return pfFetch("/prompt_forge/templates").then((r) => r.json()).then((j) => {
    tpl = j.items || [];
    return tpl;
  });
}
function loadSceneMeta() {
  if (sceneMeta) return Promise.resolve(sceneMeta);
  return pfFetch("/prompt_forge/scene_meta").then((r) => r.json()).then((j) => {
    sceneMeta = j || {};
    return sceneMeta;
  });
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
  if (panel?.cnt) panel.cnt.textContent = `${st.selected.length} / 60`;
}
function toggleTag(en) {
  const i = st.selected.indexOf(en);
  if (i >= 0) st.selected.splice(i, 1);
  else if (st.selected.length < 60) { st.selected.push(en); pushRecent(en); }
  syncNode();
  if (panel) refreshChipStates();
}
function pushRecent(en) {
  const i = st.recent.indexOf(en);
  if (i >= 0) st.recent.splice(i, 1);
  st.recent.unshift(en);
  if (st.recent.length > 20) st.recent.length = 20;
  lsSet(RECENT_KEY, st.recent);
  refreshSideCounts();
}
function refreshSideCounts() {
  if (!panel?.freeRows) return;
  for (const r of panel.freeRows) {
    if (r.key === "fav") r.n.textContent = String(st.favTags.length);
    if (r.key === "recent") r.n.textContent = String(st.recent.length);
  }
}

/* ---------- 面板 ---------- */
let panel = null;
function closePanel() { if (panel) { panel.root.remove(); panel = null; } }

function renderPicked() {
  const box = panel.picked;
  box.innerHTML = "";
  st.selected.forEach((en) => {
    const chip = el("span", "pk", en);
    const x = el("i", null, "✕");
    x.onclick = () => { toggleTag(en); };
    chip.appendChild(x);
    box.appendChild(chip);
  });
}

function chipOf(t, favSet) {
  const on = st.selected.includes(t.en);
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
    lsSet(FAV_TAG_KEY, st.favTags);
    refreshSideCounts();
    refreshChipStates();
    if (st.fcat === "fav") renderFreeList();
  };
  chip.appendChild(star);
  chip.onclick = () => toggleTag(t.en);
  return chip;
}

function refreshChipStates() {
  if (!panel?.freeMain) return;
  const favSet = new Set(st.favTags);
  panel.freeMain.querySelectorAll(".fchip").forEach((c) => {
    const en = c.dataset.en;
    const on = st.selected.includes(en);
    c.classList.toggle("on", on);
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
  const box = panel.freeMain;
  box.innerHTML = "";
  const byEn = new Map(lib.map((t) => [t.en, t]));

  const pushSec = (title, tags) => {
    const shown = tags.filter(hit);
    if (!shown.length && q) return 0;
    const sec = el("div", "f-sec");
    const h = el("div", "f-sec-h");
    h.appendChild(el("b", null, title));
    h.appendChild(el("span", "n", String(shown.length)));
    sec.appendChild(h);
    const wrap = el("div", "f-chips");
    shown.forEach((t) => wrap.appendChild(chipOf(t, favSet)));
    sec.appendChild(wrap);
    box.appendChild(sec);
    return shown.length;
  };

  let title = "全部", count = 0;
  if (st.fcat === "fav") {
    title = "收藏";
    count = pushSec("★ 我的收藏", st.favTags.map((e) => byEn.get(e)).filter(Boolean));
  } else if (st.fcat === "recent") {
    title = "最近";
    count = pushSec("◷ 最近点过", st.recent.map((e) => byEn.get(e)).filter(Boolean));
  } else if (st.fcat !== "all") {
    const c = libCats.find((x) => x.id === st.fcat);
    title = c ? c.name : "全部";
    count = c ? pushSec(c.name, c.tags) : 0;
  } else {
    title = "全部";
    libCats.forEach((c) => { count += pushSec(c.name, c.tags); });
  }
  if (!count) box.appendChild(el("div", "empty", q ? "没有匹配的词条" : "这里还是空的，去别的分类挑吧"));
  if (panel.freeTitle) panel.freeTitle.textContent = title;
  if (panel.freeCount) panel.freeCount.textContent = `${count} 个标签`;
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
      rows.forEach((r) => r.row.classList.toggle("on", r.key === key));
      renderFreeList();
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

/* ---------- 模板页 ---------- */
function cardOf(item) {
  const fav = st.favTpl.includes(item.id);
  const card = el("div", "card");
  const head = el("div", "card-h");
  head.appendChild(el("span", "no", `#${String(item.index).padStart(3, "0")}`));
  head.appendChild(el("span", "nm", (SCENE_ZH[item.bundle] || item.bundle) + (item.kind === "monster" ? " · 异种" : "")));
  const badge = el("span", "badge" + (item.kind === "monster" ? " mon" : ""), item.level);
  head.appendChild(badge);
  const star = el("span", "star" + (fav ? " on" : ""), fav ? "★" : "☆");
  star.onclick = () => {
    const i = st.favTpl.indexOf(item.id);
    if (i >= 0) st.favTpl.splice(i, 1); else st.favTpl.push(item.id);
    lsSet(FAV_TPL_KEY, st.favTpl);
    renderCards();
  };
  head.appendChild(star);
  card.appendChild(head);

  const tags = item.prompt.split(",").map((s) => s.trim()).filter(Boolean);
  const meta = el("div", "card-meta");
  [item.kind === "monster" ? "异种" : "普通",
   tags.includes("2girls") ? "2girls duo" : "1girl solo",
   `${tags.length} 标签`, SCENE_ZH[item.bundle] || item.bundle].forEach((x) => meta.appendChild(el("span", null, x)));
  card.appendChild(meta);

  const tagBox = el("div", "card-tags");
  tagBox.style.display = "none";
  tags.forEach((t) => tagBox.appendChild(el("span", "tg", t)));
  card.appendChild(tagBox);

  const fold = el("div", "tag-fold", `▸ 展开 ${tags.length} 个标签`);
  fold.onclick = () => {
    const open = tagBox.style.display !== "none";
    tagBox.style.display = open ? "none" : "flex";
    fold.textContent = open ? `▸ 展开 ${tags.length} 个标签` : "▾ 收起标签";
    fold.classList.toggle("on", !open);
  };
  card.appendChild(fold);

  const btns = el("div", "card-btns");
  const b1 = el("div", "btn", "复制");
  b1.onclick = () => copyText(item.prompt);
  const b2 = el("div", "btn gold", "套用到节点");
  b2.onclick = () => {
    st.selected = tags;
    syncNode();
    copyText(item.prompt);
    toast("已写入节点，排队即可出图");
  };
  btns.appendChild(b1); btns.appendChild(b2);
  card.appendChild(btns);
  return card;
}

function renderCards() {
  if (!panel) return;
  const wrap = panel.cards;
  const q = st.q.trim().toLowerCase();
  let items = tpl.filter((x) => {
    if (st.kind !== "all" && x.kind !== st.kind) return false;
    if (st.cat !== "all" && (sceneMeta?.[x.bundle]?.[st.cat] !== true)) return false;
    if (st.onlyFav && !st.favTpl.includes(x.id)) return false;
    if (q && !(x.prompt.toLowerCase().includes(q) || (SCENE_ZH[x.bundle] || "").includes(q))) return false;
    return true;
  });
  const pageSize = 9;
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  st.page = Math.min(st.page, pages - 1);
  const pageItems = items.slice(st.page * pageSize, st.page * pageSize + pageSize);
  wrap.innerHTML = "";
  if (!pageItems.length) { wrap.appendChild(el("div", "empty", "没有匹配的模板")); }
  pageItems.forEach((it) => wrap.appendChild(cardOf(it)));
  if (panel.pageInfo) {
    panel.pageInfo.textContent = `${items.length} 条 · 第 ${st.page + 1}/${pages} 页`;
  }
  if (panel.prev) panel.prev.style.opacity = st.page > 0 ? "1" : ".35";
  if (panel.next) panel.next.style.opacity = st.page < pages - 1 ? "1" : ".35";
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
                ["monster", "异种", "🧬"]];
  cats.forEach(([key, label, ico]) => {
    const row = el("div", "cat" + (st.cat === key ? " on" : ""));
    row.appendChild(el("span", "ico", ico));
    row.appendChild(el("span", "nm", label));
    row.onclick = () => { st.cat = key; st.page = 0; rebuildTpl(); };
    list.appendChild(row);
  });
  side.appendChild(list);
  const favbar = el("div", "favbar" + (st.onlyFav ? "" : " off"), `★ 只看我的收藏 (${st.favTpl.length})`);
  favbar.onclick = () => { st.onlyFav = !st.onlyFav; st.page = 0; rebuildTpl(); };
  side.appendChild(favbar);
  container.appendChild(side);

  const main = el("div", "main");
  const cards = el("div", "cards");
  main.appendChild(cards);
  const foot = el("div", "foot");
  const prev = el("div", "btn", "上一页");
  prev.style.cssText = "flex:0 0 90px;padding:5px 8px";
  const next = el("div", "btn", "下一页");
  next.style.cssText = "flex:0 0 90px;padding:5px 8px";
  const info = el("div", null, "");
  info.style.cssText = "flex:1;text-align:center";
  prev.onclick = () => { if (st.page > 0) { st.page--; renderCards(); } };
  next.onclick = () => { st.page++; renderCards(); };
  foot.appendChild(prev); foot.appendChild(info); foot.appendChild(next);
  main.appendChild(foot);
  container.appendChild(main);
  panel.cards = cards; panel.pageInfo = info; panel.prev = prev; panel.next = next;
  renderCards();
}

function rebuildTpl() {
  const box = panel.left;
  box.innerHTML = "";
  buildTplTab(box);
}

/* ---------- 面板骨架 ---------- */
function openPanel(node) {
  closePanel();
  st.node = node;
  st.favTags = lsGet(FAV_TAG_KEY, []);
  st.favTpl = lsGet(FAV_TPL_KEY, []);
  st.recent = lsGet(RECENT_KEY, []);
  st.zh = lsGet(ZH_KEY, true);
  const cur = node?.widgets?.find((x) => x.name === "template_override")?.value || "";
  st.selected = String(cur).split(",").map((s) => s.trim()).filter(Boolean);

  const root = el("div", "pf-mask");
  const win = el("div", "pf-win");
  root.appendChild(win);

  const head = el("div", "head");
  const logo = el("div", "logo");
  logo.innerHTML = "⚙ Prompt Forge <small>提示词工作台 · v6 中文界面</small>";
  head.appendChild(logo);

  const tabs = el("div", "tabs");
  const tFree = el("div", "tab on", "🎛 自由选词");
  const tTpl = el("div", "tab", "🗂 模板卡片");
  tFree.onclick = () => switchTab("free");
  tTpl.onclick = () => switchTab("tpl");
  tabs.appendChild(tFree); tabs.appendChild(tTpl);
  head.appendChild(tabs);

  head.appendChild(el("div", "grow"));

  // 模板页用的类型筛选（自由选词页不影响）
  const kindSel = el("select", "sel");
  [["all", "全部类型"], ["normal", "普通"], ["monster", "异种"]].forEach(([v, t]) => {
    const o = el("option", null, t);
    o.value = v;
    kindSel.appendChild(o);
  });
  kindSel.onchange = () => { st.kind = kindSel.value; st.page = 0; renderCards(); };
  kindSel.style.display = "none";
  head.appendChild(kindSel);

  const search = el("input", "search");
  search.placeholder = "搜索词条 / 场景，如 bikini、bedroom";
  search.oninput = () => {
    st.q = search.value;
    if (st.tab === "free") renderFreeList(); else renderCards();
  };
  head.appendChild(search);

  const x = el("div", "x", "✕");
  x.onclick = closePanel;
  head.appendChild(x);
  win.appendChild(head);

  const body = el("div", "body");
  win.appendChild(body);
  const left = el("div");
  left.style.cssText = "flex:1;display:flex;min-width:0;min-height:0";
  body.appendChild(left);

  const foot = el("div", "foot");
  panel = { root, win, body, left, out: null, picked: null, cnt: null, sections: [], foot };

  const right = el("div", "right");
  const rh = el("div", "r-h");
  rh.appendChild(el("b", null, "已选词条"));
  rh.appendChild(el("span", null, "按点击顺序"));
  const cnt = el("span", "cnt", "0 / 60");
  rh.appendChild(cnt);
  right.appendChild(rh);
  const sync = el("div", "sync");
  sync.innerHTML = '<i></i>勾选即写回节点，取消勾选会一起删掉';
  right.appendChild(sync);
  const picked = el("div", "picked");
  right.appendChild(picked);
  const outwrap = el("div", "outwrap");
  const out = el("textarea", "out");
  out.placeholder = "这里是从节点读到的 / 手写的提示词";
  out.oninput = () => {
    st.selected = out.value.split(",").map((s) => s.trim()).filter(Boolean);
    const node = st.node;
    if (node) {
      const w = node.widgets?.find((xx) => xx.name === "template_override");
      if (w) { w.value = out.value; if (w.inputEl) w.inputEl.value = out.value; node.setDirtyCanvas(true, true); }
    }
    renderPicked();
  };
  outwrap.appendChild(out);
  const row = el("div");
  row.style.cssText = "display:flex;gap:8px";
  const rnd = el("div", "btn", "🎲 随机一份");
  rnd.onclick = () => {
    pfFetch("/prompt_forge/roll?level=any")
      .then((r) => r.json())
      .then((j) => {
        st.selected = (j.positive || "").split(",").map((s) => s.trim()).filter(Boolean);
        syncNode(); renderFreeList();
        toast("已随机一份并写入节点");
      })
      .catch(() => toast("随机失败", false));
  };
  const clr = el("div", "btn", "🧹 清空");
  clr.onclick = () => { st.selected = []; syncNode(); renderFreeList(); };
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
  panel.out = out; panel.picked = picked; panel.cnt = cnt;
  renderPicked();

  document.body.appendChild(root);
  root.addEventListener("mousedown", (e) => { if (e.target === root) closePanel(); });

  Promise.all([loadLib(), loadTpl(), loadSceneMeta()]).then(() => {
    switchTab("free");
  });

  function switchTab(kind) {
    st.tab = kind;
    tFree.classList.toggle("on", kind === "free");
    tTpl.classList.toggle("on", kind === "tpl");
    kindSel.style.display = kind === "tpl" ? "" : "none";
    left.innerHTML = "";
    st.page = 0;
    if (kind === "free") {
      if (!lib) left.appendChild(el("div", "empty", "词库加载中…"));
      else buildFreeTab(left);
    } else {
      if (!tpl) left.appendChild(el("div", "empty", "模板加载中…"));
      else buildTplTab(left);
    }
  }
}

/* ---------- CSS ---------- */
const CSS = `
.pf-mask{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:99999;display:flex;align-items:center;justify-content:center}
.pf-win{width:min(1360px,95vw);height:min(820px,90vh);background:#1b1c21;border:1px solid #2e3037;border-radius:14px;
  display:flex;flex-direction:column;overflow:hidden;color:#e3e6ec;box-shadow:0 24px 80px rgba(0,0,0,.6);
  font:13px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
.pf-win .head{display:flex;align-items:center;gap:12px;padding:0 16px;height:58px;border-bottom:1px solid #2e3037;flex:0 0 auto}
.pf-win .logo{font-weight:700;color:#e6b45c;white-space:nowrap}
.pf-win .logo small{color:#666c77;font-weight:400;margin-left:6px}
.pf-win .tabs{display:flex;gap:6px;margin-left:8px}
.pf-win .tab{padding:7px 15px;border-radius:9px;background:#22242a;color:#8d939e;cursor:pointer;border:1px solid transparent}
.pf-win .tab.on{background:linear-gradient(180deg,#2b2e36,#24262c);color:#fff;border-color:#e6b45c;box-shadow:inset 0 -2px 0 #e6b45c}
.pf-win .grow{flex:1}
.pf-win .range{display:flex;align-items:center;gap:7px;color:#8d939e;font-size:12px}
.pf-win .sel{padding:6px 9px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec}
.pf-win .search{width:240px;padding:6px 11px;border-radius:8px;background:#23252b;border:1px solid #383b43;color:#e3e6ec;outline:none}
.pf-win .search::placeholder{color:#666c77}
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
.pf-win .fchip{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:99px;background:#24262c;border:1px solid #2f323a;color:#cfd5df;cursor:pointer;font-size:12.5px;white-space:nowrap}
.pf-win .fchip:hover{border-color:#4a4e59}
.pf-win .fchip.on{border-color:#3f8f6f;background:rgba(63,143,111,.12);color:#d6f2e5;box-shadow:0 0 0 1px rgba(63,143,111,.35) inset}
.pf-win .fchip .ck{display:none;width:13px;height:13px;border-radius:3px;background:#3f8f6f;place-items:center;font-size:10px;color:#fff}
.pf-win .fchip.on .ck{display:grid}
.pf-win .fchip .zh{color:#666c77;font-size:11.5px}
.pf-win .fchip.on .zh{color:#9ec9b4}
.pf-win .fchip .star{font-size:11px;color:#666c77}
.pf-win .fchip.fav .star{color:#e6b45c}
.pf-win .acc{flex:1;overflow:auto;padding:8px 14px;min-width:0}
.pf-win .sec{border-bottom:1px solid #26282e}
.pf-win .sec-h{display:flex;align-items:center;gap:9px;padding:11px 8px;cursor:pointer;border-radius:8px}
.pf-win .sec-h:hover{background:#212329}
.pf-win .caret{color:#666c77;width:12px;font-size:11px;transition:transform .12s}
.pf-win .sec.open .caret{transform:rotate(90deg)}
.pf-win .sec-h .lb{font-weight:600;font-size:13.5px}
.pf-win .sec-h .n{color:#666c77;font-size:12px}
.pf-win .sec-h .desc{color:#8d939e;font-size:11.5px}
.pf-win .sec-h .cur{margin-left:auto;color:#e6b45c;font-size:11px;border:1px solid #5a4728;background:rgba(230,180,92,.1);padding:2px 8px;border-radius:99px}
.pf-win .sec-body{display:none;padding:4px 8px 14px 28px;flex-wrap:wrap;gap:8px}
.pf-win .sec.open .sec-body{display:flex}
.pf-win .fav-sec .lb{color:#e6b45c}
.pf-win .chip{display:flex;align-items:center;gap:7px;padding:6px 10px;border-radius:8px;background:#262931;border:1px solid #31343d;color:#c9ced8;cursor:pointer;font-size:12px}
.pf-win .chip:hover{border-color:#4a4e59}
.pf-win .chip.on{background:rgba(63,143,111,.16);border-color:#3f8f6f;color:#d6f2e5}
.pf-win .chip .ck{width:13px;height:13px;border-radius:3px;border:1px solid #4a4e59;display:grid;place-items:center;font-size:10px;color:transparent}
.pf-win .chip.on .ck{background:#3f8f6f;border-color:#3f8f6f;color:#fff}
.pf-win .chip .lv-d{font-size:10px;color:#666c77}
.pf-win .chip .star{font-size:11px;color:#666c77}
.pf-win .chip.starred .star{color:#e6b45c}
.pf-win .empty{color:#666c77;padding:6px 2px;font-size:12px}
.pf-win .right{width:344px;border-left:1px solid #2e3037;display:flex;flex-direction:column;min-height:0;background:#191a1f}
.pf-win .r-h{padding:10px 14px;border-bottom:1px solid #2e3037;display:flex;align-items:center;gap:8px;color:#8d939e;font-size:12px}
.pf-win .r-h b{color:#e3e6ec;font-size:13px}
.pf-win .r-h .cnt{margin-left:auto;color:#666c77;font-size:11px}
.pf-win .sync{display:flex;align-items:center;gap:6px;padding:7px 14px;color:#7fd0aa;font-size:11.5px;border-bottom:1px solid #2e3037;background:rgba(63,143,111,.08)}
.pf-win .sync i{width:7px;height:7px;border-radius:50%;background:#3f8f6f}
.pf-win .picked{max-height:190px;overflow:auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}
.pf-win .pk{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:7px;background:#262931;border:1px solid #343842;font-size:11.5px;color:#cfd5df}
.pf-win .pk i{font-style:normal;color:#666c77;cursor:pointer}
.pf-win .outwrap{flex:1;padding:8px 14px 0;display:flex;flex-direction:column;gap:8px;min-height:0}
.pf-win .out{flex:1;background:#202127;border:1px solid #383b43;border-radius:10px;padding:10px 12px;
  font:12px/1.7 Consolas,monospace;color:#b9c1cd;resize:none;outline:none}
.pf-win .btns{display:flex;gap:8px;padding:10px 14px 14px}
.pf-win .btn{flex:1;text-align:center;padding:8px 10px;border-radius:9px;background:#262931;border:1px solid #3a3e48;color:#dde2ea;cursor:pointer;font-size:12.5px}
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
.pf-win .main{flex:1;display:flex;flex-direction:column;min-width:0}
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
.pf-win .tag-fold{padding:0 11px 9px;color:#8d939e;font-size:11.5px;cursor:pointer}
.pf-win .tag-fold:hover{color:#dde2ea}
.pf-win .tag-fold.on{color:#e6b45c}
.pf-win .card-tags .tg{font:11px/1.5 Consolas,monospace;padding:2px 6px;border-radius:6px;background:#262931;border:1px solid #31343d;color:#aeb6c2}
.pf-win .fold{padding:0 11px 8px}
.pf-win .fold-t{color:#8d939e;font-size:11.5px;cursor:pointer;padding:3px 0}
.pf-win .fold-b{margin-top:5px;font:11.5px/1.6 Consolas,monospace;color:#9aa3b0;max-height:74px;overflow:hidden;border-top:1px dashed #2e3037;padding-top:6px;white-space:normal;word-break:break-word}
.pf-win .card-btns{display:flex;gap:7px;padding:9px 11px;margin-top:auto;border-top:1px solid #2e3037}
.pf-win .card-btns .btn{padding:6px 8px;font-size:11.5px}
.pf-win .foot{display:flex;align-items:center;gap:12px;padding:8px 15px;border-top:1px solid #2e3037;color:#666c77;font-size:11px;flex:0 0 auto}
`;
if (!document.getElementById("pf-style")) {
  const s = document.createElement("style");
  s.id = "pf-style";
  s.textContent = CSS;
  document.head.appendChild(s);
}


export { openPanel };


