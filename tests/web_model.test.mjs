// Run with: node --test tests/web_model.test.mjs   (needs web/data from python -m src.export_web)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Model } from "../web/js/model.js";

const dir = new URL("../web/data/", import.meta.url);
const meta = JSON.parse(readFileSync(new URL("catalog.json", dir), "utf8"));
const model = new Model(meta, new Int8Array(readFileSync(new URL("vectors.bin", dir)).buffer.slice(0)),
                        new Int8Array(readFileSync(new URL("descriptors.bin", dir)).buffer.slice(0)));
const byTitle = (t) => model.tracks.find(x => x.t.startsWith(t));
const seed = (byTitle("Champagne Poetry") || model.tracks[0]).id;

test("data shapes line up", () => {
  assert.equal(model.vectors.mix.length, model.n * model.dims);
  assert.equal(model.descScores.length, model.n * model.descriptors.length);
});

test("recommendations exclude the seed and respect the limit", () => {
  const recs = model.recommend({ seed, liked: ["drums"], limit: 10 });
  assert.equal(recs.length, 10);
  assert.ok(!recs.some(r => r.id === seed));
});

test("diversity caps each artist at two songs", () => {
  const recs = model.recommend({ seed, liked: ["vocals"], limit: 12 });
  const counts = {};
  for (const r of recs) { const a = model.track(r.id).a0; counts[a] = (counts[a] || 0) + 1; }
  assert.ok(Math.max(...Object.values(counts)) <= 2);
});

test("sample aspect prefers songs with sample credits", () => {
  const recs = model.recommend({ seed, liked: ["sample"], limit: 10 });
  const withSample = recs.filter(r => model.track(r.id).sk.length || model.track(r.id).hs).length;
  assert.ok(withSample >= 8, `only ${withSample}/10 have a sample`);
});

test("different aspects give different lists, plain mode ignores aspects", () => {
  const drums = model.recommend({ seed, liked: ["drums"], limit: 10 }).map(r => r.id);
  const vocals = model.recommend({ seed, liked: ["vocals"], limit: 10 }).map(r => r.id);
  assert.ok(drums.filter(id => vocals.includes(id)).length < 8);
  const plainA = model.recommend({ seed, liked: ["drums"], mode: "plain", limit: 10 }).map(r => r.id);
  const plainB = model.recommend({ seed, liked: ["vocals"], mode: "plain", limit: 10 }).map(r => r.id);
  assert.deepEqual(plainA, plainB);
});

test("disliking an aspect pushes similar-sounding songs down", () => {
  const liked = model.recommend({ seed, liked: ["drums"], limit: 10, diversity: false }).map(r => r.id);
  const avoided = model.recommend({ seed, disliked: ["drums"], limit: 200, diversity: false }).map(r => r.id);
  for (const id of liked.slice(0, 3)) assert.ok(!avoided.slice(0, 20).includes(id));
});

test("song feedback moves results", () => {
  const before = model.recommend({ seed, liked: ["melody"], limit: 10 });
  const after = model.recommend({ seed, liked: ["melody"], limit: 10, feedback: { [before[0].id]: false } });
  assert.ok(!after.some(r => r.id === before[0].id));
});

test("taste profile of one song ranks like that song alone", () => {
  const one = model.recommend({ seed, liked: ["sample"], limit: 10 }).map(r => r.id);
  const prof = model.profile([{ seed, liked: ["sample"], disliked: [], text: "" }], { limit: 10 }).map(r => r.id);
  assert.deepEqual(prof, one);
});

test("taste profile mixes songs, excludes them and says which one each pick came from", () => {
  const other = (byTitle("I Got A Story") || model.tracks[1]).id;
  const entries = [{ seed, liked: ["sample", "backing"], disliked: [], text: "" },
                   { seed: other, liked: ["drums"], disliked: [], text: "" }];
  const recs = model.profile(entries, { limit: 12 });
  assert.equal(recs.length, 12);
  assert.ok(!recs.some(r => r.id === seed || r.id === other));
  const from = new Set(recs.map(r => r.because));
  assert.ok(from.has(seed) && from.has(other), "both songs should contribute");
});

test("songs you've rated are never recommended again", () => {
  const first = model.recommend({ seed, liked: ["sample"], limit: 10 }).map(r => r.id);
  const exclude = first.slice(0, 5);
  const again = model.recommend({ seed, liked: ["sample"], limit: 10, exclude }).map(r => r.id);
  assert.ok(!again.some(id => exclude.includes(id)));
  const prof = model.profile([{ seed, liked: ["sample"], disliked: [], text: "" }], { limit: 10, exclude }).map(r => r.id);
  assert.ok(!prof.some(id => exclude.includes(id)));
});

test("a song with only ✕ picks is never a 'because you like' and pushes its parts down", () => {
  const other = (byTitle("I Got A Story") || model.tracks[1]).id;
  const like = { seed, liked: ["sample"], disliked: [], text: "" };
  const avoid = { seed: other, liked: [], disliked: ["drums"], text: "" };
  assert.ok(model.positive(like) && !model.positive(avoid) && model.positive({ ...avoid, loved: true }));
  const recs = model.profile([like, avoid], { limit: 30 });
  assert.ok(recs.length && recs.every(r => r.because === seed));
  assert.ok(!recs.some(r => r.id === other));
  assert.deepEqual(model.profile([avoid], { limit: 10 }), []);
  // Songs whose drums sound most like the avoided song's drop in the mix.
  const drumsLike = model.recommend({ seed: other, liked: ["drums"], limit: 200, diversity: false }).map(r => r.id);
  const pos = (list, id) => { const i = list.indexOf(id); return i < 0 ? Infinity : i; };
  const plain = model.profile([like], { limit: 200, diversity: false }).map(r => r.id);
  const steered = model.profile([like, avoid], { limit: 200, diversity: false }).map(r => r.id);
  const shared = drumsLike.filter(id => plain.includes(id)).slice(0, 10);
  const moved = shared.filter(id => pos(steered, id) > pos(plain, id)).length;
  assert.ok(moved >= shared.length * 0.7, `only ${moved}/${shared.length} moved down`);
});

test("text parsing separates background vocals, negation and descriptors", () => {
  const p = model.parse("the angelic sample and background vocals, but not the drums");
  assert.deepEqual(p.liked.sort(), ["backing", "sample"]);
  assert.deepEqual(p.disliked, ["drums"]);
  assert.ok(p.descriptors.some(k => model.descriptors[k].label === "angelic vocals"));
  assert.deepEqual(model.parse("the rapping").liked, ["vocals"]);
});
