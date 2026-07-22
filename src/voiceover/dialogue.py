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

# "the old man", "his mother", "a voice" — at most two words after the
# determiner, so we never swallow the rest of the sentence.
_DESCRIPTOR = r"(?:[Tt]he|[Hh]is|[Hh]er|[Tt]heir|[Mm]y|[Oo]ur|[Aa]n?)\s+(?:[a-z]+\s+)?[a-z]+"

_PRONOUN = r"(?:[Hh]e|[Ss]he|[Tt]hey|I|[Ww]e|[Ii]t)"

# Wrapped in a group so the alternation never leaks into the pattern
# this is embedded in. Group 1: named/descriptor speaker; group 2: pronoun.
_SUBJECT = rf"(?:({_NAME}|{_DESCRIPTOR})|({_PRONOUN}))"

# After a quote: `said Elias`, `Elias said`, `the old man growled`.
_AFTER_VERB_SUBJ = re.compile(rf"^[\s,;—-]{{0,4}}(?:{_SPEECH_VERBS})\s+{_SUBJECT}")
_AFTER_SUBJ_VERB = re.compile(rf"^[\s,;—-]{{0,4}}{_SUBJECT}\s+(?:{_SPEECH_VERBS})\b")

# Before a quote: `Elias said,`, `said Elias:`, `the old man growled —`.
_BEFORE_SUBJ_VERB = re.compile(rf"{_SUBJECT}\s+(?:{_SPEECH_VERBS})[,:\s—-]{{0,4}}$")
_BEFORE_VERB_SUBJ = re.compile(rf"(?:{_SPEECH_VERBS})\s+{_SUBJECT}[,:\s—-]{{0,4}}$")

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
    Seven Eight Nine Ten First Second Third Last Next Every Each Some
    Any All Both Few Many Much More Most Other Another Such Same New
    Old Good Great Little Long Small Every Never Always Soon Suddenly
    Finally Perhaps Maybe Meanwhile Outside Inside Above Below Beyond
    Behind Around Across Against Among Between During Through Toward
    Well Oh Ah Hey Look Listen Wait Stop Come Go Right Left North
    South East West Monday Tuesday Wednesday Thursday Friday Saturday
    Sunday January February March April May June July August September
    October November December God Lord Heaven Hell Earth Sun Moon
""".split())


@dataclass
class Segment:
    speaker: str  # NARRATOR or a character name
    text: str

    @property
    def is_dialogue(self) -> bool:
        return self.speaker != NARRATOR


def _normalize_speaker(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip(" ,.;:—-")


def _match_attribution(patterns, text: str) -> str | None:
    """Return a speaker name, "" for a bare pronoun, or None for no match."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            name, pronoun = match.group(1), match.group(2)
            if name:
                return _normalize_speaker(name)
            if pronoun and pronoun.strip() == "I":
                return "I"  # first-person narrator-character
            return ""
    return None


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
                characters.add(_normalize_speaker(match.group(1)))

    # Proper nouns: capitalized at least twice, never seen lowercased.
    capitalized = Counter(_CAP_WORD.findall(outside_quotes))
    lowercased = set(_LOWER_WORD.findall(text))
    for word, count in capitalized.items():
        if count >= 2 and word.lower() not in lowercased and word not in _NAME_STOPWORDS:
            characters.add(word)
    return characters


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
            speaker = _match_attribution((_BEFORE_SUBJ_VERB, _BEFORE_VERB_SUBJ), head)
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

        quoted_text = (quote.group(1) or quote.group(2) or "").strip()
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
    segments: list[Segment] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for segment in _paragraph_segments(paragraph, context):
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
