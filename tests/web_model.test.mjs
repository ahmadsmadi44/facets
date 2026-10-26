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

test("text parsing separates background vocals, negation and descriptors", () => {
  const p = model.parse("the angelic sample and background vocals, but not the drums");
  assert.deepEqual(p.liked.sort(), ["backing", "sample"]);
  assert.deepEqual(p.disliked, ["drums"]);
  assert.ok(p.descriptors.some(k => model.descriptors[k].label === "angelic vocals"));
  assert.deepEqual(model.parse("the rapping").liked, ["vocals"]);
});
