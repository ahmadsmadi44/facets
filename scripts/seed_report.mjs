// Print new-model vs plain-similarity results for the listener's seed requests.
// Usage: node scripts/seed_report.mjs
import { readFileSync } from "node:fs";
import { Model } from "../web/js/model.js";
const dir = new URL("../web/data/", import.meta.url);
const model = new Model(JSON.parse(readFileSync(new URL("catalog.json", dir), "utf8")),
  new Int8Array(readFileSync(new URL("vectors.bin", dir)).buffer.slice(0)),
  new Int8Array(readFileSync(new URL("descriptors.bin", dir)).buffer.slice(0)));
export const REQUESTS = [
  ["Champagne Poetry", ["sample", "backing"], "the angelic choir sample"],
  ["8am in Charlotte", ["melody", "vocals"], ""],
  ["Stories About My Brother", ["vocals", "melody"], ""],
  ["Make Them Pay", ["drums", "sample"], ""],
  ["Love All", ["vocals", "melody"], ""],
  ["I Got A Story To Tell", ["vocals", "drums"], ""],
  ["September", ["drums", "backing"], ""],
  ["Ain't No Mountain High Enough", ["vocals", "backing"], ""],
];
for (const [title, liked, text] of REQUESTS) {
  const seed = model.tracks.find(t => t.t.startsWith(title));
  if (!seed) { console.log("MISSING", title); continue; }
  const a = model.recommend({ seed: seed.id, liked, text, limit: 8 });
  const p = model.recommend({ seed: seed.id, liked, text, limit: 8, mode: "plain" });
  console.log(`\n## ${title} [${seed.tg.join(", ")}] — like ${liked.join("+")} ${text ? `"${text}"` : ""}`);
  for (let k = 0; k < 8; k++) {
    const x = model.track(a[k].id), y = model.track(p[k].id);
    console.log(`  ${(x.t.slice(0, 30) + " — " + x.a0).padEnd(52)} ${("[" + a[k].why.join("; ") + "]").slice(0, 60).padEnd(60)} | plain: ${y.t.slice(0, 26)} — ${y.a0}`);
  }
}
