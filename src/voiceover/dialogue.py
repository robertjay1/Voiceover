"""Detect speakers in prose so dialogue can be voiced per character.

The attribution problem: prose rarely announces the speaker up front.
Tags arrive after the quote ("Get down!" Elias shouted.), before it
(Elias said, "Get down!"), mid-quote ("Get down," he said, "now."),
as a bare pronoun ("he said" — the name only appears in surrounding
narration), or not at all — unattributed lines in a two-person exchange
alternate by convention.

Resolution strategy, paragraph by paragraph:

1. Find every quoted span and any explicit attribution tag, looking
   AFTER each quote first (the common case), then before it.
2. A named attribution anywhere in a paragraph claims that paragraph's
   untagged and pronoun-tagged quotes too — late attribution reaches
   back ("Wait." A pause. "It moved," said Mira.).
3. Otherwise, resolve from context, in order:
   a. a character freshly mentioned in narration since the last quote
      (who isn't the person who just spoke) — covers "Elias took the
      glass. 'It's a boat,' he said.";
   b. conversational alternation between the two most recent speakers;
   c. any recently mentioned character who isn't the last speaker;
   d. the last speaker (continuation).
4. Anything still unresolved stays with the narrator — the safe
   default, and exactly what a single-voice audiobook would do.

Character names are learned from attribution tags plus a proper-noun
scan of the narration (words that recur capitalized and never appear
lowercased), so a character introduced only by narration still exists
by the time a pronoun points at them.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

NARRATOR = "narrator"

_SPEECH_VERBS = (
    "said|asked|replied|answered|responded|retorted|shouted|yelled|screamed|"
    "whispered|muttered|murmured|mumbled|cried|called|exclaimed|snapped|"
    "growled|added|continued|began|agreed|admitted|observed|remarked|"
    "repeated|insisted|demanded|warned|laughed|sighed|hissed|barked|"
    "bellowed|stammered|urged|offered|suggested|noted|conceded|protested|"
    "interrupted|ventured|wondered|mused|declared|announced|explained|"
    "scoffed|sneered|drawled|quipped|groaned|moaned|pleaded|begged|"
    "whimpered|croaked|rasped|chuckled|breathed|echoed|finished|concluded|"
    "put in|cut in|went on|spoke up|pointed out|read aloud|read"
)

_TITLE = (
    r"(?:Mr|Mrs|Ms|Mx|Dr|Miss|Sir|Lady|Lord|Dame|Professor|Prof|Captain|"
    r"Sergeant|Major|Colonel|General|Admiral|Father|Mother|Brother|Sister|"
    r"Aunt|Uncle|Madame|Madam|Monsieur|Señor|Señora|King|Queen|"
    r"Prince|Princess|Doctor|Officer|Detective|Agent|Judge|Nurse|Coach)\.?"
)

# "Elias", "Mrs. Higgins", "Old Tom" — one or two capitalized words,
# optionally titled.
_NAME = rf"(?:{_TITLE}\s+)?[A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*)?"

# "the old man", "his mother", "Denise's mother", "a voice" — at most
# two words after the determiner/possessive, so we never swallow the
# rest of the sentence.
_DESCRIPTOR = (
    r"(?:(?:[Tt]he|[Hh]is|[Hh]er|[Tt]heir|[Mm]y|[Oo]ur|[Aa]n?"
    r"|[A-Z][\w’'-]*[’']s)\s+(?:[a-z]+\s+)?[a-z]+)"
)

_PRONOUN = r"(?:[Hh]e|[Ss]he|[Tt]hey|I|[Ww]e|[Ii]t)"

# Wrapped in a group so the alternation never leaks into the pattern
# this is embedded in. Group 1: named/descriptor speaker; group 2: pronoun.
# Descriptor is tried first so "Denise's mother" wins over the bare
# possessive "Denise's" that the name pattern would grab.
_SUBJECT = rf"(?:({_DESCRIPTOR}|{_NAME})|({_PRONOUN}))"

# After a quote: `said Elias`, `Elias said`, `the old man growled`.
_AFTER_VERB_SUBJ = re.compile(rf"^[\s,;—-]{{0,4}}(?:{_SPEECH_VERBS})\s+{_SUBJECT}")
_AFTER_SUBJ_VERB = re.compile(rf"^[\s,;—-]{{0,4}}{_SUBJECT}\s+(?:{_SPEECH_VERBS})\b")

# Before a quote: `Elias said,`, `said Elias:`, `the old man growled —`.
_BEFORE_SUBJ_VERB = re.compile(rf"{_SUBJECT}\s+(?:{_SPEECH_VERBS})[,:\s—-]{{0,4}}$")
_BEFORE_VERB_SUBJ = re.compile(rf"(?:{_SPEECH_VERBS})\s+{_SUBJECT}[,:\s—-]{{0,4}}$")

# Long-range subject: `James, who was tired and ten years into the habit,
# said, "..."` — a name opening the clause, the speech verb just before
# the quote, and no sentence boundary in between. The dummy () keeps the
# name/pronoun group numbering of the other patterns.
_BEFORE_FAR_SUBJ = re.compile(
    rf"(?:^|[.!?…]\s+)({_NAME})()[^.!?…“”\"]*?\s(?:{_SPEECH_VERBS})[,:\s—-]{{0,4}}$"
)

# Curly or straight double quotes.
_QUOTE = re.compile(r"“([^”]*)”|\"([^\"]*)\"")

_CAP_WORD = re.compile(r"\b[A-Z][a-z’'-]+\b")
_LOWER_WORD = re.compile(r"\b[a-z][a-z’'-]+\b")

# Capitalized words that are never character names.
_NAME_STOPWORDS = frozenset("""
    The A An And But Or Nor So Yet For If When While After Before Then
    There Here This That These Those He She It They We You I His Her
    Their Its My Our Your Not No Yes Now Once Only Even Still Just At
    By In On Of To From With As Out Up Down Over Under Into Onto What
    Who Whom Whose Why How Where Which Chapter Part Prologue Epilogue
    Mr Mrs Ms Dr Miss Sir Madam Lady Lord One Two Three Four Five Six
    Seven Eight Nine Ten First Second Third Fourth Fifth Sixth Seventh
    Eighth Ninth Tenth Last Next Every Each Some
    Any All Both Few Many Much More Most Other Another Such Same New
    Old Good Great Little Long Small Every Never Always Soon Suddenly
    Finally Perhaps Maybe Meanwhile Outside Inside Above Below Beyond
    Behind Around Across Against Among Between During Through Toward
    Well Oh Ah Hey Look Listen Wait Stop Come Go Right Left North
    South East West Monday Tuesday Wednesday Thursday Friday Saturday
    Sunday January February March April May June July August September
    October November December God Lord Heaven Hell Earth Sun Moon
    Nobody Someone Somebody Everyone Everybody Anyone Anybody Nothing
    Something Everything
""".split())


@dataclass
class Segment:
    speaker: str  # NARRATOR or a character name
    text: str

    @property
    def is_dialogue(self) -> bool:
        return self.speaker != NARRATOR


def tidy_speech(text: str) -> str:
    """Give an extracted line sentence-final punctuation so a neural
    voice reads it with a complete intonation contour instead of a
    hanging one.

    A quote pulled out of "Fine," said Ray. arrives as "Fine," — a
    trailing comma the engine intones as unfinished, then the audio
    stops dead. Promoting that comma (or a bare fragment with no mark)
    to a full stop is the single biggest prosody win for dialogue.
    Interruptions and trailing-off (— … -) are intentional and kept.
    """
    text = " ".join(text.split())
    if not text:
        return text
    # Ignore a trailing closing quote/bracket when judging the ending.
    stripped = text.rstrip("\"'”’)]}")
    if not stripped:
        return text
    last = stripped[-1]
    if last in ",;:":
        return stripped[:-1].rstrip() + "."
    if last in ".!?…—–-":
        return text
    return stripped + "."


# Words a descriptor should never end on — regex overreach like
# "a voice at [the door]" or "a [nurse] had [seen]" gets trimmed back.
_TRAILING_JUNK = frozenset("""
    at in on by of to from with near into onto over under and or but
    had has have was were is are be been did does would could should
    who which that as when while then there
""".split())


def _normalize_speaker(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw).strip(" ,.;:—-")
    tokens = name.split()
    while tokens and tokens[-1].lower() in _TRAILING_JUNK:
        tokens.pop()
    return " ".join(tokens)


# Sentence-initial pronouns are capitalized and would otherwise pass as
# names ("He said" -> speaker "He").
_PRONOUN_WORDS = frozenset(["he", "she", "they", "we", "it", "you", "i"])

# "Nobody answered." / "Someone called out." — narration, not attribution.
_NONSPEAKERS = frozenset([
    "nobody", "no one", "someone", "somebody", "everyone", "everybody",
    "anyone", "anybody", "nothing", "something", "everything",
])


def _match_attribution(patterns, text: str) -> str | None:
    """Return a speaker name, "" for a bare pronoun, or None for no match."""
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        name, pronoun = match.group(1), match.group(2)
        if name:
            name = _normalize_speaker(name)
            lowered = name.lower()
            if not name or lowered in _NONSPEAKERS:
                continue  # not an attribution at all
            if lowered in ("a", "an", "the", "his", "her", "their", "my", "our"):
                continue  # descriptor reduced to a bare determiner
            if name in _NAME_STOPWORDS:
                continue  # "And Gary said" must not attribute to "And"
            if lowered in _PRONOUN_WORDS:
                pronoun, name = name, None
            else:
                return name
        if pronoun and pronoun.strip().lower() == "i":
            return "I"  # first-person narrator-character
        return ""
    return None


def _strip_possessive(word: str) -> str:
    """'Ray’s' -> 'Ray' — a possessive mention still refers to the person."""
    return re.sub(r"[’']s$", "", word)


# Leading words that vary between mentions of the same person.
_ALIAS_TITLE_WORDS = frozenset("""
    mr mrs ms mx dr miss sir lady lord dame professor prof captain
    sergeant major colonel general admiral father mother brother sister
    aunt uncle madame madam monsieur king queen prince princess doctor
    officer detective agent judge nurse coach
    dc ds di dci pc wpc sgt insp supt const
""".split())


def _title_stripped(name: str) -> str:
    tokens = name.split()
    while tokens and tokens[0].rstrip(".").lower() in _ALIAS_TITLE_WORDS:
        tokens = tokens[1:]
    return " ".join(tokens)


def merge_aliases(names: set[str]) -> dict[str, str]:
    """Map each speaker name to a canonical form, so 'DC Rehman' and
    'Rehman', or 'Brent' and 'Brent Kowalski', share one voice.

    Two rules: titles are noise ('Dr Rob' == 'Rob'), and a lone name
    that appears as a token of exactly one longer name is that person
    ('Brent' == 'Brent Kowalski'). Descriptors ('the old man') are
    left alone.
    """
    canonical: dict[str, str] = {}
    by_base: dict[str, list[str]] = {}
    for name in names:
        if name == NARRATOR or (name and name[0].islower()):
            canonical[name] = name
            continue
        base = _title_stripped(name) or name
        by_base.setdefault(base.lower(), []).append(name)

    for group in by_base.values():
        target = min(group, key=len)  # "Rehman" over "DC Rehman"
        for name in group:
            canonical[name] = target

    # Lone first/last names fold into a unique longer match.
    values = set(canonical.values())
    for short in [v for v in values if " " not in v and v[:1].isupper()]:
        matches = [
            v for v in values
            if " " in v and short in _title_stripped(v).split()
        ]
        if len(matches) == 1:
            for name, canon in canonical.items():
                if canon == short:
                    canonical[name] = matches[0]
    return canonical


def _collect_characters(text: str) -> set[str]:
    """Names learned from attribution tags plus recurring proper nouns."""
    characters: set[str] = set()

    # Every explicitly tagged speaker, anywhere in the text.
    outside_quotes = _QUOTE.sub(" ", text)
    for pattern in (
        re.compile(rf"(?:{_SPEECH_VERBS})\s+{_SUBJECT}"),
        re.compile(rf"{_SUBJECT}\s+(?:{_SPEECH_VERBS})\b"),
    ):
        for match in pattern.finditer(outside_quotes):
            if match.group(1):
                name = _normalize_speaker(match.group(1))
                if name.lower() in _NONSPEAKERS or name in _NAME_STOPWORDS:
                    continue
                characters.add(name)

    # Proper nouns: capitalized at least twice, never seen lowercased.
    capitalized = Counter(
        _strip_possessive(w) for w in _CAP_WORD.findall(outside_quotes)
    )
    lowercased = set(_LOWER_WORD.findall(text))
    for word, count in capitalized.items():
        if count >= 2 and word.lower() not in lowercased and word not in _NAME_STOPWORDS:
            if not _looks_like_place(word, outside_quotes):
                characters.add(word)
    return characters


_PLACE_PREPOSITIONS = (
    "in|at|to|from|near|into|onto|through|across|toward|towards|around"
    "|outside|inside|behind|beyond|along|past|down|up|off|via|of"
)


def _looks_like_place(word: str, text: str) -> bool:
    """People act; places get gone to. A proper noun whose occurrences
    mostly follow a preposition ('in Kamloops', 'at the Tramways') is a
    location and must never soak up unattributed dialogue."""
    occurrences = re.findall(
        rf"(\b(?:{_PLACE_PREPOSITIONS})\s+(?:the\s+)?)?{re.escape(word)}\b", text
    )
    if not occurrences:
        return False
    after_preposition = sum(1 for prefix in occurrences if prefix)
    return after_preposition / len(occurrences) > 0.5


class _Context:
    """Conversation state: recent speakers and recent narration mentions."""

    def __init__(self, characters: set[str]) -> None:
        self.characters = characters
        self.recent: list[str] = []  # last two distinct speakers, most recent last
        self.mentions: list[str] = []  # narration mentions, most recent last
        self.fresh: list[str] = []  # mentions since the previous quote

    def note_speaker(self, speaker: str) -> None:
        if speaker in (NARRATOR, ""):
            return
        if speaker in self.recent:
            self.recent.remove(speaker)
        self.recent.append(speaker)
        del self.recent[:-2]
        self.fresh = []

    def scan_narration(self, narration: str) -> None:
        for word in _CAP_WORD.findall(narration):
            word = _strip_possessive(word)
            if word in self.characters:
                for bucket in (self.mentions, self.fresh):
                    if word in bucket:
                        bucket.remove(word)
                    bucket.append(word)
        del self.mentions[:-6]

    def last_speaker(self) -> str | None:
        return self.recent[-1] if self.recent else None

    def resolve_unattributed(self) -> str | None:
        last = self.last_speaker()
        # a) someone narration just pointed at (who didn't just speak)
        for name in reversed(self.fresh):
            if name != last:
                return name
        # b) two-person alternation
        if len(self.recent) == 2:
            return self.recent[0]
        # c) any recent mention who didn't just speak
        for name in reversed(self.mentions):
            if name != last:
                return name
        # d) continuation by the same speaker
        return last


def _paragraph_segments(paragraph: str, context: _Context) -> list[Segment]:
    quotes = list(_QUOTE.finditer(paragraph))
    if not quotes:
        context.scan_narration(paragraph)
        return [Segment(NARRATOR, paragraph)]

    # Pass 1: explicit attribution per quote — tail (after) wins over head.
    attributions: list[str | None] = []
    for index, quote in enumerate(quotes):
        tail_end = quotes[index + 1].start() if index + 1 < len(quotes) else len(paragraph)
        tail = paragraph[quote.end():tail_end]
        head_start = quotes[index - 1].end() if index > 0 else 0
        head = paragraph[head_start:quote.start()]

        speaker = _match_attribution((_AFTER_VERB_SUBJ, _AFTER_SUBJ_VERB), tail)
        if speaker is None:
            speaker = _match_attribution(
                (_BEFORE_SUBJ_VERB, _BEFORE_VERB_SUBJ, _BEFORE_FAR_SUBJ), head
            )
        attributions.append(speaker)

    # Pass 2: a named attribution anywhere in the paragraph claims its
    # untagged/pronoun-tagged quotes — late attribution reaches back.
    named = [a for a in attributions if a]
    paragraph_speaker = named[0] if named else None

    segments: list[Segment] = []
    cursor = 0
    resolved_for_paragraph: str | None = None
    for quote, attribution in zip(quotes, attributions):
        narration = paragraph[cursor:quote.start()].strip()
        if narration:
            context.scan_narration(narration)
            segments.append(Segment(NARRATOR, narration))

        if attribution:
            speaker = attribution
        elif paragraph_speaker:
            speaker = paragraph_speaker
        elif resolved_for_paragraph:
            # Untagged quotes within one paragraph share a speaker.
            speaker = resolved_for_paragraph
        else:
            speaker = context.resolve_unattributed() or NARRATOR
        resolved_for_paragraph = resolved_for_paragraph or speaker

        quoted_text = tidy_speech(quote.group(1) or quote.group(2) or "")
        if quoted_text:
            segments.append(Segment(speaker, quoted_text))
            context.note_speaker(speaker)
        cursor = quote.end()

    trailing = paragraph[cursor:].strip()
    if trailing:
        context.scan_narration(trailing)
        segments.append(Segment(NARRATOR, trailing))
    return segments


def segment_dialogue(text: str) -> list[Segment]:
    """Split chapter text into narrator/character segments.

    Consecutive segments with the same speaker are merged so the
    synthesizer gets fewer, longer, more natural runs.
    """
    context = _Context(_collect_characters(text))
    raw: list[Segment] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        raw.extend(_paragraph_segments(paragraph, context))

    # Fold aliases ('DC Rehman' -> 'Rehman') before merging neighbors.
    canonical = merge_aliases({s.speaker for s in raw})
    segments: list[Segment] = []
    for segment in raw:
        segment.speaker = canonical.get(segment.speaker, segment.speaker)
        if segments and segments[-1].speaker == segment.speaker:
            joiner = "\n\n" if segments[-1].text.endswith((".", "!", "?", "…")) else " "
            segments[-1].text = f"{segments[-1].text}{joiner}{segment.text}"
        else:
            segments.append(segment)
    return segments


def speaker_stats(text: str) -> dict[str, int]:
    """Word counts per speaker — used by 'voiceover cast' to build a cast list."""
    counts: dict[str, int] = {}
    for segment in segment_dialogue(text):
        counts[segment.speaker] = counts.get(segment.speaker, 0) + len(segment.text.split())
    return counts
