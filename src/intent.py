"""Turn a free-text description ("the dancehall beat with the rapping") into aspects.

Keyword-based and deterministic, so it works offline. The app shows what it understood
so the user can correct it.
"""

import re

LABELS = {
    "rhythm": "The beat / groove",
    "tempo": "The tempo / speed",
    "drums": "The drums / 808s",
    "vocals": "The rapping / vocals",
    "melody": "The melody",
    "timbre": "The overall sound / production",
    "energy": "The energy",
    "mood": "The vibe / mood",
}

KEYWORDS = {
    "rhythm": r"beat|groove|rhythm|dancehall|afrobeat|bounce|swing|dance|danceable|syncopat|riddim|bassline|flow of the beat",
    "tempo": r"dancehall|tempo|bpm|fast|slow|speed|pace|uptempo|mid-?tempo|laid.?back",
    "drums": r"beat|drum|808|kick|snare|hi-?hat|percussion|trap beat|bass|knock",
    "vocals": r"rap|rapping|flow|vocal|voice|singing|sing|lyric|bars|verse|delivery|hook|autotune|auto-tune|harmon|singer",
    "melody": r"melod|chord|keys|piano|guitar|sample|tune|catchy|hook|harmony|notes",
    "timbre": r"sound|production|texture|tone|timbre|mix|produced|polished|lo-?fi|gritty|clean|warm|dark sound",
    "energy": r"energy|energetic|hype|intense|aggressive|loud|hard|lit|pump|mellow|calm|chill|soft|quiet",
    "mood": r"vibe|mood|feel|feeling|atmosphere|emotion|dark|moody|sad|happy|bright|summer|romantic|dreamy|ambient|smooth",
}

# Words that flip the clause that follows them to "don't want this".
NEGATIONS = r"\bbut not\b|\bnot the\b|\bwithout\b|\bdon'?t like\b|\bdo not like\b|\bdon'?t want\b|\bavoid\b|\bhate\b|\bless\b|\bno more\b|\bnot a fan of\b|\bsick of\b"


def aspects_in(text, available=None):
    found = [a for a, pattern in KEYWORDS.items() if re.search(rf"\b(?:{pattern})", text.lower())]
    if available is not None:
        found = [a for a in found if a in available]
    return found


def parse_preferences(text, available=None):
    """Return (liked, disliked) aspect lists. Clauses after a negation phrase are dislikes."""
    first, *rest = re.split(NEGATIONS, text.lower())
    disliked = [a for part in rest for a in aspects_in(part, available)]
    liked = [a for a in aspects_in(first, available) if a not in disliked]
    return liked, list(dict.fromkeys(disliked))
