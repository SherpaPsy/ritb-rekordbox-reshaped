"""Parse a OneNote setlist page's HTML into (title, artist(s), label) tracks.

Page structure, reverse-engineered from "John's Notebook" (see memory/
onenote-graph-integration): each track is three consecutive non-blank <p>
lines - title, artist(s), label - with a "===...===" divider <p> roughly
every 5 tracks marking an hour block, and sometimes a "Set Starter:" label
line marking the opening track. Multi-artist tracks are comma-separated on
the artist line, e.g. "Wayward Brothers, Arina Alba".

Formatting drifted over the years this has been hand-maintained: some pages
carry a leading cover-image caption block before the real content starts,
in several different forms ("Art: <url>", "Cover:" then the url on its own
line, "Title: <custom name>" then the url, or just a bare custom title
immediately followed by the url) - see _strip_leading_header. Page titles
also switched convention partway through, from "Month Day, Year[ Set]" in
2021 to "yyyy.mm.dd[ extra text]" from 2022 onward (matching the same style
Rekordbox playlist names already use - see core/rekordbox_extractor.py).

The track block layout itself also drifted, in two stages: the original
3-line convention (title, artist, plain label name) gave way around 2024 to
a 3-line variant where the label line is the literal "[Label Year]" bracket
tag, before collapsing further around 2026 into a 2-line convention where
that same bracket tag is appended directly onto the title line instead -
i.e. the exact [Label]/[Label Year] convention core.rekordbox_extractor
already parses back out of Rekordbox titles. See _group_as_pairs/
_group_as_triplets and their reuse of parse_title/LABEL_TAG_PATTERN from
that module.
"""
import datetime
import re
from html.parser import HTMLParser

from core.rekordbox_extractor import parse_title

# A bare "=====...=====" hour-block divider, or a "Set Starter(s):"/"(set
# starter)" label - both mark structure, not track content, wherever they
# appear in a page.
MARKER_LINE_PATTERN = re.compile(r"^\(?(=+|set\s*starters?\s*:?)\)?\s*$", re.I)

URL_PATTERN = re.compile(r"https?://", re.I)
HEADER_LABEL_PATTERN = re.compile(r"^(art|cover|title)\s*:", re.I)

# A label line that's just "[Label]" or "[Label Year]" and nothing else - the
# 2024-era transitional convention (see module docstring), same shape as the
# trailing tag core.rekordbox_extractor.LABEL_TAG_PATTERN matches, just
# anchored to the whole line since here it's already isolated onto one.
WRAPPED_LABEL_PATTERN = re.compile(r"^\[([^\[\]]+?)(?:\s+\d{4})?\]$")

DOTTED_DATE_PATTERN = re.compile(r"^(\d{2,4})\.(\d{1,2})\.(\d{1,2})\b")
WORDY_DATE_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*/\s*\d{1,2}(?:st|nd|rd|th)?)*,?\s+(\d{4})",
    re.I,
)


class _ParagraphExtractor(HTMLParser):
    """Pulls the text content of every top-level <p> element, in document order."""

    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self._depth = 0
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._depth += 1
        elif self._depth > 0 and tag == "br":
            self._buffer.append(" ")

    def handle_endtag(self, tag):
        if tag == "p" and self._depth > 0:
            self._depth -= 1
            if self._depth == 0:
                self.paragraphs.append("".join(self._buffer).strip())
                self._buffer = []

    def handle_data(self, data):
        if self._depth > 0:
            self._buffer.append(data)


def extract_paragraphs(page_html):
    """Return the stripped text of every top-level <p> in page_html, in order."""
    parser = _ParagraphExtractor()
    parser.feed(page_html)
    return [re.sub(r"\s+", " ", p).strip() for p in parser.paragraphs]


def is_set_page_title(title):
    """Whether `title` structurally looks like a dated setlist page, even if
    the date itself doesn't parse cleanly (e.g. a typo'd year like
    "2924.09.21" or "202.02.14", both seen in real page titles).

    Used to tell real (if messy) set pages apart from unrelated pages mixed
    into a section, like "Best of mix", "Songs to fix", or the handful of
    non-setlist pages found in the "2022 BC" section.
    """
    text = (title or "").strip()
    return bool(DOTTED_DATE_PATTERN.match(text) or WORDY_DATE_PATTERN.match(text))


def parse_page_date(title):
    """Return an ISO date parsed from a setlist page title, or None if the
    title doesn't look date-like at all, or looks date-like but the date
    itself doesn't parse cleanly.

    Handles both title conventions seen across years: "Month Day, Year[ Set]"
    (2021, e.g. "April 17, 2021 Set") and "yyyy.mm.dd[ extra text]" (2022
    onward, e.g. "2022.07.16 Heatwave", "2023.12.30 (31)"). Check
    is_set_page_title separately to still process a page whose title looks
    date-like but didn't parse (rather than skipping it as junk).
    """
    text = (title or "").strip()

    match = DOTTED_DATE_PATTERN.match(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            return None
        if not (2015 <= date.year <= datetime.date.today().year + 1):
            return None  # e.g. "2924.09.21", "202.02.14" - typo'd years, not real dates
        return date.isoformat()

    match = WORDY_DATE_PATTERN.match(text)
    if match:
        month_name, day, year = match.groups()
        try:
            return datetime.datetime.strptime(f"{month_name} {day}, {year}", "%B %d, %Y").date().isoformat()
        except ValueError:
            return None

    return None


def _strip_leading_header(lines, page_title):
    """Drop leading non-track lines some pages have before the real
    title/artist/label triplets start: OneNote's echoed page title, and/or a
    hand-added cover-image caption block. The caption block's exact wording
    varies across years ("Art: <url>", "Cover:" then the url as its own
    line, "Title: <custom name>" then the url, or a bare custom title
    immediately followed by the url with no label at all) - so a line is
    treated as header junk if it's labelled art/cover/title, contains a url,
    or immediately precedes one.
    """
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().lower() == (page_title or "").strip().lower():
            i += 1
            continue
        is_label = bool(HEADER_LABEL_PATTERN.match(line))
        is_url = bool(URL_PATTERN.search(line))
        is_caption_for_next_url = (
            not is_label and not is_url and i + 1 < len(lines) and bool(URL_PATTERN.search(lines[i + 1]))
        )
        if is_label or is_url or is_caption_for_next_url:
            i += 1
        else:
            break
    return lines[i:]


def _group_as_triplets(lines):
    """(title, artist, label) grouping.

    Pages using the "[Label Year]" bracket-tag convention for the label line
    (2024 onward - see module docstring) are grouped by anchoring on each
    line matching that shape (WRAPPED_LABEL_PATTERN) and taking the two
    lines immediately before it as title/artist, rather than counting
    forward in fixed steps of 3 from the start. That survives a stray line
    inserted anywhere on the page - a one-off editorial aside like "(oh this
    is bad labelling!)" seen wedged between two tracks in real data, or an
    unstrippable leading comment - either of which would otherwise silently
    shift every track after it by one position. Some pages switch convention
    partway through rather than at a page boundary (a run of plain,
    unbracketed label triplets before or after the bracket-tagged ones, seen
    in real 2022 data), so whatever the anchor pass doesn't consume is also
    tried as plain triplets, run by contiguous run. Pages with no bracket-tag
    signal at all skip straight to that fallback for the whole page.

    Returns (tracks, dropped) where `dropped` is the count of lines that
    ended up in neither a title, artist, nor label slot.
    """
    expected_label_lines = max(len(lines) // 3, 1)
    wrapped_count = sum(1 for line in lines if WRAPPED_LABEL_PATTERN.match(line))

    if wrapped_count / expected_label_lines >= 0.5:
        tracks = []
        consumed = set()
        for i in range(2, len(lines)):
            if WRAPPED_LABEL_PATTERN.match(lines[i]):
                tracks.append(
                    {
                        "title": lines[i - 2],
                        "artist_text": lines[i - 1],
                        "label": WRAPPED_LABEL_PATTERN.match(lines[i]).group(1).strip(),
                    }
                )
                consumed.update((i - 2, i - 1, i))

        dropped = 0
        run = []
        for i in list(range(len(lines))) + [None]:  # None flushes the final run
            if i is not None and i not in consumed:
                run.append(lines[i])
                continue
            remainder = len(run) % 3
            tracks.extend(
                {"title": run[j], "artist_text": run[j + 1], "label": run[j + 2]}
                for j in range(0, len(run) - remainder, 3)
            )
            dropped += remainder
            run = []
        return tracks, dropped

    remainder = len(lines) % 3
    tracks = [
        {"title": lines[i], "artist_text": lines[i + 1], "label": lines[i + 2]}
        for i in range(0, len(lines) - remainder, 3)
    ]
    return tracks, remainder


def _group_as_pairs(lines):
    """(title-with-a-[Label]-tag, artist) grouping - what pages switched to
    around 2026, folding the label directly into the title the same way
    Rekordbox titles already do (core.rekordbox_extractor.parse_title).

    Returns (tracks, remainder, tagged_fraction). Entries whose title has no
    resolvable tag are dropped (nothing to key a label off), which is also
    how tagged_fraction is used by parse_page_tracks to tell a real 2-line
    page from a 3-line page that merely divides evenly by 2 as well.
    """
    pair_count = len(lines) // 2
    tracks = []
    tagged = 0
    for i in range(0, pair_count * 2, 2):
        raw_title, artist_text = lines[i], lines[i + 1]
        title, label, flagged = parse_title(raw_title)
        if label:
            tagged += 1
            tracks.append({"title": title, "artist_text": artist_text, "label": label})
    tagged_fraction = tagged / pair_count if pair_count else 0
    return tracks, len(lines) % 2, tagged_fraction


def parse_page_tracks(page_html, page_title, section_name):
    """Parse one OneNote setlist page into title/artist(s)/label track dicts.

    Tries both the 3-line (title, artist, label) and 2-line (title-with-tag,
    artist) groupings - see _group_as_triplets/_group_as_pairs - and picks
    the pair grouping only when most of its titles actually carry a
    resolvable [Label] tag, since that's the real signal a page switched
    convention (an even paragraph count alone proves nothing).

    Returns (tracks, warning). `warning` is set when neither grouping
    divided evenly - the page is still parsed as far as it cleanly can be
    (leftover lines dropped from the end), but it's worth a manual look in
    OneNote since the mismatch is usually a one-off hand-typed irregularity
    (a stray comment line, a track's fields split across an extra line,
    etc.) rather than one of the known conventions already handled here.
    """
    lines = [p for p in extract_paragraphs(page_html) if p and not MARKER_LINE_PATTERN.match(p)]
    lines = _strip_leading_header(lines, page_title)

    triplet_tracks, triplet_dropped = _group_as_triplets(lines)
    pair_tracks, pair_remainder, pair_tagged_fraction = _group_as_pairs(lines)

    if pair_tagged_fraction >= 0.7:
        tracks, dropped = pair_tracks, pair_remainder
        grouping = "title/artist"
    else:
        tracks, dropped = triplet_tracks, triplet_dropped
        grouping = "title/artist/label"

    warning = None
    if dropped:
        warning = (
            f"{page_title!r} ({section_name}): {dropped} paragraph(s) dropped (unmatched leading "
            f"or trailing lines) after grouping into {grouping} entries - check the page manually"
        )
    return tracks, warning
