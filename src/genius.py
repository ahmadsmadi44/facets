"""Pull human-written descriptors (bio, credits, samples) for catalog songs from the Genius API.

Needs a free API client token in .env as GENIUS_TOKEN. Raw responses are cached per track in
gitignored data/genius/, so reruns only fetch what is missing.
"""

import argparse
import difflib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from src.catalog import base_title, credited

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
API = "https://api.genius.com"
RELATIONS = ("samples", "sampled_in", "interpolates", "interpolated_by", "cover_of", "covered_by",
             "remix_of", "remixed_by", "live_version_of", "performed_live_as")


def token():
    if os.environ.get("GENIUS_TOKEN"):
        return os.environ["GENIUS_TOKEN"]
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GENIUS_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("Set GENIUS_TOKEN in .env (free client token from genius.com/api-clients)")


def api_get(path, headers, params=None, retries=3):
    for attempt in range(retries):
        response = requests.get(f"{API}{path}", params=params, headers=headers, timeout=30)
        if response.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()["response"]
    raise RuntimeError("Genius rate limit persisted")


def best_hit(hits, title, artist):
    """Pick the search hit whose title and primary artist match; None if nothing is close."""
    wanted = base_title(title)
    best, best_score = None, 0.0
    for hit in hits:
        result = hit["result"]
        ratio = difflib.SequenceMatcher(None, wanted, base_title(result["title"])).ratio()
        names = result.get("artist_names", "")
        first = artist.split(" & ")[0].split(",")[0].strip().lower()
        if first not in names.lower():
            continue
        if ratio > best_score:
            best, best_score = result, ratio
    return best if best_score >= 0.8 else None


def fetch_track(track_id, title, artist, folder, headers):
    target = folder / f"{track_id}.json"
    if target.exists():
        return
    hits = api_get("/search", headers, {"q": f"{base_title(title)} {artist.split(' & ')[0]}"})["hits"]
    result = best_hit(hits, title, artist)
    record = {"track_id": int(track_id), "matched": False}
    if result:
        song = api_get(f"/songs/{result['id']}", headers, {"text_format": "plain"})["song"]
        record = {
            "track_id": int(track_id), "matched": True, "genius_id": song["id"], "url": song["url"],
            "genius_title": song["full_title"],
            "bio": (song.get("description") or {}).get("plain", ""),
            "producers": [a["name"] for a in song.get("producer_artists", [])],
            "writers": [a["name"] for a in song.get("writer_artists", [])],
            "featured": [a["name"] for a in song.get("featured_artists", [])],
            "performances": {p["label"]: [a["name"] for a in p["artists"]]
                             for p in song.get("custom_performances", [])},
            "relationships": {rel["relationship_type"]: [s["full_title"] for s in rel["songs"]]
                              for rel in song.get("song_relationships", []) if rel["songs"]},
        }
    target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def build(data_dir=DATA_DIR, pause=0.4, limit=None):
    data_dir = Path(data_dir)
    catalog = pd.read_csv(data_dir / "catalog.csv", index_col=0)
    folder = data_dir / "genius"
    folder.mkdir(exist_ok=True)
    headers = {"Authorization": f"Bearer {token()}"}
    rows = list(catalog.iterrows())[:limit]
    for n, (track_id, row) in enumerate(rows, 1):
        try:
            fetch_track(track_id, row["title"], row["artist"], folder, headers)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"  {track_id} {row['title']}: {exc}", flush=True)
        if n % 50 == 0:
            print(f"{n}/{len(rows)}", flush=True)
        time.sleep(pause)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")]
    matched = sum(r["matched"] for r in records)
    print(f"Genius: matched {matched}/{len(records)} tracks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    build(args.data_dir, limit=args.limit)


if __name__ == "__main__":
    main()
