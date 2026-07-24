"""Automatic casting: infer each character's gender/age/accent from the
prose, then assign a distinct, natural, trait-matched voice.

Two design choices keep the result human-sounding:

* Distinctiveness comes from using different *base* voices, not from
  pitch-shifting one voice — big pitch shifts make edge voices sound
  electronic. Auto-casting draws from ~40 real voices across accents and
  only nudges rate/pitch slightly when it runs out of fresh bases.
* Accent is assigned only where the text gives an explicit cue
  ("began life in the West Indies", "local boy, said the accent"); a
  name alone never decides an accent.

Choices are recorded in the voice bank keyed by character, so recurring
series characters keep one voice across every book.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .dialogue import NARRATOR
from .voicebank import VoiceProfile

# --- Voice catalogue -------------------------------------------------------
# Each voice: (shortname, gender, region, timbre). timbre is a rough hint:
# "young" / "neutral" / "mature". Only voices reliably present in edge-tts.

VOICES: list[tuple[str, str, str, str]] = [
    # British
    ("en-GB-RyanNeural", "male", "gb", "neutral"),
    ("en-GB-ThomasNeural", "male", "gb", "mature"),
    ("en-GB-SoniaNeural", "female", "gb", "neutral"),
    ("en-GB-LibbyNeural", "female", "gb", "young"),
    ("en-GB-MaisieNeural", "female", "gb", "child"),
    # Irish
    ("en-IE-ConnorNeural", "male", "ie", "neutral"),
    ("en-IE-EmilyNeural", "female", "ie", "neutral"),
    # Australian / NZ
    ("en-AU-WilliamNeural", "male", "au", "neutral"),
    ("en-AU-NatashaNeural", "female", "au", "neutral"),
    ("en-NZ-MitchellNeural", "male", "nz", "neutral"),
    ("en-NZ-MollyNeural", "female", "nz", "neutral"),
    # Canadian
    ("en-CA-LiamNeural", "male", "ca", "neutral"),
    ("en-CA-ClaraNeural", "female", "ca", "neutral"),
    # US
    ("en-US-AndrewMultilingualNeural", "male", "us", "neutral"),
    ("en-US-BrianMultilingualNeural", "male", "us", "mature"),
    ("en-US-ChristopherNeural", "male", "us", "mature"),
    ("en-US-EricNeural", "male", "us", "neutral"),
    ("en-US-RogerNeural", "male", "us", "neutral"),
    ("en-US-GuyNeural", "male", "us", "neutral"),
    ("en-US-AvaMultilingualNeural", "female", "us", "neutral"),
    ("en-US-EmmaMultilingualNeural", "female", "us", "young"),
    ("en-US-JennyNeural", "female", "us", "neutral"),
    ("en-US-AriaNeural", "female", "us", "neutral"),
    ("en-US-MichelleNeural", "female", "us", "mature"),
    # African
    ("en-ZA-LukeNeural", "male", "za", "neutral"),
    ("en-ZA-LeahNeural", "female", "za", "neutral"),
    ("en-KE-ChilembaNeural", "male", "ke", "mature"),
    ("en-KE-AsiliaNeural", "female", "ke", "neutral"),
    ("en-NG-AbeoNeural", "male", "ng", "mature"),
    ("en-NG-EzinneNeural", "female", "ng", "neutral"),
    # South Asian / SE Asian
    ("en-IN-PrabhatNeural", "male", "in", "neutral"),
    ("en-IN-NeerjaNeural", "female", "in", "neutral"),
    ("en-HK-SamNeural", "male", "hk", "neutral"),
    ("en-HK-YanNeural", "female", "hk", "neutral"),
    ("en-SG-WayneNeural", "male", "sg", "neutral"),
    ("en-SG-LunaNeural", "female", "sg", "neutral"),
    ("en-PH-JamesNeural", "male", "ph", "neutral"),
    ("en-PH-RosaNeural", "female", "ph", "neutral"),
]

# Accent-cue phrases -> region code. West Indies has no edge voice; we
# approximate with a warm African-accented voice and flag it.
ACCENT_CUES: list[tuple[str, str]] = [
    (r"west ind|caribbean|jamaic|trinidad|barbad|guyan|antigua|tobago", "za"),
    (r"nigeri|lagos|yoruba|igbo", "ng"),
    (r"kenya|nairobi", "ke"),
    (r"south afric|johannesburg|cape town|afrikaan", "za"),
    (r"\bindian?\b|delhi|mumbai|punjab|gujarat|tamil", "in"),
    (r"irish|ireland|dublin|cork\b", "ie"),
    (r"australian?|sydney|melbourne|brisbane", "au"),
    (r"new zealand|kiwi|auckland", "nz"),
    (r"canadian?|toronto|vancouver|\blocal boy\b", "ca"),
    (r"american?|texan|new york|california|yankee", "us"),
    (r"filipino|manila|philippine", "ph"),
    (r"singapore", "sg"),
    (r"hong kong|cantonese", "hk"),
]

# First-name gender lexicon — the most reliable gender signal in fiction,
# since pronoun proximity fails when a protagonist of one gender is in
# nearly every scene. Surnames/unknowns fall through to pronoun analysis.
_FEMALE_NAMES = set("""
alice amanda amy anna anne annie barbara beatrice bea betty carol carole
caroline catherine cathy charlotte chris christine claire clara dawn debbie
deborah denise diana donna dorothy eleanor elizabeth ella ellen emily emma
esther eve evelyn fiona florence gill gillian grace hannah harriet heather
helen holly imani irene isabel isabella jane janet jean jennifer jenny jess
jessica jill joan joanna josephine joy judith judy julia julie june karen
kate katherine kathleen kathy katie kay kayleigh kelly kelsee kelsey kim laura
leah libby linda lisa lucy lynn madison maggie margaret marjorie martha mary
maureen megan melanie michelle molly nancy naomi narelle natasha nicola nicole
noeline olivia pam pamela patricia paula pauline penny philippa phoebe priya
priyanka rachel rebecca rita roberta rose rosa roxanne ruth sally samantha
sandra sarah sharon sheila sonia sophie stella susan tanya teresa theresa tina
tracy vera victoria wendy yan zoe asilia clara ezinne luna neerja
""".split())
_MALE_NAMES = set("""
aaron adam adrian alan albert alex alexander alfred andrew anthony arthur ash
barry ben benjamin bernard bill bob brandon brent brian bruce carl cedric
charles chris christopher clark clive cody colin connor craig daniel danny
dave david dax dean dennis derek don donald douglas duncan eddie edward elimu
emmanuel eric ernest frank fred gary gavin geoff geoffrey george gordon graham
greg harold harry henry herbert horace howard ian jack jacob james jason
jeff jeffrey jeremy jim joe joel john johnny jonathan joseph josh joshua julian
keith ken kenneth kevin larry lawrence lee leo leonard liam louis luke marcus
mark martin marty matthew maurice max michael mike miklos nathan neil nicholas
nigel norman oliver oscar patrick paul pete peter philip phil prabhat ralph
ray raymond richard rob robert roger ron ronald roy russell ryan sam
samuel scott sean sidney simon stan stanley stephen steve steven stuart ted
terry thomas tim timothy toby tom tony trevor victor vincent wade walter wayne
william abeo chilemba prabhat sam wayne
""".split())

_MALE_TITLES = re.compile(r"\b(mr|sir|lord|father|uncle|king|prince|master|monsieur)\b\.?", re.I)
_FEMALE_TITLES = re.compile(
    r"\b(mrs|ms|miss|lady|dame|mother|aunt|queen|princess|madame|madam)\b\.?", re.I
)
_MALE_PRON = re.compile(r"\b(he|him|his|himself)\b", re.I)
_FEMALE_PRON = re.compile(r"\b(she|her|hers|herself)\b", re.I)

# Age cues kept conservative — bare "old"/"young" appear in idioms
# ("old friend", "young man" said of anyone), so require specific signals.
_OLD_CUES = re.compile(
    r"\b(elderly|aged|retire[drs]?|retiring|retirement|pension\w*|"
    r"grand(?:father|mother|ma|pa|dad)|widow\w*|frail|stooped|wizened|"
    r"sixty|seventy|eighty|ninety|sixty-\w+|seventy-\w+|in his sixties|"
    r"in her sixties|in his seventies|in her seventies|decades of)\b",
    re.I,
)
_YOUNG_CUES = re.compile(
    r"\b(teenage\w*|schoolgirl|schoolboy|trainee|apprentice|toddler|"
    r"nineteen|twenty|twenty-\w+|twenties|graduate|undergraduate|student)\b",
    re.I,
)
_CHILD_CUES = re.compile(r"\b(child|toddler|infant|little (?:boy|girl)|year-old)\b", re.I)


@dataclass
class Traits:
    gender: str | None = None  # "male" / "female" / None
    age: str = "adult"  # "child" / "young" / "adult" / "older"
    region: str | None = None  # accent code, or None for default
    accent_explicit: bool = False
    note: str = ""


def _windows(name: str, text: str, radius: int = 90) -> list[str]:
    spans = []
    for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text):
        spans.append(text[max(0, m.start() - 25): m.end() + radius])
    return spans


def _first_name(name: str) -> str:
    tokens = _title_free(name).split()
    return tokens[0].lower() if tokens else ""


def _title_free(name: str) -> str:
    return re.sub(r"\b(?:mr|mrs|ms|mx|dr|miss|sir|lady|lord|prof|professor|dc|ds|"
                  r"di|dci|pc|sgt|detective|constable|sergeant)\b\.?", " ", name, flags=re.I).strip()


def _pronoun_tally(name: str, text: str, name_set: set[str], maxdist: int) -> tuple[int, int]:
    """Credit each gendered pronoun to the nearest name before it, within
    the same sentence and maxdist characters."""
    names = sorted(name_set, key=len, reverse=True)
    if not names:
        return (0, 0)
    token = re.compile(
        r"(?P<name>(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?!\w))"
        r"|(?P<he>\b(?:he|him|his|himself)\b)"
        r"|(?P<she>\b(?:she|her|hers|herself)\b)"
        r"|(?P<brk>[.!?\n])",
        re.I,
    )
    male = female = 0
    current, pos = None, 0
    for m in token.finditer(text):
        if m.lastgroup == "brk":
            current = None
        elif m.group("name"):
            current, pos = m.group("name"), m.end()
        elif current == name and m.start() - pos < maxdist:
            if m.lastgroup == "he":
                male += 1
            else:
                female += 1
    return male, female


def infer_gender(name: str, text: str, name_set: set[str]) -> str | None:
    """Gender from, in order: honorific, first-name lexicon, then pronouns
    credited to the nearest preceding name (tight window first)."""
    esc = re.escape(name)
    male_titled = len(re.findall(
        rf"\b(?:Mr|Sir|Lord|Father|Uncle|King|Prince|Master|Monsieur)\.?\s+{esc}\b", text))
    female_titled = len(re.findall(
        rf"\b(?:Mrs|Ms|Miss|Lady|Dame|Mother|Aunt|Queen|Princess|Madame|Madam)\.?\s+{esc}\b",
        text))
    if male_titled > female_titled:
        return "male"
    if female_titled > male_titled:
        return "female"

    first = _first_name(name)
    if first in _FEMALE_NAMES and first not in _MALE_NAMES:
        return "female"
    if first in _MALE_NAMES and first not in _FEMALE_NAMES:
        return "male"

    for maxdist in (45, 120):
        male, female = _pronoun_tally(name, text, name_set, maxdist)
        if male + female >= 2 and (male >= female * 2 or female >= male * 2):
            return "male" if male > female else "female"
    male, female = _pronoun_tally(name, text, name_set, 120)
    if male != female:
        return "male" if male > female else "female"
    return None


def infer_age(name: str, text: str) -> str:
    old = young = child = 0
    for window in _windows(name, text, radius=70):
        old += len(_OLD_CUES.findall(window))
        young += len(_YOUNG_CUES.findall(window))
        child += len(_CHILD_CUES.findall(window))
    if child >= 1 and child >= old:
        return "child"
    if old > young:
        return "older"
    if young > old:
        return "young"
    return "adult"


# Setting markers — where a scene is set, used as a soft accent default
# for characters with no personal accent cue (handles anthologies whose
# cases move between countries).
SETTING_MARKERS: list[tuple[str, str]] = [
    (r"ontario|kamloops|fraser|rcmp|\btim horton|toronto|vancouver|"
     r"\bloonie|\btoonie|british columbia|\bbc\b|mountie", "ca"),
    (r"sydney|melbourne|brisbane|queensland|\bnsw\b|outback", "au"),
]


def infer_accent(
    name: str, text: str, default_region: str = "gb"
) -> tuple[str | None, bool, str]:
    """Return (region, explicit, note). Explicit personal cues win; else a
    soft default from the setting of the character's scenes."""
    joined = " ".join(_windows(name, text, radius=120)).lower()
    for pattern, region in ACCENT_CUES:
        if re.search(pattern, joined):
            note = ""
            if region == "za" and re.search(r"west ind|caribbean|jamaic|trinidad", joined):
                note = "Caribbean cue — no Caribbean TTS voice; approximated with a warm African voice."
            return region, True, note

    # No personal cue: default to the dominant setting of this character's
    # scenes (wider windows), so a UK case in a mostly-Canadian book still
    # reads British.
    context = " ".join(_windows(name, text, radius=400)).lower()
    counts = Counter()
    for pattern, region in SETTING_MARKERS:
        counts[region] += len(re.findall(pattern, context))
    if counts and max(counts.values()) >= 2:
        return counts.most_common(1)[0][0], False, ""
    return default_region, False, ""


def infer_traits(name: str, text: str, name_set: set[str], default_region: str = "gb") -> Traits:
    if name.lower().startswith(("the ", "a ", "an ")):
        # Descriptor like "the agency lad" — glean what we can from the phrase.
        gender = "male" if re.search(r"\b(lad|man|boy|gent|husband|father|guy|sir)\b", name, re.I) else \
                 "female" if re.search(r"\b(lass|woman|girl|lady|wife|mother|nurse)\b", name, re.I) else None
        age = "young" if re.search(r"\b(lad|boy|girl|kid|young)\b", name, re.I) else \
              "older" if re.search(r"\b(old|elderly)\b", name, re.I) else "adult"
        region, explicit, note = infer_accent(name, text, default_region)
        return Traits(gender=gender, age=age, region=region, accent_explicit=explicit, note=note)
    gender = infer_gender(name, text, name_set)
    age = infer_age(name, text)
    region, explicit, note = infer_accent(name, text, default_region)
    return Traits(gender=gender, age=age, region=region, accent_explicit=explicit, note=note)


def group_full_name_aliases(names: list[str], text: str) -> dict[str, str]:
    """Link a first name and a surname that name the same person, using
    'First Last' bigrams in the prose (Cody + Dufresne -> one voice).

    Returns each name mapped to a canonical (longest) label.
    """
    singles = [n for n in names if " " not in n and n[:1].isupper()]
    canon = {n: n for n in names}
    for a in singles:
        for b in singles:
            if a is b or a == b:
                continue
            # "Cody Dufresne" appears in text -> a is first, b is surname.
            if re.search(rf"(?<!\w){re.escape(a)}\s+{re.escape(b)}(?!\w)", text):
                # Canonical = the surname (what the narration usually uses
                # for adults), but only merge when the pairing is unique.
                target = f"{a} {b}"
                # Prefer an existing detected full name if present, else surname.
                canon[a] = canon[b] = b if _mostly_surname(b, text) else a
    return canon


def _mostly_surname(word: str, text: str) -> bool:
    titled = len(re.findall(rf"\b(?:Mr|Mrs|Ms|Dr|Miss|Sir)\.?\s+{re.escape(word)}\b", text))
    return titled > 0


REGION_LABEL = {
    "gb": "British", "ie": "Irish", "au": "Australian", "nz": "NZ",
    "ca": "Canadian", "us": "American", "za": "S.African", "ke": "Kenyan",
    "ng": "Nigerian", "in": "Indian", "hk": "HK", "sg": "Singapore", "ph": "Filipino",
}


@dataclass
class CastEntry:
    speaker: str
    canonical: str
    traits: Traits
    profile: VoiceProfile
    reused: bool  # already in the bank from a previous book


def autocast(
    speakers: list[str],
    text: str,
    *,
    bank: dict[str, VoiceProfile],
    narrator: VoiceProfile,
    default_region: str = "gb",
) -> list[CastEntry]:
    """Assign each speaker a distinct, trait-matched voice.

    Recurring characters already in `bank` keep their voice; the rest are
    allocated fresh voices that don't collide with those or each other.
    Bank keys are slugified character names, so a second book reuses the
    first book's cast automatically.
    """
    from .voicebank import slugify

    name_set = {s for s in speakers if not s.lower().startswith(("the ", "a ", "an "))}
    alias_map = group_full_name_aliases(speakers, text)

    # Voices already committed (narrator + anything in the bank) are reserved.
    reserved = {narrator.voice} | {p.voice for p in bank.values() if p.voice}
    allocator = VoiceAllocator(default_region, reserved=reserved)

    # Order by prominence (most dialogue first) so leads get the cleanest
    # matching voices before the pool thins.
    entries: list[CastEntry] = []
    seen_canonical: dict[str, CastEntry] = {}
    for speaker in speakers:
        canonical = alias_map.get(speaker, speaker)
        if canonical in seen_canonical:
            base = seen_canonical[canonical]
            entries.append(CastEntry(speaker, canonical, base.traits, base.profile, base.reused))
            continue

        slug = slugify(canonical)
        if slug in bank:
            entry = CastEntry(speaker, canonical, Traits(), bank[slug], reused=True)
        else:
            traits = infer_traits(canonical, text, name_set, default_region)
            profile = allocator.allocate(traits)
            bank[slug] = profile
            entry = CastEntry(speaker, canonical, traits, profile, reused=False)
        seen_canonical[canonical] = entry
        entries.append(entry)
    return entries


# Native-English accent chains: a character with no explicit accent cue
# may borrow a neighbouring English accent for distinctiveness, but never
# a far one (African/South-Asian/SE-Asian) — those are reserved for an
# explicit textual cue, so nobody is mis-accented by accident.
_NEIGHBOURS = {
    "gb": ["gb", "ie", "au", "nz", "ca", "us"],
    "ie": ["ie", "gb", "au", "nz", "ca", "us"],
    "ca": ["ca", "us", "gb", "ie", "au", "nz"],
    "us": ["us", "ca", "gb", "ie", "au", "nz"],
    "au": ["au", "nz", "gb", "ie", "ca", "us"],
    "nz": ["nz", "au", "gb", "ie", "ca", "us"],
}
# Modest, natural-sounding variation steps (rate first — rate changes read
# as pace, not the electronic artefact big pitch shifts cause).
_RATE_STEPS = [1.0, 0.95, 1.05, 0.92, 1.08, 0.97, 1.03, 0.9, 1.1]
_PITCH_STEPS = [1.0, 0.97, 1.03, 0.95, 1.05]


class VoiceAllocator:
    """Hands out distinct voices matched to traits, keeping accents right."""

    def __init__(self, default_region: str, reserved: set[str] | None = None):
        self.default_region = default_region
        self.taken: set[tuple] = set()  # (voice, rate, pitch) already issued
        for v in (reserved or set()):
            self.taken.add((v, 1.0, 1.0))
        self._base_voices: set[str] = {v for v, *_ in VOICES}
        self._reserved_bases = set(reserved or set())
        self._by_gender_region: dict[tuple, list] = defaultdict(list)
        for name, gender, region, timbre in VOICES:
            self._by_gender_region[(gender, region)].append((name, timbre))

    def _bases(self, gender: str, region: str, explicit: bool, age: str) -> list[str]:
        want = {"older": "mature", "young": "young", "child": "child"}.get(age)
        # Explicit accent → that region only. Otherwise walk native-English
        # neighbours. Far accents are only reachable via an explicit region.
        chain = [region] if explicit else _NEIGHBOURS.get(region, [region])
        if explicit and region not in _NEIGHBOURS:
            chain = [region]  # a far accent explicitly requested
        ordered: list[str] = []
        for reg in chain:
            pool = list(self._by_gender_region.get((gender, reg), []))
            # child-timbre voices only for child characters
            pool = [(n, t) for n, t in pool if t != "child" or age == "child"]
            pool.sort(key=lambda nt: 0 if want and nt[1] == want else
                                     1 if nt[1] == "neutral" else 2)
            ordered.extend(n for n, _ in pool)
        return ordered

    def allocate(self, traits: Traits) -> VoiceProfile:
        genders = [traits.gender] if traits.gender else ["female", "male"]
        region = traits.region or self.default_region
        age_rate = {"older": 0.93, "young": 1.05}.get(traits.age, 1.0)

        bases: list[str] = []
        for g in genders:
            bases += [b for b in self._bases(g, region, traits.accent_explicit, traits.age)
                      if b not in bases]

        # 1) a fresh base voice at its natural rate (age-nudged)
        for base in bases:
            key = (base, age_rate, 1.0)
            if base not in self._reserved_bases and key not in self.taken and \
                    (base, 1.0, 1.0) not in self.taken:
                self.taken.add(key)
                return VoiceProfile(engine="edge", voice=base, rate=age_rate)

        # 2) same-accent variants: step rate, then a gentle pitch nudge
        for pitch in _PITCH_STEPS:
            for rate_step in _RATE_STEPS:
                rate = round(age_rate * rate_step, 3)
                for base in bases:
                    key = (base, rate, pitch)
                    if key not in self.taken:
                        self.taken.add(key)
                        return VoiceProfile(engine="edge", voice=base, rate=rate,
                                            pitch=pitch if pitch != 1.0 else 1.0)

        # 3) exhausted (huge cast) — fall back to a rate-jittered narrator-ish voice
        base = bases[0] if bases else "en-GB-RyanNeural"
        rate = round(age_rate * (0.85 + 0.01 * (len(self.taken) % 20)), 3)
        self.taken.add((base, rate, 1.0))
        return VoiceProfile(engine="edge", voice=base, rate=rate)
