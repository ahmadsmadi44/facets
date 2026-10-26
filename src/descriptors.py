"""Human-style descriptors scored zero-shot by CLAP against the matching stem.

Each entry: (label shown to users, stem it describes, group). The CLAP prompt is built from the
label. Scores are z-normalised across the catalog, which removes CLAP's bias toward generic
prompts (every hip hop clip looks a bit like "soul sample" in raw similarity).
"""

DESCRIPTORS = [
    # Vocals stem
    ("angelic vocals", "vocals", "vocals"), ("soulful female vocals", "vocals", "vocals"),
    ("soulful male vocals", "vocals", "vocals"), ("falsetto", "vocals", "vocals"),
    ("gritty rap vocals", "vocals", "vocals"), ("aggressive rap", "vocals", "vocals"),
    ("laid-back rap flow", "vocals", "vocals"), ("fast rap flow", "vocals", "vocals"),
    ("storytelling rap", "vocals", "vocals"), ("melodic auto-tune singing", "vocals", "vocals"),
    ("smooth r&b vocals", "vocals", "vocals"), ("deep male voice", "vocals", "vocals"),
    ("female rap", "vocals", "vocals"), ("spoken word", "vocals", "vocals"),
    ("pitched-up chipmunk soul vocal sample", "vocals", "sample"), ("gospel choir", "vocals", "backing"),
    ("background vocal harmonies", "vocals", "backing"), ("vocal ad-libs", "vocals", "backing"),
    ("call and response vocals", "vocals", "backing"), ("whispered vocals", "vocals", "vocals"),
    ("operatic vocals", "vocals", "vocals"), ("crooning", "vocals", "vocals"),
    # Other stem (melody, samples, instruments)
    ("soul sample", "other", "sample"), ("vinyl crackle", "other", "sample"), ("piano", "other", "melody"),
    ("rhodes electric piano", "other", "melody"), ("strings", "other", "melody"),
    ("orchestral", "other", "melody"), ("horns", "other", "melody"), ("brass section", "other", "melody"),
    ("jazz chords", "other", "melody"), ("acoustic guitar", "other", "melody"),
    ("electric guitar", "other", "melody"), ("synth pads", "other", "melody"),
    ("ambient atmosphere", "other", "melody"), ("dark minor chords", "other", "melody"),
    ("bright major chords", "other", "melody"), ("flute", "other", "melody"), ("bells", "other", "melody"),
    ("church organ", "other", "melody"), ("harp", "other", "melody"),
    ("afrobeat guitar", "other", "melody"), ("disco strings", "other", "melody"),
    ("funk guitar", "other", "melody"), ("motown", "other", "melody"), ("cinematic", "other", "melody"),
    ("lo-fi", "other", "melody"), ("dreamy", "other", "melody"), ("eerie", "other", "melody"),
    ("triumphant", "other", "melody"), ("melancholic", "other", "melody"),
    ("romantic", "other", "melody"), ("nostalgic", "other", "melody"),
    # Drums stem
    ("boom bap drums", "drums", "drums"), ("trap hi-hats", "drums", "drums"),
    ("hard-hitting drums", "drums", "drums"), ("live drums", "drums", "drums"),
    ("drill drums", "drums", "drums"), ("afrobeat percussion", "drums", "drums"),
    ("dancehall riddim", "drums", "drums"), ("four on the floor disco beat", "drums", "drums"),
    ("breakbeat", "drums", "drums"), ("snappy snare", "drums", "drums"), ("hand claps", "drums", "drums"),
    ("minimal sparse drums", "drums", "drums"), ("shuffling groove", "drums", "drums"),
    # Bass stem
    ("heavy 808", "bass", "bass"), ("sliding 808", "bass", "bass"), ("funk bass guitar", "bass", "bass"),
    ("deep sub bass", "bass", "bass"), ("walking bass", "bass", "bass"), ("synth bass", "bass", "bass"),
    # Full mix
    ("party", "mix", "vibe"), ("chill", "mix", "vibe"), ("late night", "mix", "vibe"),
    ("summer", "mix", "vibe"), ("sad", "mix", "vibe"), ("energetic", "mix", "vibe"),
    ("laid-back", "mix", "vibe"), ("emotional", "mix", "vibe"), ("uplifting", "mix", "vibe"),
    ("club banger", "mix", "vibe"), ("smooth", "mix", "vibe"), ("groovy", "mix", "vibe"),
    ("dark", "mix", "vibe"), ("hype", "mix", "vibe"), ("soulful", "mix", "vibe"), ("jazzy", "mix", "vibe"),
    ("gospel", "mix", "vibe"), ("old school 90s hip hop", "mix", "vibe"), ("70s soul", "mix", "vibe"),
    ("afrobeats", "mix", "vibe"), ("dancehall", "mix", "vibe"), ("uk drill", "mix", "vibe"),
]

# Generic words don't identify a descriptor on their own ("angelic sample" should hit "angelic").
GENERIC = {"vocals", "vocal", "sample", "drums", "bass", "music", "song", "sound", "singing", "voice", "rap",
           "beat", "a", "the", "and", "of", "on", "with", "flow", "chords"}


def prompt(label, stem):
    if stem == "mix":
        return f"a {label} song"
    return f"{label}"


def words(label):
    return [w for w in label.lower().replace("&", " & ").split() if w not in GENERIC] or [label.lower()]
