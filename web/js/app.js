import { Model, ASPECTS } from "./model.js";
import { Social, FRIENDS, avatar, esc, ago } from "./social.js";

const SEED_TITLES = [
  ["Champagne Poetry", "Drake"], ["8am in Charlotte", "Drake"], ["Stories About My Brother", "Drake"],
  ["Make Them Pay", "Drake"], ["Love All", "Drake"], ["I Got A Story To Tell", "Notorious"],
  ["September", "Earth, Wind"], ["Ain't No Mountain High Enough", "Marvin Gaye"],
];
const ASPECT_ORDER = ["drums", "bass", "melody", "vocals", "sample", "backing", "tempo", "vibe", "producer"];
const RATE_TARGET = 20;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ICON = {
  play: '<svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6.5" y="5" width="4" height="14" rx="1"/><rect x="13.5" y="5" width="4" height="14" rx="1"/></svg>',
  chev: '<svg class="chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  up: '<svg viewBox="0 0 24 24"><path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="M17 13V4h3v9zM17 13l-4 8a2 2 0 0 1-2-2v-4H5.5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.7 4H17"/></svg>',
  heart: '<svg viewBox="0 0 24 24"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>',
  bookmark: '<svg viewBox="0 0 24 24"><path d="M7 3h10a1 1 0 0 1 1 1v17l-6-4-6 4V4a1 1 0 0 1 1-1z"/></svg>',
};

// ---------- persistent per-browser state ----------
const store = {
  key: "facets.v1",
  load() {
    let data = {};
    try { data = JSON.parse(localStorage.getItem(this.key)) || {}; } catch { /* private mode: start fresh */ }
    Object.assign(this, { current: null, liked: [], aspects: {}, text: "", feedback: {}, reactions: {}, comments: {},
                          tests: [], introSeen: false }, data);
    return this;
  },
  save() {
    const { key, load, save, ...data } = this;
    try { localStorage.setItem(this.key, JSON.stringify(data)); } catch { /* storage unavailable */ }
  },
}.load();

let model, social, seeds = [], test = null;
const audio = $("#audio");
const ui = { tab: "all", openFriends: new Set() };

// ---------- helpers ----------
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 1800);
}
const art = (t, size = 300) => (t.art || "").replace("300x300bb", `${size}x${size}bb`);
const firstArtist = (a) => a.split(" & ")[0].split(",")[0];
function jsonp(url) {
  return new Promise((resolve, reject) => {
    const cb = `dz${Math.random().toString(36).slice(2)}`, s = document.createElement("script");
    window[cb] = (data) => { resolve(data); delete window[cb]; s.remove(); };
    s.src = `${url}${url.includes("?") ? "&" : "?"}output=jsonp&callback=${cb}`;
    s.onerror = reject;
    document.head.append(s);
  });
}
function liked() { return Object.entries(store.aspects).filter(([, v]) => v === "like").map(([a]) => a); }
function disliked() { return Object.entries(store.aspects).filter(([, v]) => v === "dislike").map(([a]) => a); }
function seedId() { return store.current ?? seeds[0]; }
function recs(opts = {}) {
  return model.recommend({ seed: seedId(), liked: liked(), disliked: disliked(), text: store.text,
                           feedback: store.feedback, limit: 12, ...opts });
}

// ---------- player ----------
async function play(id, { open = false } = {}) {
  const t = model.track(id);
  if (!t) return;
  const changed = store.current !== id;
  store.current = id;
  store.save();
  let src = t.p;
  if (t.src === "dz") {  // Deezer preview links expire: fetch a fresh one by ID
    try { src = (await jsonp(`https://api.deezer.com/track/${-t.id}`)).preview || src; } catch { /* keep cached */ }
  }
  if (changed || audio.src !== src) audio.src = src;
  audio.play().catch(() => toast("Tap play to start audio"));
  renderPlayer();
  if (changed) renderView();
  if (open) openSheet();
}
function togglePlay() {
  if (!audio.src) return play(seedId());
  audio.paused ? audio.play() : audio.pause();
}
audio.addEventListener("play", renderPlayIcons);
audio.addEventListener("pause", renderPlayIcons);
audio.addEventListener("ended", () => { renderPlayIcons(); nextRec(); });
audio.addEventListener("timeupdate", () => {
  const p = audio.duration ? audio.currentTime / audio.duration : 0;
  $("#mini-progress").style.transform = `scaleX(${p})`;
  $("#np-progress").style.transform = `scaleX(${p})`;
  const s = Math.floor(audio.currentTime);
  $("#np-time").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
});
function nextRec() {
  const next = recs({ limit: 1 })[0];
  if (next) play(next.id);
}
function renderPlayIcons() {
  const icon = audio.paused ? ICON.play : ICON.pause;
  $("#mini-play").innerHTML = icon;
  $("#np-play").innerHTML = icon;
  $("#mini-play").setAttribute("aria-label", audio.paused ? "Play" : "Pause");
}
function renderPlayer() {
  const t = model.track(seedId());
  if (!t) return;
  $("#mini").hidden = !store.current;
  $("#mini-art").src = art(t, 100);
  $("#mini-title").textContent = t.t;
  $("#mini-artist").textContent = t.a;
  $("#np-art").src = art(t, 600);
  $("#sheet-bg").style.backgroundImage = `url("${art(t, 300)}")`;
  $("#np-title").textContent = t.t;
  $("#np-artist").textContent = t.a;
  $("#np-like").classList.toggle("on", store.liked.includes(t.id));
  $("#np-tags").innerHTML = [t.bpm ? `${Math.round(t.bpm)} bpm` : null, ...(t.tg || [])].filter(Boolean)
    .map(x => `<i>${esc(x)}</i>`).join("");
  const credits = [];
  if (t.pd?.length) credits.push(`<b>Produced by</b> ${esc(t.pd.join(", "))}`);
  if (t.sd?.length) credits.push(`<b>Samples</b> ${esc(t.sd.slice(0, 3).join(" · "))}`);
  if (t.gu) credits.push(`<a href="${esc(t.gu)}" target="_blank" rel="noopener">Credits on Genius</a>`);
  $("#np-credits").innerHTML = credits.join("<br>");
  renderAspectChips($("#np-aspects"));
  $("#np-text").value = store.text;
  renderHeard($("#np-heard"));
  renderPlayIcons();
}

// ---------- aspect controls (shared by sheet and For You) ----------
function renderAspectChips(root) {
  root.innerHTML = ASPECT_ORDER.map(a => {
    const state = store.aspects[a] || "none";
    const mark = state === "like" ? "♥" : state === "dislike" ? "✕" : "+";
    return `<button class="aspect" data-aspect="${a}" data-state="${state}" type="button" aria-pressed="${state !== "none"}">
      <span class="mark">${mark}</span>${esc(ASPECTS[a].label)}</button>`;
  }).join("");
}
function cycleAspect(a) {
  const next = { none: "like", like: "dislike", dislike: "none" }[store.aspects[a] || "none"];
  if (next === "none") delete store.aspects[a]; else store.aspects[a] = next;
  store.save();
  refreshControls();
}
function renderHeard(el) {
  if (!store.text.trim()) { el.innerHTML = ""; return; }
  const p = model.parse(store.text);
  const bits = [
    ...p.liked.map(a => `<b>♥ ${esc(ASPECTS[a].label)}</b>`),
    ...p.disliked.map(a => `✕ ${esc(ASPECTS[a].label)}`),
    ...p.descriptors.map(k => `<b>“${esc(model.descriptors[k].label)}”</b>`),
  ];
  el.innerHTML = bits.length ? `Heard: ${bits.join(" · ")}` : "Didn't catch an aspect. Try drums, sample, vocals, 808s, piano, angelic…";
}
function refreshControls() {
  $$(".aspect-chips").forEach(renderAspectChips);
  $$(".heard").forEach(renderHeard);
  if (ui.tab === "foryou") renderForYouList(); else if (ui.tab === "all") renderMadeForYou();
}
document.addEventListener("click", (e) => {
  const chip = e.target.closest(".aspect");
  if (chip) cycleAspect(chip.dataset.aspect);
});
let typing;
document.addEventListener("input", (e) => {
  if (!e.target.matches("#np-text, #fy-text")) return;
  store.text = e.target.value;
  store.save();
  clearTimeout(typing);
  typing = setTimeout(() => {
    $$("#np-text, #fy-text").forEach(i => { if (i !== e.target) i.value = store.text; });
    refreshControls();
  }, 220);
});

// ---------- shared row markup ----------
function trackRow(t, extra = "") {
  return `<div class="row ${store.current === t.id ? "playing" : ""}" data-id="${t.id}">
    <button class="row-main" data-play="${t.id}" type="button">
      <img src="${esc(art(t, 100))}" alt="" loading="lazy">
      <span class="row-text"><b>${esc(t.t)}</b><span>${esc(t.a)}</span>${extra}</span>
    </button></div>`;
}

// ---------- views ----------
function renderView() {
  if (ui.tab === "all") renderAll();
  else if (ui.tab === "friends") renderFriends();
  else if (ui.tab === "foryou") renderForYou();
  else if (ui.tab === "rate") renderRate();
}
function setTab(tab) {
  ui.tab = tab;
  $$(".chip").forEach(c => c.setAttribute("aria-selected", String(c.dataset.tab === tab)));
  $$(".tabbar button").forEach(b => b.classList.toggle("on", b.dataset.nav === tab));
  $$(".view").forEach(v => { v.hidden = v.dataset.view !== tab; });
  window.scrollTo({ top: 0 });
  renderView();
}

function liveCard() {
  const online = social.state.filter(f => f.online);
  return `<button class="live" data-goto="friends" type="button">
    <span class="live-head"><span class="live-label"><span class="dot"></span>FRIENDS ARE LIVE</span>
    <span class="online"><span class="dot"></span>${online.length} online</span></span>
    <span class="stack">${online.map(f => avatar(f, "", 1)).join("")}<span class="more">+${FRIENDS.length - online.length}</span></span>
  </button>`;
}

function friendBlock(f) {
  const t = model.track(f.track), open = ui.openFriends.has(f.id), mine = social.myReaction(f);
  const reactions = Object.entries(f.reactions).map(([e, n]) =>
    `<button class="react ${mine === e ? "mine" : ""}" data-react="${e}" data-friend="${f.id}" type="button"><span>${e}</span><span class="n">${n}</span></button>`).join("");
  const comments = social.commentsFor(f).map(c => {
    const who = social.person(c.who);
    return `<div class="comment">${avatar(who)}<div><b>${esc(who.name)}</b><time>${ago(c.at)}</time><p>${esc(c.text)}</p></div></div>`;
  }).join("");
  return `<div class="friend ${open ? "open" : ""}" data-friend="${f.id}">
    <button class="friend-row" data-toggle="${f.id}" type="button" aria-expanded="${open}">
      <span class="ring ${f.online ? "" : "away"}">${avatar(f)}</span>
      <span class="friend-text"><b>${esc(f.name)}</b><span class="song">${esc(t.t)}</span>
      <span class="meta">${esc(t.a)}${t.al ? ` · ${esc(t.al)}` : ""}</span></span>
      ${f.online ? ICON.chev : `<span class="ago">${ago(f.lastSeen)}</span>`}
    </button>
    <div class="friend-more"><div><div class="pad">
      <button class="cta ghost" data-play="${t.id}" type="button" style="margin:0 0 12px;padding:9px">Play ${esc(t.t.split(" (")[0])}</button>
      <div class="label">Reactions</div><div class="reacts">${reactions}</div>
      <div class="label" style="margin-top:12px">Comments</div><div class="comments">${comments}</div>
      <form class="compose" data-compose="${f.id}">${avatar(social.person("me"))}
        <input name="c" placeholder="Add a comment…" maxlength="140" autocomplete="off">
        <button class="send" type="submit" aria-label="Send">${ICON.send}</button></form>
    </div></div></div>
  </div>`;
}

function renderAll() {
  const v = $("#view-all");
  const likedTracks = store.liked.map(id => model.track(id)).filter(Boolean);
  v.innerHTML = `
    <div class="tiles">
      <button class="tile" data-goto-section="liked-section" type="button"><span class="tile-icon liked">${ICON.heart}</span><span>Liked Songs</span></button>
      <button class="tile" data-goto-section="seeds-section" type="button"><span class="tile-icon saved">${ICON.bookmark}</span><span>Your Seeds</span></button>
      ${seeds.slice(0, 4).map(id => { const t = model.track(id);
        return `<button class="tile" data-play="${id}" type="button"><img src="${esc(art(t, 100))}" alt=""><span>${esc(t.t)}</span></button>`; }).join("")}
    </div>
    ${liveCard()}
    <h2 class="section">Listening now</h2>
    <div id="all-friends">${social.state.filter(f => f.online).slice(0, 3).map(friendBlock).join("")}</div>
    <h2 class="section">Made for you</h2>
    <p class="sub" id="mfy-sub"></p>
    <div class="cards" id="mfy"></div>
    <h2 class="section" id="seeds-section">Your seeds</h2>
    ${seeds.map(id => trackRow(model.track(id))).join("")}
    <h2 class="section" id="liked-section">Liked Songs</h2>
    ${likedTracks.length ? likedTracks.map(t => trackRow(t)).join("") : '<p class="empty">Tap ♥ in the player to save songs here.</p>'}`;
  renderMadeForYou();
}
function renderMadeForYou() {
  const box = $("#mfy");
  if (!box) return;
  const t = model.track(seedId()), asp = liked();
  $("#mfy-sub").textContent = asp.length || store.text
    ? `The ${asp.map(a => ASPECTS[a].label.toLowerCase().replace(/^the /, "")).join(" + ") || "parts you described"} in ${t.t}`
    : `Sounds like ${t.t}. Open the player to say what hits.`;
  box.innerHTML = recs({ limit: 10 }).map(r => { const x = model.track(r.id);
    return `<button class="card" data-play="${x.id}" type="button"><img src="${esc(art(x))}" alt="" loading="lazy"><b>${esc(x.t)}</b><span>${esc(firstArtist(x.a))}</span></button>`; }).join("");
}

function renderFriends() {
  const online = social.state.filter(f => f.online), recent = social.state.filter(f => !f.online);
  $("#view-friends").innerHTML = `${liveCard()}
    <h2 class="section">Listening now</h2><div>${online.map(friendBlock).join("")}</div>
    <h2 class="section">Recently</h2><div class="recent">${recent.map(friendBlock).join("")}</div>`;
}

function renderForYou() {
  const t = model.track(seedId());
  $("#view-foryou").innerHTML = `
    <div class="foryou-head">
      <div class="foryou-seed"><img src="${esc(art(t, 100))}" alt=""><div><span>Because of</span><b>${esc(t.t)}</b><span>${esc(t.a)}</span></div></div>
      <div class="aspect-chips"></div>
      <label class="say"><input id="fy-text" type="text" value="${esc(store.text)}" placeholder="Or say it: the angelic sample and the drums…" autocomplete="off"></label>
      <p class="heard"></p>
    </div>
    <h2 class="section">For You</h2>
    <div id="fy-list"></div>
    <button class="cta ghost" data-goto="rate" type="button" style="margin-top:18px">Rate these blind vs plain similarity</button>`;
  renderAspectChips($(".aspect-chips", $("#view-foryou")));
  renderHeard($(".heard", $("#view-foryou")));
  renderForYouList();
}
function renderForYouList() {
  const list = $("#fy-list");
  if (!list) return;
  const results = recs();
  list.innerHTML = results.map(r => {
    const t = model.track(r.id), vote = store.feedback[t.id];
    const why = [...r.why.map(w => `<i>${esc(w)}</i>`), ...(r.why.length ? [] : (t.tg || []).slice(0, 2).map(w => `<i class="tag">${esc(w)}</i>`))];
    return `<div class="row ${store.current === t.id ? "playing" : ""}" data-id="${t.id}">
      <button class="row-main" data-play="${t.id}" type="button"><img src="${esc(art(t, 100))}" alt="" loading="lazy">
      <span class="row-text"><b>${esc(t.t)}</b><span>${esc(t.a)}</span><span class="why">${why.join("")}</span></span></button>
      <button class="vote up ${vote === true ? "on" : ""}" data-vote="${t.id}" data-v="1" type="button" aria-label="More like this">${ICON.up}</button>
      <button class="vote down ${vote === false ? "on" : ""}" data-vote="${t.id}" data-v="0" type="button" aria-label="Less like this">${ICON.down}</button>
    </div>`;
  }).join("") || '<p class="empty">Nothing left. Clear some votes.</p>';
}

// ---------- blind A/B rating ----------
function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
function startTest() {
  const ask = { seed: seedId(), liked: liked(), disliked: disliked(), text: store.text };
  if (!ask.liked.length && !ask.disliked.length && !ask.text.trim()) {
    toast("First pick what hits (or type it) for this song");
    return;
  }
  const a = model.recommend({ ...ask, limit: 5, feedback: {} }).map(r => r.id);
  const p = model.recommend({ ...ask, limit: 5, feedback: {}, mode: "plain" }).map(r => r.id);
  const ids = [...new Set([...a, ...p])];
  test = { ...ask, at: Date.now(), items: shuffle(ids).map(id => ({ id, methods: [a.includes(id) && "aspect", p.includes(id) && "plain"].filter(Boolean) })), ratings: {} };
  renderRate();
}
function summary(tests) {
  const sums = { aspect: [0, 0], plain: [0, 0] };
  for (const t of tests) for (const item of t.items) {
    const r = t.ratings[item.id];
    if (!r) continue;
    for (const m of item.methods) { sums[m][0] += r; sums[m][1]++; }
  }
  return Object.fromEntries(Object.entries(sums).map(([m, [s, n]]) => [m, { mean: n ? s / n : 0, n }]));
}
function ratedCount() { return store.tests.reduce((n, t) => n + Object.keys(t.ratings).length, 0) + (test ? Object.keys(test.ratings).length : 0); }
function renderRate() {
  const v = $("#view-rate"), t = model.track(seedId());
  const ask = [...liked().map(a => ASPECTS[a].label.toLowerCase()), ...disliked().map(a => `not ${ASPECTS[a].label.toLowerCase()}`),
               ...(store.text ? [`“${store.text}”`] : [])].join(", ");
  let body = "";
  if (!test) {
    body = `<button class="cta" id="start-test" type="button">Start a blind round for ${esc(t.t)}</button>
      <p class="sub" style="margin-top:10px">Asking for: ${esc(ask || "nothing yet. Pick aspects in the player or For You first.")}</p>`;
  } else {
    const done = test.items.every(i => test.ratings[i.id]);
    body = `<p class="sub">How well does each song match <b>${esc(ask || "your request")}</b> in ${esc(model.track(test.seed).t)}? 1 = not at all, 5 = exactly.</p>
      ${test.items.map(item => { const x = model.track(item.id), r = test.ratings[item.id];
        return `<div class="row ${store.current === x.id ? "playing" : ""}"><button class="row-main" data-play="${x.id}" type="button"><img src="${esc(art(x, 100))}" alt="">
          <span class="row-text"><b>${esc(x.t)}</b><span>${esc(x.a)}</span>
          <span class="stars">${[1, 2, 3, 4, 5].map(n => `<span class="star ${r === n ? "on" : ""}" data-rate="${x.id}" data-n="${n}" role="button" tabindex="0">${n}</span>`).join("")}</span></span></button></div>`; }).join("")}
      <button class="cta" id="finish-test" type="button" ${done ? "" : "disabled"}>${done ? "Reveal which was which" : "Rate every song to reveal"}</button>`;
  }
  const s = summary(store.tests);
  const results = store.tests.length ? `<h2 class="section">Results so far</h2>
    <div class="result-bars">
      <div class="result-bar"><span>Aspect model</span><span class="bar"><i style="width:${s.aspect.mean / 5 * 100}%"></i></span><b>${s.aspect.mean.toFixed(2)}</b></div>
      <div class="result-bar plain"><span>Plain similarity</span><span class="bar"><i style="width:${s.plain.mean / 5 * 100}%"></i></span><b>${s.plain.mean.toFixed(2)}</b></div>
    </div>
    <p class="sub" style="margin-top:10px">Mean rating out of 5 across ${s.aspect.n} aspect-model and ${s.plain.n} plain-similarity songs (songs both picked count for both).</p>
    <button class="cta ghost" id="export-ratings" type="button">Download ratings (JSON)</button>` : "";
  v.innerHTML = `<div class="rate-intro"><b>Blind test.</b> Each round mixes the top 5 from the aspect model with the top 5 from plain
    “sounds like the whole song” similarity, shuffled and unlabeled. Rate how well each matches what you asked for.
    <br><span class="progress-pill">${ratedCount()} / ${RATE_TARGET} rated</span></div>
    <h2 class="section">${test ? "Rate this round" : "New round"}</h2>${body}${results}`;
}
function finishTest() {
  const before = summary([test]);
  store.tests.push(test);
  store.save();
  toast(`This round: aspect ${before.aspect.mean.toFixed(1)} vs plain ${before.plain.mean.toFixed(1)}`);
  test = null;
  renderRate();
}
function exportRatings() {
  const rows = store.tests.map(t => ({ seed: model.track(t.seed)?.t, liked: t.liked, disliked: t.disliked, text: t.text,
    items: t.items.map(i => ({ id: i.id, title: model.track(i.id)?.t, artist: model.track(i.id)?.a, methods: i.methods, rating: t.ratings[i.id] })) }));
  const blob = new Blob([JSON.stringify({ exported: new Date().toISOString(), summary: summary(store.tests), rounds: rows }, null, 2)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "facets-ratings.json" });
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- search ----------
function openSearch() {
  $("#search").classList.add("open");
  $("#search").setAttribute("aria-hidden", "false");
  $("#search-input").focus();
  renderSearch();
}
function closeSearch() { $("#search").classList.remove("open"); $("#search").setAttribute("aria-hidden", "true"); }
function renderSearch() {
  const q = $("#search-input").value.trim().toLowerCase();
  const hits = q ? model.tracks.filter(t => `${t.t} ${t.a}`.toLowerCase().includes(q)).slice(0, 60) : seeds.map(id => model.track(id));
  $("#search-results").innerHTML = (q ? "" : '<h2 class="section">Your seeds</h2>') +
    (hits.map(t => trackRow(t)).join("") || '<p class="empty">No songs found in the catalog.</p>');
}
$("#search-input").addEventListener("input", renderSearch);
$("#search-close").addEventListener("click", closeSearch);
$("#open-search").addEventListener("click", openSearch);

// ---------- sheet ----------
function openSheet() { $("#sheet").classList.add("open"); $("#sheet").setAttribute("aria-hidden", "false"); }
function closeSheet() { $("#sheet").classList.remove("open"); $("#sheet").setAttribute("aria-hidden", "true"); }
$("#mini-open").addEventListener("click", openSheet);
$("#sheet-close").addEventListener("click", closeSheet);
$("#mini-play").addEventListener("click", togglePlay);
$("#np-play").addEventListener("click", togglePlay);
$("#np-next").addEventListener("click", nextRec);
$("#np-foryou").addEventListener("click", () => { closeSheet(); setTab("foryou"); });
$("#np-like").addEventListener("click", () => {
  const id = seedId(), i = store.liked.indexOf(id);
  if (i >= 0) store.liked.splice(i, 1); else store.liked.unshift(id);
  store.save();
  $("#np-like").classList.toggle("on", i < 0);
  toast(i < 0 ? "Added to Liked Songs" : "Removed from Liked Songs");
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeSheet(); closeSearch(); }
});

// ---------- delegated clicks ----------
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-play],[data-goto],[data-goto-section],[data-toggle],[data-react],[data-vote],[data-rate],#start-test,#finish-test,#export-ratings,[data-tab],[data-nav]");
  if (!el) return;
  if (el.dataset.rate) {
    test.ratings[el.dataset.rate] = +el.dataset.n;
    renderRate();
    return;
  }
  if (el.dataset.play) { closeSearch(); play(+el.dataset.play); return; }
  if (el.dataset.goto) { setTab(el.dataset.goto); return; }
  if (el.dataset.gotoSection) { document.getElementById(el.dataset.gotoSection)?.scrollIntoView({ behavior: "smooth" }); return; }
  if (el.dataset.tab) { setTab(el.dataset.tab); return; }
  if (el.dataset.nav) { el.dataset.nav === "search" ? openSearch() : setTab(el.dataset.nav); return; }
  if (el.dataset.toggle) {
    const id = el.dataset.toggle;
    if (!social.friend(id).online) return;
    ui.openFriends.has(id) ? ui.openFriends.delete(id) : ui.openFriends.add(id);
    $$(`.friend[data-friend="${id}"]`).forEach(b => { b.classList.toggle("open"); b.querySelector(".friend-row").setAttribute("aria-expanded", String(ui.openFriends.has(id))); });
    return;
  }
  if (el.dataset.react) { social.react(el.dataset.friend, el.dataset.react); return; }
  if (el.dataset.vote) {
    const id = +el.dataset.vote, v = el.dataset.v === "1";
    if (store.feedback[id] === v) delete store.feedback[id]; else store.feedback[id] = v;
    store.save();
    toast(store.feedback[id] === undefined ? "Vote cleared" : v ? "More like this" : "Less like this");
    renderForYouList();
    return;
  }
  if (el.id === "start-test") startTest();
  if (el.id === "finish-test") finishTest();
  if (el.id === "export-ratings") exportRatings();
});
document.addEventListener("submit", (e) => {
  const form = e.target.closest("[data-compose]");
  if (!form) return;
  e.preventDefault();
  const text = form.c.value.trim();
  if (!text) return;
  form.c.value = "";
  social.comment(form.dataset.compose, text);
});

// Live social updates patch just the affected friend so open panels and inputs survive.
function patchFriend(id, kind) {
  const f = social.friend(id);
  $$(`.friend[data-friend="${id}"]`).forEach(node => {
    const input = node.querySelector("input"), draft = input?.value, focused = document.activeElement === input;
    const fresh = document.createElement("div");
    fresh.innerHTML = friendBlock(f);
    const next = fresh.firstElementChild;
    node.replaceWith(next);
    const newInput = next.querySelector("input");
    if (newInput && draft) newInput.value = draft;
    if (focused) newInput?.focus();
    if (kind.startsWith("bump:")) {
      const chip = next.querySelector(`[data-react="${kind.slice(5)}"]`);
      chip?.classList.add("bump");
    }
    if (kind === "comment") next.querySelector(".comment:last-child")?.classList.add("new");
  });
  if (kind === "track") $$(".live").forEach(l => { l.outerHTML = liveCard(); });
}

// ---------- intro ----------
function runIntro(force = false) {
  const intro = $("#intro");
  if (store.introSeen && !force) { intro.classList.add("done"); return; }
  intro.classList.remove("done");
  $("#intro-avatars").innerHTML = FRIENDS.slice(0, 3).map(f => avatar(f, "", 1)).join("");
  const steps = $$("[data-step]", intro), times = [300, 2100, 3600, 5000, 6900], end = 8900;
  const timers = steps.map((el, k) => setTimeout(() => {
    steps.forEach(s => s.classList.remove("on"));
    el.classList.add("on");
  }, times[k]));
  const finish = () => {
    timers.forEach(clearTimeout);
    clearTimeout(done);
    intro.classList.add("done");
    store.introSeen = true;
    store.save();
  };
  const done = setTimeout(finish, end);
  $("#intro-skip").onclick = finish;
  intro.onclick = (e) => { if (e.target === intro) finish(); };
}
$("#me").addEventListener("click", () => runIntro(true));

// ---------- boot ----------
(async function boot() {
  runIntro();
  model = await Model.load("data");
  seeds = SEED_TITLES.map(([title, artist]) => model.tracks.find(t => t.t.toLowerCase().startsWith(title.toLowerCase())
    && t.a.toLowerCase().includes(artist.toLowerCase()))?.id).filter(Boolean);
  if (!seeds.length) seeds = model.tracks.slice(0, 8).map(t => t.id);
  if (store.current && !model.track(store.current)) store.current = null;
  // Friends listen to songs near your seeds, so the feed feels like your circle.
  const pool = [...new Set(seeds.flatMap(s => model.recommend({ seed: s, limit: 12, diversity: false }).map(r => r.id)))];
  social = new Social(model, pool, store);
  social.addEventListener("change", (e) => patchFriend(e.detail.id, e.detail.kind));
  social.start();
  renderPlayer();
  $("#mini").hidden = !store.current;
  setTab("all");
  window.facets = { model, store, social };  // handy for debugging in the console
})();
