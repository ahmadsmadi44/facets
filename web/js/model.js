// In-browser aspect recommender. Data comes from `python -m src.export_web`.
//
// Each track has five CLAP embeddings: the full mix and four Demucs stems (drums, bass,
// other = melody/samples/instruments, vocals). An aspect compares the matching stem of the
// seed with every other track's stem; Genius credits add sample / background-vocal / producer
// knowledge; free text maps onto calibrated CLAP text descriptors.

export const ASPECTS = {
  drums:    { label: "Drums",            stems: { drums: 1 } },
  bass:     { label: "808s / bass",      stems: { bass: 1 } },
  melody:   { label: "Melody",           stems: { other: 1 } },
  vocals:   { label: "Vocals",           stems: { vocals: 1 } },
  sample:   { label: "The sample",       stems: { other: 0.6 }, knowledge: "sample" },
  backing:  { label: "Background vocals", stems: { vocals: 0.4 }, knowledge: "backing", descriptor: "backing" },
  tempo:    { label: "Tempo",            tempo: true },
  vibe:     { label: "Vibe",             stems: { mix: 1 } },
  producer: { label: "Producers",        knowledge: "producer" },
};

const STEMS = ["mix", "drums", "bass", "other", "vocals"];
// Weight of whole-song similarity when aspects are chosen; the aspect terms together weigh 1.
export const COHERENCE = 0.8;
// Score cost of each extra taste-mix pick that comes from the same one of your songs.
const SOURCE_PENALTY = 0.5;
// How hard a song with only ✕ picks pushes down songs whose parts sound like those.
const AVOID = 0.5;
const KEYWORDS = {
  drums: /\b(drum|drums|beat|hi-?hats?|snare|kick|percussion|boom ?bap|knock|bounce|riddim|groove)/,
  bass: /\b(808s?|bass|bassline|sub)/,
  melody: /\b(melod\w*|chords?|keys|piano|guitar|strings|horns?|synths?|instrumental|production|tune|catchy)/,
  vocals: /\b(vocals?|voice|rap\w*|flow|bars|verse|singing|sing|sung|hook|delivery|lyrics?|cadence)/,
  sample: /\b(sampl\w*|interpolat\w*|flip\w*|chop\w*|chipmunk)/,
  backing: /\b(background|backing|harmon\w*|choir|choral|ad-?libs?|backup)/,
  tempo: /\b(tempo|bpm|fast|slow|speed|pace|uptempo)/,
  vibe: /\b(vibe|mood|feel|feeling|energy|atmosphere)/,
  producer: /\b(producers?|produced|production team|beatmaker|writers?|credits)/,
};
const NEGATION = /\b(?:but not|not the|without|don'?t like|do not like|don'?t want|avoid|hate|less|no more|not a fan of)\b/;
const BACKGROUND_PHRASE = /(?:background|backing)\s+(?:vocals?|singers?|harmon\w*)|harmon\w*|ad-?libs?/g;

export class Model {
  constructor(meta, vectors, descriptors) {
    this.meta = meta;
    this.tracks = meta.tracks;
    this.n = this.tracks.length;
    this.dims = meta.dims;
    this.index = new Map(this.tracks.map((t, i) => [t.id, i]));
    this.vectors = {};
    STEMS.forEach((stem, s) => {
      const out = new Float32Array(this.n * this.dims);
      for (let i = 0; i < this.n; i++) {
        const base = (i * STEMS.length + s) * this.dims;
        let norm = 0;
        for (let d = 0; d < this.dims; d++) { const v = vectors[base + d] / 127; out[i * this.dims + d] = v; norm += v * v; }
        norm = Math.sqrt(norm) || 1;
        for (let d = 0; d < this.dims; d++) out[i * this.dims + d] /= norm;
      }
      this.vectors[stem] = out;
    });
    this.descriptors = meta.descriptors;
    this.descScores = descriptors;  // int8 z-scores * 16, track-major
    this.sourceOwners = new Map();  // sample source -> tracks that use it
    this.tracks.forEach((t, i) => (t.sk || []).forEach(k => {
      if (!this.sourceOwners.has(k)) this.sourceOwners.set(k, []);
      this.sourceOwners.get(k).push(i);
    }));
    this.keyOwners = new Map();
    this.tracks.forEach((t, i) => this.keyOwners.set(t.key, [...(this.keyOwners.get(t.key) || []), i]));
  }

  static async load(base = "data") {
    const [meta, vec, desc] = await Promise.all([
      fetch(`${base}/catalog.json`).then(r => r.json()),
      fetch(`${base}/vectors.bin`).then(r => r.arrayBuffer()),
      fetch(`${base}/descriptors.bin`).then(r => r.arrayBuffer()),
    ]);
    return new Model(meta, new Int8Array(vec), new Int8Array(desc));
  }

  track(id) { return this.tracks[this.index.get(id)]; }

  vec(stem, i) { return this.vectors[stem].subarray(i * this.dims, (i + 1) * this.dims); }

  /** Cosine of every track's stem vector with query q (already in the same space). */
  cosines(stem, q) {
    const V = this.vectors[stem], D = this.dims, out = new Float32Array(this.n);
    let qn = 0; for (let d = 0; d < D; d++) qn += q[d] * q[d];
    qn = Math.sqrt(qn) || 1;
    for (let i = 0; i < this.n; i++) {
      let s = 0; const b = i * D;
      for (let d = 0; d < D; d++) s += V[b + d] * q[d];
      out[i] = s / qn;
    }
    return out;
  }

  /** Rocchio query: seed + 0.75 * mean(liked songs) - 0.25 * mean(disliked songs). */
  query(stem, seed, feedback) {
    const q = Float32Array.from(this.vec(stem, seed));
    for (const [liked, weight] of [[true, 0.75], [false, -0.25]]) {
      const ids = Object.entries(feedback).filter(([, v]) => v === liked).map(([id]) => this.index.get(+id))
        .filter(i => i !== undefined);
      if (!ids.length) continue;
      for (const i of ids) { const v = this.vec(stem, i); for (let d = 0; d < this.dims; d++) q[d] += weight * v[d] / ids.length; }
    }
    return q;
  }

  descriptor(i, k) { return this.descScores[i * this.descriptors.length + k] / 16; }

  /** Calibrated per-track score for descriptors (z-scores across the catalog). */
  descriptorScores(indices) {
    const out = new Float32Array(this.n);
    if (!indices.length) return out;
    for (let i = 0; i < this.n; i++) {
      let s = 0; for (const k of indices) s += this.descriptor(i, k);
      out[i] = s / indices.length;
    }
    return out;
  }

  knowledge(kind, seed) {
    const s = this.tracks[seed], out = new Float32Array(this.n);
    if (kind === "sample") {
      const mine = new Set(s.sk || []);
      for (let i = 0; i < this.n; i++) {
        const t = this.tracks[i];
        const shared = (t.sk || []).some(k => mine.has(k));
        const direct = (t.sk || []).includes(s.key) || mine.has(t.key);
        out[i] = shared || direct ? 2 : (t.sk || []).length ? 0.6 : t.hs ? 0.35 : -0.35;
      }
    } else if (kind === "backing") {
      for (let i = 0; i < this.n; i++) out[i] = this.tracks[i].bk ? 0.6 : -0.15;
    } else if (kind === "producer") {
      const mine = new Set(s.pr || []);
      for (let i = 0; i < this.n; i++) {
        const shared = (this.tracks[i].pr || []).filter(p => mine.has(p)).length;
        out[i] = mine.size ? Math.min(3, 3 * shared / mine.size) : 0;
      }
    }
    return out;
  }

  tempoScores(seed) {
    const out = new Float32Array(this.n), b = this.tracks[seed].bpm;
    for (let i = 0; i < this.n; i++) {
      const c = this.tracks[i].bpm;
      if (!b || !c) continue;
      // Half/double time count as the same feel.
      const ratio = Math.abs(Math.log2(c / b));
      const folded = Math.min(ratio, Math.abs(ratio - 1));
      out[i] = 1.5 - 12 * folded;
    }
    return out;
  }

  /** Parse "the angelic sample and background vocals, but not the drums". */
  parse(text) {
    const lower = (text || "").toLowerCase();
    const [first, ...rest] = lower.split(NEGATION);
    const find = (part) => Object.entries(KEYWORDS).filter(([a, re]) =>
      re.test(a === "vocals" ? part.replace(BACKGROUND_PHRASE, " ") : part)).map(([a]) => a);
    const disliked = [...new Set(rest.flatMap(find))];
    const liked = find(first).filter(a => !disliked.includes(a));
    // Descriptive words ("angelic", "dreamy", "boom bap") match calibrated CLAP descriptors.
    const words = new Set(first.match(/[a-z0-9&'-]+/g) || []);
    const desc = this.descriptors.map((d, k) => [k, d.words.filter(w => words.has(w)).length / d.words.length])
      .filter(([, hit]) => hit >= 0.5).map(([k]) => k);
    return { liked, disliked, descriptors: desc };
  }

  /** z-normalise so aspects with different scales contribute comparably. */
  static z(values, exclude) {
    let sum = 0, sq = 0, m = 0;
    for (let i = 0; i < values.length; i++) if (!exclude.has(i)) { sum += values[i]; sq += values[i] * values[i]; m++; }
    const mean = sum / m, std = Math.sqrt(Math.max(1e-9, sq / m - mean * mean));
    return values.map(v => (v - mean) / std);
  }

  /** Indices of these track ids and every other version of the same title. */
  versions(ids) {
    const seen = new Set();
    for (const id of ids) {
      const i = this.index.get(+id);
      if (i === undefined) continue;
      seen.add(i);
      for (const j of this.keyOwners.get(this.tracks[i].key) || []) seen.add(j);
    }
    return seen;
  }

  /** True when an entry says something you like. One with only ✕ picks is something to avoid. */
  positive(e) {
    if (e.loved || e.liked?.length) return true;
    const p = this.parse(e.text);
    return p.liked.length > 0 || p.descriptors.length > 0;
  }

  /** Score every track for one request: a sum of z-scored parts, plus what's needed to explain it. */
  score({ seed, liked = [], disliked = [], text = "", feedback = {}, exclude = [], mode = "aspect" }) {
    const s = this.index.get(seed);
    const seen = this.versions([seed, ...Object.keys(feedback), ...exclude]);
    const parsed = this.parse(text);
    liked = [...new Set([...liked, ...parsed.liked])].filter(a => !disliked.includes(a));
    disliked = [...new Set([...disliked, ...parsed.disliked])];
    const total = new Float32Array(this.n), parts = {};
    const add = (name, values, weight) => {
      const z = Model.z(values, seen);
      parts[name] = z;
      for (let i = 0; i < this.n; i++) total[i] += weight * z[i];
    };
    const stemCache = {};
    const stemSim = stem => stemCache[stem] ??= this.cosines(stem, this.query(stem, s, feedback));
    if (mode === "plain") {
      add("vibe", stemSim("mix"), 1);
    } else {
      // A little overall similarity keeps results coherent (rap seed -> not gospel for "vocals").
      const asked = liked.length + disliked.length + (parsed.descriptors.length ? 1 : 0);
      add("_coherence", stemSim("mix"), asked ? COHERENCE : 1);
      for (const [aspects, sign] of [[liked, 1 / Math.max(1, asked)], [disliked, -1 / Math.max(1, asked)]]) {
        for (const a of aspects) {
          const spec = ASPECTS[a];
          if (!spec) continue;
          const values = new Float32Array(this.n);
          for (const [stem, w] of Object.entries(spec.stems || {})) {
            const z = Model.z(stemSim(stem), seen);
            for (let i = 0; i < this.n; i++) values[i] += w * z[i];
          }
          if (spec.knowledge) { const k = this.knowledge(spec.knowledge, s); for (let i = 0; i < this.n; i++) values[i] += k[i]; }
          if (spec.descriptor) {
            const ks = this.descriptors.map((d, k) => [d, k]).filter(([d]) => d.group === spec.descriptor).map(([, k]) => k);
            const ds = this.descriptorScores(ks); for (let i = 0; i < this.n; i++) values[i] += 0.5 * ds[i];
          }
          if (spec.tempo) { const t = this.tempoScores(s); for (let i = 0; i < this.n; i++) values[i] += t[i]; }
          add(a, values, sign);
        }
      }
      if (parsed.descriptors.length) add("_words", this.descriptorScores(parsed.descriptors), 1 / asked);
    }
    return { s, seen, total, parts, liked, parsed };
  }

  rank(total, seen, limit, diversity, source = null) {
    const order = Array.from({ length: this.n }, (_, i) => i).filter(i => !seen.has(i))
      .sort((a, b) => total[b] - total[a]);
    return diversity ? this.mmr(order, total, limit, 0.6, source) : order.slice(0, limit);
  }

  /** Songs for one song and what you said about it. */
  recommend({ limit = 12, diversity = true, ...request }) {
    const r = this.score(request);
    return this.rank(r.total, r.seen, limit, diversity)
      .map(i => ({ id: this.tracks[i].id, score: r.total[i], why: this.explain(i, r.s, r.liked, r.parts, r.parsed) }));
  }

  /**
   * Your taste across songs. Each song you described is one request, scored as in recommend()
   * and re-standardised so every song counts the same. A candidate's score is the mean over your
   * songs plus half the best single match: it wins by matching one of your songs strongly and
   * gets a bonus for matching several. `because` is the song that match came from, and is only
   * ever a song you like: a song where you only said what you don't like (✕) never votes for
   * anything, it pushes songs with those parts down instead.
   */
  profile(entries, { feedback = {}, exclude = [], limit = 12, diversity = true } = {}) {
    const likes = entries.filter(e => this.positive(e)), avoids = entries.filter(e => !this.positive(e));
    if (!likes.length) return [];
    exclude = [...exclude, ...entries.map(e => e.seed)];
    const runs = likes.map(e => ({ e, r: this.score({ ...e, feedback, exclude }) }));
    const seen = new Set(runs.flatMap(({ r }) => [...r.seen]));
    const mean = new Float32Array(this.n), best = new Float32Array(this.n).fill(-Infinity), from = new Int32Array(this.n);
    let weights = 0;
    runs.forEach(({ e, r }, k) => {
      const w = e.weight ?? 1, z = Model.z(r.total, seen);
      weights += w;
      for (let i = 0; i < this.n; i++) {
        const v = w * z[i];
        mean[i] += v;
        if (v > best[i]) { best[i] = v; from[i] = k; }
      }
    });
    const total = mean.map((m, i) => m / weights + 0.5 * best[i]);
    // Songs whose ✕ parts sound like the parts you said you don't like in that song.
    for (const e of avoids) {
      const r = this.score({ seed: e.seed, liked: [], disliked: e.disliked, text: e.text, feedback, exclude });
      const parts = Object.keys(r.parts).filter(k => !k.startsWith("_"));
      for (const k of parts) for (let i = 0; i < this.n; i++) total[i] -= AVOID * r.parts[k][i] / parts.length / avoids.length;
    }
    return this.rank(total, seen, limit, diversity, from).map(i => {
      const { e, r } = runs[from[i]];
      return { id: this.tracks[i].id, score: total[i], because: e.seed, why: this.explain(i, r.s, r.liked, r.parts, r.parsed) };
    });
  }

  /**
   * Maximal marginal relevance: penalise near-duplicates and cap two songs per artist. With a
   * `source` per track (which of your songs it matched best), each extra pick from the same
   * source costs a little, so one song can't take over a taste mix.
   */
  mmr(order, total, limit, lambda = 0.6, source = null) {
    const pool = order.slice(0, 200), picked = [], perArtist = new Map(), titles = new Set(), perSource = new Map();
    while (picked.length < limit && pool.length) {
      let best = -1, bestScore = -Infinity;
      for (let p = 0; p < pool.length; p++) {
        const i = pool[p], artist = this.tracks[i].a0;
        if ((perArtist.get(artist) || 0) >= 2 || titles.has(this.tracks[i].key)) continue;  // no duplicate versions
        let redundancy = 0;
        for (const j of picked) {
          const a = this.vec("mix", i), b = this.vec("mix", j); let d = 0;
          for (let k = 0; k < this.dims; k++) d += a[k] * b[k];
          redundancy = Math.max(redundancy, d);
        }
        let score = total[i] - lambda * Math.max(0, redundancy - 0.85) * 10;
        if (source) score -= SOURCE_PENALTY * (perSource.get(source[i]) || 0);
        if (score > bestScore) { bestScore = score; best = p; }
      }
      if (best < 0) break;
      const [i] = pool.splice(best, 1);
      picked.push(i);
      if (source) perSource.set(source[i], (perSource.get(source[i]) || 0) + 1);
      titles.add(this.tracks[i].key);
      perArtist.set(this.tracks[i].a0, (perArtist.get(this.tracks[i].a0) || 0) + 1);
    }
    return picked;
  }

  explain(i, s, liked, parts, parsed) {
    const t = this.tracks[i], seed = this.tracks[s], notes = [];
    if (liked.includes("sample")) {
      const shared = (t.sk || []).find(k => (seed.sk || []).includes(k));
      const title = (k) => (t.sd[k] || "").split(" — ")[0];
      if (shared) notes.push(`same sample: ${title((t.sk || []).indexOf(shared)) || shared}`);
      else if ((t.sk || []).includes(seed.key) || (seed.sk || []).includes(t.key)) notes.push("sample link to your song");
      else if ((t.sd || []).length) notes.push(`samples ${title(0)}`);
    }
    if (liked.includes("backing") && t.bk) notes.push("credited background vocals");
    if (liked.includes("producer")) {
      const shared = (t.pr || []).filter(p => (seed.pr || []).includes(p));
      if (shared.length) notes.push(`prod. ${shared.slice(0, 2).join(", ")}`);
    }
    for (const a of liked) {
      if (["sample", "backing", "producer"].includes(a) || !parts[a]) continue;
      if (parts[a][i] > 1.2) notes.push(`${ASPECTS[a].label.toLowerCase()} match`);
    }
    if (liked.includes("tempo") && t.bpm) notes.push(`${Math.round(t.bpm)} bpm`);
    for (const k of parsed.descriptors) if (this.descriptor(i, k) > 1.5) notes.push(this.descriptors[k].label);
    return notes.slice(0, 3);
  }
}
