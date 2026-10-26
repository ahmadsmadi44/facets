// Simulated friends for the social layer (the reel's "see what your friends are playing").
// Friends are fictional; their songs come from the real catalog and change over time.
// Your own reactions and comments are kept in this browser.

export const FRIENDS = [
  { id: "julia", name: "Julia", hue: 330 },
  { id: "mark", name: "Mark", hue: 210 },
  { id: "nia", name: "Nia", hue: 280 },
  { id: "kofi", name: "Kofi", hue: 30 },
  { id: "dre", name: "Dre", hue: 150 },
  { id: "sam", name: "Sam", hue: 0 },
  { id: "leila", name: "Leila", hue: 260 },
];
const ONLINE = 4;

const LINES = [
  "{title} is the perfect song, no notes",
  "{artist} era? ok ok 🔥",
  "Need this on repeat for the rest of the year, absolute masterpiece!",
  "the drums on this 😮‍💨",
  "who produced this??",
  "that sample flip is crazy",
  "this one hits different at night",
  "the vocals at the end >>>",
  "been playing this all week",
  "{artist} never misses",
  "this beat switch tho",
  "underrated fr",
];

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function avatar(person, cls = "", letters = 2) {
  const initials = person.name.slice(0, letters).toUpperCase();
  const style = `background:linear-gradient(135deg,hsl(${person.hue} 70% 52%),hsl(${person.hue + 40} 65% 28%))`;
  return `<span class="av ${cls}" style="${style}" aria-hidden="true">${esc(initials)}</span>`;
}

const rand = (n) => Math.floor(Math.random() * n);
const pick = (list) => list[rand(list.length)];

export class Social extends EventTarget {
  constructor(model, poolIds, store) {
    super();
    this.model = model;
    this.pool = poolIds.filter(id => model.index.has(id));
    this.store = store;
    this.state = FRIENDS.map((f, i) => ({
      ...f, online: i < ONLINE, track: pick(this.pool), started: Date.now() - rand(120000),
      reactions: { "❤️": 2 + rand(9), "🔥": 1 + rand(8), "💯": rand(4) },
      comments: this.seedComments(f, 2 - (i % 2)),
    }));
    this.state.forEach(f => { if (!f.online) f.lastSeen = Date.now() - (5 + rand(90)) * 60000; });
  }

  line(trackId, avoid = []) {
    const t = this.model.track(trackId);
    const fresh = LINES.filter(l => !avoid.some(a => a.startsWith(l.slice(0, 12))));
    return pick(fresh.length ? fresh : LINES).replace("{title}", t.t.split(" (")[0]).replace("{artist}", t.a.split(" & ")[0].split(",")[0]);
  }

  seedComments(friend, count) {
    const others = FRIENDS.filter(f => f.id !== friend.id);
    return Array.from({ length: count }, (_, k) => ({ who: pick(others).id, text: null, at: Date.now() - (count - k) * 60000 * (1 + rand(9)) }));
  }

  friend(id) { return this.state.find(f => f.id === id); }
  person(id) { return id === "me" ? { id: "me", name: "Ahmad", hue: 140 } : FRIENDS.find(f => f.id === id); }

  commentsFor(f) {
    const mine = this.store.comments[`${f.id}:${f.track}`] || [];
    const theirs = f.comments.map((c, k) => ({ ...c, text: c.text || (c.text = this.line(f.track, f.comments.slice(0, k).map(x => x.text || ""))) }));
    return [...theirs, ...mine].sort((a, b) => a.at - b.at).slice(-4);
  }

  myReaction(f) { return this.store.reactions[`${f.id}:${f.track}`] || null; }

  react(id, emoji) {
    const f = this.friend(id), key = `${f.id}:${f.track}`, prev = this.store.reactions[key];
    if (prev) f.reactions[prev]--;
    if (prev === emoji) delete this.store.reactions[key];
    else { this.store.reactions[key] = emoji; f.reactions[emoji]++; }
    this.store.save();
    this.emit(id, "react");
  }

  comment(id, text) {
    const f = this.friend(id), key = `${f.id}:${f.track}`;
    (this.store.comments[key] ||= []).push({ who: "me", text, at: Date.now() });
    this.store.save();
    this.emit(id, "comment");
  }

  emit(id, kind) { this.dispatchEvent(new CustomEvent("change", { detail: { id, kind } })); }

  /** Something happens every few seconds: a reaction, a comment, or a friend changes song. */
  start() {
    const step = () => {
      const online = this.state.filter(f => f.online), f = pick(online), roll = Math.random();
      if (roll < 0.55) {
        const e = pick(["❤️", "❤️", "🔥", "🔥", "💯"]);
        f.reactions[e]++;
        this.emit(f.id, `bump:${e}`);
      } else if (roll < 0.85) {
        f.comments.push({ who: pick(FRIENDS.filter(x => x.id !== f.id)).id, text: this.line(f.track, f.comments.map(c => c.text || "")), at: Date.now() });
        this.emit(f.id, "comment");
      } else {
        f.track = pick(this.pool);
        f.started = Date.now();
        f.reactions = { "❤️": rand(3), "🔥": rand(2), "💯": 0 };
        f.comments = [];
        this.emit(f.id, "track");
      }
      this.timer = setTimeout(step, 3500 + rand(4000));
    };
    this.timer = setTimeout(step, 4000);
  }
}

export function ago(ms) {
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}
