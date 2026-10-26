"""Build a hip hop / R&B catalog from the iTunes Search API and cache 30 s previews.

Previews are for personal, local use. They stay in gitignored data/ and are not redistributed.
"""

import argparse
import re
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ARTISTS = Path(__file__).resolve().parents[1] / "artists.txt"
SEEDS = Path(__file__).resolve().parents[1] / "seeds.txt"
SEARCH = "https://itunes.apple.com/search"
GENRES = {"hip-hop/rap", "r&b/soul", "rap", "hip hop/rap", "hip-hop", "r&b", "soul", "funk", "disco", "pop",
          "afrobeats", "afro-beat", "african", "afro-pop", "uk hip-hop", "dance", "neo-soul", "motown"}


def read_lines(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines() if Path(path).exists() else []
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def read_artists(path=ARTISTS):
    """'Drake | 100' sets a per-artist track count; plain names use the default."""
    entries = []
    for line in read_lines(path):
        name, _, count = line.partition("|")
        entries.append((name.strip(), int(count) if count.strip() else None))
    return entries


def read_seeds(path=SEEDS):
    """'Title - Artist' lines: songs that must be in the catalog regardless of genre or rank."""
    return [tuple(part.strip() for part in line.rsplit(" - ", 1)) for line in read_lines(path) if " - " in line]


def base_title(title):
    """Collapse remasters, deluxe tags and featuring credits to dedupe versions."""
    return re.sub(r"\s*[\(\[].*?[\)\]]|\s*-\s*(remaster|single|radio|live).*", "", title, flags=re.I).strip().lower()


def credited(artist_name, wanted):
    """True if `wanted` is exactly one of the credited artists (not a substring like Future Islands)."""
    protected = artist_name.lower().replace(wanted, "@@")
    parts = re.split(r"\s*(?:&|,|;|feat\.?|ft\.?|with| x )\s*", protected)
    return "@@" in [part.strip() for part in parts]


def search_artist(artist, per_artist=25, session=None):
    session = session or requests
    response = session.get(SEARCH, params={"term": artist, "entity": "song", "attribute": "artistTerm",
                                           "limit": 200, "country": "US"}, timeout=20)
    response.raise_for_status()
    wanted = artist.lower()
    rows, seen = [], set()
    for item in response.json().get("results", []):
        if not credited(item.get("artistName", ""), wanted) or not item.get("previewUrl"):
            continue
        if item.get("primaryGenreName", "").lower() not in GENRES:
            continue
        key = base_title(item["trackName"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row_for(item, artist))
        if len(rows) >= per_artist:
            break
    return rows


def row_for(item, seed_artist):
    return {"track_id": item["trackId"], "title": item["trackName"], "artist": item["artistName"],
            "seed_artist": seed_artist, "album": item.get("collectionName"),
            "genre": item.get("primaryGenreName"), "preview_url": item["previewUrl"],
            "artwork": item.get("artworkUrl100")}


def search_song(title, artist, session=None):
    """Find one specific song by title and credited artist; None if iTunes has no match."""
    session = session or requests
    response = session.get(SEARCH, params={"term": f"{title} {artist}", "entity": "song", "limit": 25,
                                           "country": "US"}, timeout=20)
    response.raise_for_status()
    wanted = base_title(title)
    for item in response.json().get("results", []):
        if item.get("previewUrl") and credited(item.get("artistName", ""), artist.lower())                 and base_title(item["trackName"]).startswith(wanted):
            return row_for(item, artist)
    return None


def search_deezer(title, artist, session=None):
    """Fallback for songs missing from the US iTunes store. IDs are negated Deezer IDs; Deezer
    preview links expire, so the web app refreshes them by ID at play time."""
    session = session or requests
    response = session.get("https://api.deezer.com/search", params={"q": f"{title} {artist}"}, timeout=20)
    response.raise_for_status()
    wanted = base_title(title)
    for item in response.json().get("data", []):
        if item.get("preview") and base_title(item["title"]).startswith(wanted)                 and artist.lower() in item["artist"]["name"].lower():
            return {"track_id": -int(item["id"]), "title": base_title(item["title"]).title(),
                    "artist": item["artist"]["name"], "seed_artist": artist, "album": item["album"]["title"],
                    "genre": "Hip-Hop/Rap", "preview_url": item["preview"], "artwork": item["album"]["cover_medium"]}
    return None


def split_for(track_id):
    """Deterministic 80/10/10 split from the track ID."""
    bucket = (abs(int(track_id)) * 2654435761) % 100
    return "training" if bucket < 80 else "validation" if bucket < 90 else "test"


def build_catalog(artists, per_artist=30, data_dir=DATA_DIR, pause=3.0, seeds=()):
    rows = []
    for title, artist in seeds:
        try:
            found = search_song(title, artist) or search_deezer(title, artist)
        except requests.RequestException as exc:
            found = None
            print(f"  seed {title}: FAILED ({exc})", flush=True)
        print(f"  seed {title} - {artist}: {'ok' if found else 'NOT FOUND'}", flush=True)
        rows += [found] if found else []
        time.sleep(pause)
    for artist, count in artists:
        try:
            found = search_artist(artist, count or per_artist)
        except requests.RequestException as exc:
            print(f"  {artist}: FAILED ({exc})", flush=True)
            continue
        print(f"  {artist}: {len(found)} tracks", flush=True)
        rows += found
        time.sleep(pause)  # iTunes rate-limits to roughly 20 requests a minute
    if not rows:
        raise RuntimeError("No tracks found; check network access")
    frame = pd.DataFrame(rows).drop_duplicates("track_id").set_index("track_id")
    frame["split"] = [split_for(i) for i in frame.index]
    frame["source"] = "itunes_preview"
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    frame.to_csv(Path(data_dir) / "catalog.csv")
    return frame


def download_previews(catalog, data_dir=DATA_DIR):
    folder = Path(data_dir) / "previews"
    folder.mkdir(parents=True, exist_ok=True)
    done = 0
    for track_id, url in catalog["preview_url"].items():
        target = folder / f"{track_id}.m4a"
        if target.exists():
            continue
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            target.write_bytes(response.content)
            done += 1
        except requests.RequestException as exc:
            print(f"  {track_id}: download failed ({exc})", flush=True)
    print(f"Downloaded {done} new previews into {folder}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artists", type=Path, default=ARTISTS)
    parser.add_argument("--per-artist", type=int, default=30)
    parser.add_argument("--seeds", type=Path, default=SEEDS)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    catalog = build_catalog(read_artists(args.artists), args.per_artist, args.data_dir,
                            seeds=read_seeds(args.seeds))
    print(f"Catalog: {len(catalog)} tracks from {catalog.seed_artist.nunique()} artists")
    download_previews(catalog, args.data_dir)


if __name__ == "__main__":
    main()
