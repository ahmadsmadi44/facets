import { Model, ASPECTS } from "./model.js";

const SEED_TITLES = [
  ["Champagne Poetry", "Drake"], ["8am in Charlotte", "Drake"], ["Stories About My Brother", "Drake"],
  ["Make Them Pay", "Drake"], ["Love All", "Drake"], ["I Got A Story To Tell", "Notorious"],
  ["September", "Earth, Wind"], ["Ain't No Mountain High Enough", "Marvin Gaye"],
];
const ASPECT_ORDER = ["drums", "bass", "melody", "vocals", "sample", "backing", "tempo", "vibe", "producer"];
const RATE_TARGET = 20;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICON = {
  play: '<svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6.5" y="5" width="4" height="14" rx="1"/><rect x="13.5" y="5" width="4" height="14" rx="1"/></svg>',
  up: '<svg viewBox="0 0 24 24"><path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="M17 13V4h3v9zM17 13l-4 8a2 2 0 0 1-2-2v-4H5.5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.7 4H17"/></svg>',
  heart: '<svg viewBox="0 0 24 24"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>',
  sliders: '<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
};

// ---------- persistent per-browser state ----------
// songs: { [trackId]: { liked: [aspect], disliked: [aspect], text, at } }, what you said about each song.
const store = {
  key: "facets.v2",
  load() {
    let data = {}, old = null;
    try {
      data = JSON.parse(localStorage.getItem(this.key)) || {};
      if (!Object.keys(data).length) old = JSON.parse(localStorage.getItem("facets.v1"));
    } catch { /* private mode: start fresh */ }
    Object.assign(this, { current: null, liked: [], songs: {}, feedback: {}, tests: [], introSeen: false }, data);
    if (old) {  // v1 kept one global set of aspects; give it to the song it was set on
      Object.assign(this, { current: old.current ?? null, liked: old.liked || [], feedback: old.feedback || {}, tests: old.tests || [] });
      const asp = Object.entries(old.aspects || {});
      if (old.current != null && (asp.length || old.text)) {
        this.songs[old.current] = { liked: asp.filter(([, v]) => v === "like").map(([a]) => a),
          disliked: asp.filter(([, v]) => v === "dislike").map(([a]) => a), text: old.text || "", at: Date.now() };
      }
    }
    return this;
  },
  save() {
    const { key, load, save, ...data } = this;
    try { localStorage.setItem(this.key, JSON.stringify(data)); } catch { /* storage unavailable */ }
  },
}.load();

let model, seeds = [], test = null;
const audio = $("#audio");
const ui = { tab: "all" };
const trail = { back: [], fwd: [] };  // this visit's playback history, for the back and next buttons

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
const short = (title) => title.split(" (")[0].split(" [")[0];
function jsonp(url) {
  return new Promise((resolve, reject) => {
    const cb = `dz${Math.random().toString(36).slice(2)}`, s = document.createElement("script");
    window[cb] = (data) => { resolve(data); delete window[cb]; s.remove(); };
    s.src = `${url}${url.includes("?") ? "&" : "?"}output=jsonp&callback=${cb}`;
    s.onerror = reject;
    document.head.append(s);
  });
}
function seedId() { return store.current ?? seeds[0]; }

// What you said about one song. Empty when you haven't said anything about it.
function picks(id = seedId()) { return store.songs[id] || { liked: [], disliked: [], text: "" }; }
const said = (p) => p.liked.length || p.disliked.length || p.text.trim();
function setPicks(id, p) {
  if (said(p)) store.songs[id] = { liked: p.liked, disliked: p.disliked, text: p.text, at: Date.now() };
  else delete store.songs[id];
  store.save();
}
// Your taste: every song you described, plus hearted songs you didn't describe (as "the whole song").
function taste() {
  const described = Object.entries(store.songs).sort((a, b) => b[1].at - a[1].at)
    .map(([id, p]) => ({ seed: +id, liked: p.liked, disliked: p.disliked, text: p.text, weight: 1 }));
  const hearted = store.liked.filter(id => !store.songs[id])
    .map(id => ({ seed: id, liked: [], disliked: [], text: "", weight: 0.5 }));
  return [...described, ...hearted].filter(e => model.track(e.seed))
    .map(e => ({ ...e, loved: store.liked.includes(e.seed) }));
}
// The songs in your taste that vote for something; ones with only ✕ picks just steer away.
const liking = () => taste().filter(e => model.positive(e));
// Every song you've rated in any way. Recommendations are for discovering, so these never come back.
function rated() {
  return [...new Set([...Object.keys(store.songs).map(Number), ...store.liked, ...Object.keys(store.feedback).map(Number),
                      ...store.tests.flatMap(t => Object.keys(t.ratings).map(Number))])];
}
function songRecs(id = seedId(), opts = {}) {
  return model.recommend({ seed: id, ...picks(id), feedback: store.feedback, exclude: rated(), limit: 12, ...opts });
}
function tasteRecs(opts = {}) {
  return model.profile(taste(), { feedback: store.feedback, exclude: rated(), limit: 12, ...opts });
}
function describe(p, { max = 4 } = {}) {
  const parts = [...p.liked.map(a => ASPECTS[a].label.toLowerCase().replace(/^the /, "")),
                 ...p.disliked.map(a => `not ${ASPECTS[a].label.toLowerCase().replace(/^the /, "")}`)];
  if (p.text?.trim()) parts.push(`“${p.text.trim()}”`);
  return parts.slice(0, max).join(", ");
}
// "the sample in Champagne Poetry", or "Champagne Poetry" for a hearted song.
function becauseLabel(id) {
  const p = picks(id), t = model.track(id);
  const liked = p.liked.map(a => ASPECTS[a].label.toLowerCase().replace(/^the /, ""));
  const what = liked.length ? `the ${liked.slice(0, 2).join(" + ")}` : p.text.trim() ? `“${p.text.trim()}”` : "";
  return what ? `${what} in ${short(t.t)}` : short(t.t);
}

// ---------- player ----------
async function play(id, { via = "pick", open = false } = {}) {
  const t = model.track(id);
  if (!t) return;
  const changed = store.current !== id;
  if (changed && store.current != null) {
    if (via === "back") trail.fwd.push(store.current);
    else {
      trail.back.push(store.current);
      if (via !== "fwd") trail.fwd = [];
    }
  }
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
audio.addEventListener("ended", () => { renderPlayIcons(); next(); });
audio.addEventListener("timeupdate", () => {
  const p = audio.duration ? audio.currentTime / audio.duration : 0;
  $("#mini-progress").style.transform = `scaleX(${p})`;
  $("#np-progress").style.transform = `scaleX(${p})`;
  const s = Math.floor(audio.currentTime);
  $("#np-time").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
});
// Next: forward through history after going back; otherwise the best match you haven't heard yet.
// It follows this song's picks if you made any, else your whole taste, else plain similarity.
function next() {
  if (trail.fwd.length) return play(trail.fwd.pop(), { via: "fwd" });
  const heard = new Set([...trail.back, seedId()]);
  const list = said(picks()) || !liking().length ? songRecs(seedId(), { limit: 40 }) : tasteRecs({ limit: 40 });
  const pick = list.find(r => !heard.has(r.id));
  if (pick) play(pick.id, { via: "next" });
}
function back() {
  if (trail.back.length) return play(trail.back.pop(), { via: "back" });
  audio.currentTime = 0;
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
  $("#np-prev").classList.toggle("dim", !trail.back.length);
  $("#np-tags").innerHTML = [t.bpm ? `${Math.round(t.bpm)} bpm` : null, ...(t.tg || [])].filter(Boolean)
    .map(x => `<i>${esc(x)}</i>`).join("");
  const credits = [];
  if (t.pd?.length) credits.push(`<b>Produced by</b> ${esc(t.pd.join(", "))}`);
  if (t.sd?.length) credits.push(`<b>Samples</b> ${esc(t.sd.slice(0, 3).join(" · "))}`);
  if (t.gu) credits.push(`<a href="${esc(t.gu)}" target="_blank" rel="noopener">Credits on Genius</a>`);
  $("#np-credits").innerHTML = credits.join("<br>");
  $("#np-text").value = picks().text;
  renderSheetPicks();
  renderPlayIcons();
}

// ---------- per-song aspect controls ----------
function renderAspectChips(root, id = seedId()) {
  const p = picks(id);
  root.innerHTML = ASPECT_ORDER.map(a => {
    const state = p.liked.includes(a) ? "like" : p.disliked.includes(a) ? "dislike" : "none";
    const mark = state === "like" ? "♥" : state === "dislike" ? "✕" : "+";
    return `<button class="aspect" data-aspect="${a}" data-state="${state}" type="button" aria-pressed="${state !== "none"}">
      <span class="mark">${mark}</span>${esc(ASPECTS[a].label)}</button>`;
  }).join("");
}
function cycleAspect(a) {
  const id = seedId(), p = picks(id);
  const state = p.liked.includes(a) ? "like" : p.disliked.includes(a) ? "dislike" : "none";
  const liked = p.liked.filter(x => x !== a), disliked = p.disliked.filter(x => x !== a);
  if (state === "none") liked.push(a); else if (state === "like") disliked.push(a);
  setPicks(id, { liked, disliked, text: p.text });
  refresh();
}
function renderHeard(el) {
  const text = picks().text;
  if (!text.trim()) { el.innerHTML = ""; return; }
  const p = model.parse(text);
  const bits = [
    ...p.liked.map(a => `<b>♥ ${esc(ASPECTS[a].label)}</b>`),
    ...p.disliked.map(a => `✕ ${esc(ASPECTS[a].label)}`),
    ...p.descriptors.map(k => `<b>“${esc(model.descriptors[k].label)}”</b>`),
  ];
  el.innerHTML = bits.length ? `Heard: ${bits.join(" · ")}` : "Didn't catch an aspect. Try drums, sample, vocals, 808s, piano, angelic…";
}
// Instant feedback in the player: the top matches for exactly what you picked in this song.
function renderSheetPicks() {
  renderAspectChips($("#np-aspects"));
  renderHeard($("#np-heard"));
  const p = picks(), box = $("#np-matches");
  if (!said(p)) { box.innerHTML = ""; return; }
  box.innerHTML = `<h4 class="mini-head">Songs with ${esc(describe(p, { max: 3 }))}</h4>` +
    songRecs(seedId(), { limit: 5 }).map(r => recRow(r)).join("");
}
function refresh() {
  renderSheetPicks();
  if (ui.tab === "all") renderAll();
  else if (ui.tab === "foryou") renderForYouList();
  else if (ui.tab === "taste") renderTaste();
  else if (ui.tab === "rate" && !test) renderRate();
}
document.addEventListener("click", (e) => {
  const chip = e.target.closest(".aspect");
  if (chip) cycleAspect(chip.dataset.aspect);
});
let typing;
$("#np-text").addEventListener("input", (e) => {
  const id = seedId(), p = picks(id);
  setPicks(id, { ...p, text: e.target.value });
  clearTimeout(typing);
  typing = setTimeout(refresh, 220);
});

// ---------- shared row markup ----------
function trackRow(t) {
  return `<div class="row ${store.current === t.id ? "playing" : ""}" data-id="${t.id}">
    <button class="row-main" data-play="${t.id}" type="button">
      <img src="${esc(art(t, 100))}" alt="" loading="lazy">
      <span class="row-text"><b>${esc(t.t)}</b><span>${esc(t.a)}</span></span>
    </button></div>`;
}
function recRow(r, { votes = false, because = false } = {}) {
  const t = model.track(r.id), vote = store.feedback[t.id];
  const why = r.why.length ? r.why.map(w => `<i>${esc(w)}</i>`) : (t.tg || []).slice(0, 2).map(w => `<i class="tag">${esc(w)}</i>`);
  const from = because && r.because != null ? `<span class="because">Because you like ${esc(becauseLabel(r.because))}</span>` : "";
  return `<div class="row ${store.current === t.id ? "playing" : ""}" data-id="${t.id}">
    <button class="row-main" data-play="${t.id}" type="button"><img src="${esc(art(t, 100))}" alt="" loading="lazy">
    <span class="row-text"><b>${esc(t.t)}</b><span>${esc(t.a)}</span>${from}<span class="why">${why.join("")}</span></span></button>
    ${votes ? `<button class="vote up ${vote === true ? "on" : ""}" data-vote="${t.id}" data-v="1" type="button" aria-label="More like this">${ICON.up}</button>
    <button class="vote down ${vote === false ? "on" : ""}" data-vote="${t.id}" data-v="0" type="button" aria-label="Less like this">${ICON.down}</button>` : ""}
  </div>`;
}
function card(id) {
  const x = model.track(id);
  return `<button class="card" data-play="${x.id}" type="button"><img src="${esc(art(x))}" alt="" loading="lazy"><b>${esc(x.t)}</b><span>${esc(firstArtist(x.a))}</span></button>`;
}
function covers(ids, n = 5) {
  return `<span class="covers">${ids.slice(0, n).map(id => `<img src="${esc(art(model.track(id), 100))}" alt="">`).join("")}</span>`;
}

// ---------- views ----------
function renderView() {
  if (ui.tab === "all") renderAll();
  else if (ui.tab === "foryou") renderForYou();
  else if (ui.tab === "taste") renderTaste();
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

function renderAll() {
  const v = $("#view-all"), mine = liking();
  const likedTracks = store.liked.map(id => model.track(id)).filter(Boolean);
  const described = mine.filter(e => e.weight === 1).slice(0, 3);
  const mix = mine.length ? tasteRecs({ limit: 10 }) : songRecs(seedId(), { limit: 10 });
  v.innerHTML = `
    <div class="tiles">
      <button class="tile" data-goto-section="liked-section" type="button"><span class="tile-icon liked">${ICON.heart}</span><span>Liked Songs</span></button>
      <button class="tile" data-goto="taste" type="button"><span class="tile-icon taste">${ICON.sliders}</span><span>Your taste</span></button>
      ${seeds.slice(0, 4).map(id => { const t = model.track(id);
        return `<button class="tile" data-play="${id}" type="button"><img src="${esc(art(t, 100))}" alt=""><span>${esc(t.t)}</span></button>`; }).join("")}
    </div>
    <h2 class="section">Made for you</h2>
    <p class="sub">${mine.length ? `From what you love in ${mine.length} song${mine.length > 1 ? "s" : ""}`
      : `Sounds like ${esc(model.track(seedId()).t)}. Open the player and tell it what hits.`}</p>
    <div class="cards">${mix.map(r => card(r.id)).join("")}</div>
    ${described.map(e => `<h2 class="section because-head">Because you like ${esc(becauseLabel(e.seed))}</h2>
      <div class="cards">${songRecs(e.seed, { limit: 10 }).map(r => card(r.id)).join("")}</div>`).join("")}
    <h2 class="section" id="seeds-section">Your seeds</h2>
    ${seeds.map(id => trackRow(model.track(id))).join("")}
    <h2 class="section" id="liked-section">Liked Songs</h2>
    ${likedTracks.length ? likedTracks.map(t => trackRow(t)).join("") : '<p class="empty">Tap ♥ in the player to save songs here.</p>'}`;
}

function renderForYou() {
  const mine = liking();
  const head = mine.length
    ? `<div class="foryou-head">
        <div class="foryou-seed">${covers(mine.map(e => e.seed))}
          <div><b>Your mix</b><span>Built from what you love in ${mine.length} song${mine.length > 1 ? "s" : ""}</span></div></div>
        <button class="cta ghost" data-goto="taste" type="button">See or edit your taste</button>
      </div>`
    : `<div class="foryou-head empty-head"><b>Your For You starts with one song.</b>
        <span>Play something you love, open the player and tap what hits: the drums, the sample, the vocals.
        Do it for a few songs and this list becomes your taste. Until then it's plain “sounds like ${esc(short(model.track(seedId()).t))}”.</span>
        <button class="cta" data-open-player type="button">Open the player</button></div>`;
  $("#view-foryou").innerHTML = `${head}<h2 class="section">For You</h2><div id="fy-list"></div>`;
  renderForYouList();
}
function renderForYouList() {
  const list = $("#fy-list");
  if (!list) return;
  const mine = liking();
  const results = mine.length ? tasteRecs({ limit: 20 }) : songRecs(seedId(), { limit: 20 });
  list.innerHTML = results.map(r => recRow(r, { votes: true, because: mine.length > 1 })).join("")
    || '<p class="empty">You\'ve rated everything that matches. Describe another song to widen it.</p>';
}

function renderTaste() {
  const mine = taste();
  const rows = mine.map(e => {
    const t = model.track(e.seed), p = picks(e.seed);
    const chips = [...p.liked.map(a => `<i>♥ ${esc(ASPECTS[a].label)}</i>`),
                   ...p.disliked.map(a => `<i class="no">✕ ${esc(ASPECTS[a].label)}</i>`),
                   ...(p.text.trim() ? [`<i class="said">“${esc(p.text.trim())}”</i>`] : []),
                   ...(e.weight < 1 ? ['<i class="tag">♥ the whole song</i>'] : [])];
    return `<div class="row taste-row">
      <button class="row-main" data-play="${t.id}" data-open="1" type="button"><img src="${esc(art(t, 100))}" alt="" loading="lazy">
      <span class="row-text"><b>${esc(t.t)}</b><span>${esc(t.a)}</span><span class="why">${chips.join("")}</span></span></button>
      <button class="vote" data-forget="${t.id}" type="button" aria-label="Remove from your taste">${ICON.x}</button></div>`;
  }).join("");
  $("#view-taste").innerHTML = `
    <div class="how">
      <b>How your For You is built</b>
      <ol>
        <li><span>1</span><p>Every song is split into its parts (drums, 808s/bass, melody and samples, vocals) and each part gets its own sound fingerprint. Genius adds who produced it, what it samples and who sang backing vocals.</p></li>
        <li><span>2</span><p>When you tap <em>The sample</em> on a song, every other song is scored on how close its sample part is to this one, plus a little whole-song similarity so it stays in the same lane. Tapping twice pushes that part away.</p></li>
        <li><span>3</span><p>Each song you like something in is one vote in your taste. A song ranks high when it strongly matches one of them, with a bonus when it matches several. A song where you only tapped ✕ isn't a like: it pushes songs with those parts down. 👍 and 👎 in For You nudge it further.</p></li>
        <li><span>4</span><p>It's for discovering: a song you've described, hearted, voted on or rated is never recommended again.</p></li>
      </ol>
    </div>
    <h2 class="section">Your taste <span class="count">${mine.length} song${mine.length === 1 ? "" : "s"}</span></h2>
    ${rows || '<p class="empty">Nothing yet. Play a song, open the player and tap what hits for you.</p>'}
    ${mine.length ? '<button class="cta ghost" id="clear-taste" type="button">Start over</button>' : ""}`;
}

// ---------- blind A/B rating ----------
function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
function startTest() {
  const ask = { seed: seedId(), ...picks() };
  if (!said(ask)) {
    toast("First pick what hits (or type it) for this song");
    return;
  }
  const a = model.recommend({ ...ask, limit: 5, feedback: {}, exclude: rated() }).map(r => r.id);
  const p = model.recommend({ ...ask, limit: 5, feedback: {}, exclude: rated(), mode: "plain" }).map(r => r.id);
  const ids = [...new Set([...a, ...p])];
  test = { seed: ask.seed, liked: ask.liked, disliked: ask.disliked, text: ask.text, at: Date.now(),
           items: shuffle(ids).map(id => ({ id, methods: [a.includes(id) && "aspect", p.includes(id) && "plain"].filter(Boolean) })), ratings: {} };
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
  let body = "";
  if (!test) {
    const ask = describe(picks(), { max: 9 });
    body = `<button class="cta" id="start-test" type="button">Start a blind round for ${esc(t.t)}</button>
      <p class="sub" style="margin-top:10px">Asking for: ${esc(ask || "nothing yet. Open the player and pick what hits in this song first.")}</p>`;
  } else {
    const done = test.items.every(i => test.ratings[i.id]);
    body = `<p class="sub">How well does each song match <b>${esc(describe(test, { max: 9 }) || "your request")}</b> in ${esc(model.track(test.seed).t)}? 1 = not at all, 5 = exactly.</p>
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
$("#np-next").addEventListener("click", next);
$("#np-prev").addEventListener("click", back);
$("#np-foryou").addEventListener("click", () => { closeSheet(); setTab("foryou"); });
$("#np-like").addEventListener("click", () => {
  const id = seedId(), i = store.liked.indexOf(id);
  if (i >= 0) store.liked.splice(i, 1); else store.liked.unshift(id);
  store.save();
  $("#np-like").classList.toggle("on", i < 0);
  toast(i < 0 ? "Added to Liked Songs" : "Removed from Liked Songs");
  refresh();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeSheet(); closeSearch(); }
});

// ---------- delegated clicks ----------
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-play],[data-goto],[data-goto-section],[data-vote],[data-rate],[data-forget],[data-open-player],#start-test,#finish-test,#export-ratings,#clear-taste,[data-tab],[data-nav]");
  if (!el) return;
  if (el.dataset.rate) {
    test.ratings[el.dataset.rate] = +el.dataset.n;
    renderRate();
    return;
  }
  if (el.dataset.play) { closeSearch(); play(+el.dataset.play, { open: !!el.dataset.open }); return; }
  if (el.dataset.goto) { closeSheet(); setTab(el.dataset.goto); return; }
  if (el.dataset.gotoSection) { document.getElementById(el.dataset.gotoSection)?.scrollIntoView({ behavior: "smooth" }); return; }
  if (el.dataset.tab) { setTab(el.dataset.tab); return; }
  if (el.dataset.nav) { el.dataset.nav === "search" ? openSearch() : setTab(el.dataset.nav); return; }
  if (el.hasAttribute("data-open-player")) { if (!store.current) play(seedId()); openSheet(); return; }
  if (el.dataset.forget) {
    const id = +el.dataset.forget;
    delete store.songs[id];
    store.liked = store.liked.filter(x => x !== id);
    store.save();
    toast("Removed from your taste");
    refresh();
    return;
  }
  if (el.dataset.vote) {
    const id = +el.dataset.vote, v = el.dataset.v === "1";
    if (store.feedback[id] === v) delete store.feedback[id]; else store.feedback[id] = v;
    store.save();
    toast(store.feedback[id] === undefined ? "Vote cleared" : v ? "More like this" : "Less like this");
    renderForYouList();
    return;
  }
  if (el.id === "clear-taste") {
    store.songs = {};
    store.liked = [];
    store.feedback = {};
    store.save();
    toast("Taste cleared");
    refresh();
  }
  if (el.id === "start-test") startTest();
  if (el.id === "finish-test") finishTest();
  if (el.id === "export-ratings") exportRatings();
});

// ---------- intro ----------
function runIntro(force = false) {
  const intro = $("#intro");
  if (store.introSeen && !force) { intro.classList.add("done"); return; }
  intro.classList.remove("done");
  const steps = $$("[data-step]", intro), times = [300, 2100, 4100, 6100, 8100], end = 10100;
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
  for (const id of Object.keys(store.songs)) if (!model.track(+id)) delete store.songs[id];
  renderPlayer();
  $("#mini").hidden = !store.current;
  setTab("all");
  window.facets = { model, store, trail, taste };  // handy for debugging in the console
})();
