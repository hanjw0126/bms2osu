"""Translate BMS difficulty information into osu! terms.

- difficulty name : #DIFFICULTY, or a tag in the title / subtitle / file name
                    ("[ANOTHER]", "song_7h.bme" ...), plus #PLAYLEVEL
- set metadata    : difficulty tags are removed from #TITLE / #SUBTITLE so every
                    difficulty of a song shares one title in osu!
- OD              : from the judge rank (#RANK / #DEFEXRANK)
- HP              : from the gauge (#TOTAL) relative to the usual TOTAL for the note count

osu! star rating is always calculated by osu! itself from the notes and cannot
be written into a beatmap, so the BMS level is kept in the difficulty name.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

BEGINNER, NORMAL, HYPER, ANOTHER, INSANE, LEGGENDARIA = (
    "BEGINNER", "NORMAL", "HYPER", "ANOTHER", "INSANE", "LEGGENDARIA")
ORDER = {BEGINNER: 1, NORMAL: 2, HYPER: 3, ANOTHER: 4, INSANE: 5, LEGGENDARIA: 6}

_DIFFICULTY_HEADER = {"1": BEGINNER, "2": NORMAL, "3": HYPER, "4": ANOTHER, "5": INSANE}

# words found in titles like "Song [SP ANOTHER]" / "Song -HYPER-" / "Song (7keys LEGGENDARIA)"
_WORDS = [
    (r"black\s*another|leggendaria|legg?end", LEGGENDARIA),
    (r"insane|ex(?:tra)?\s*another|kusofumen|\u767a\u72c2|\u2605", INSANE),
    (r"another", ANOTHER),
    (r"hyper", HYPER),
    (r"normal", NORMAL),
    (r"beginner|easy|light", BEGINNER),
]
_WORD_RE = [(re.compile(rf"(?<![a-z]){p}(?![a-z])", re.I), lab) for p, lab in _WORDS]

# a trailing group that is only a difficulty tag: [ANOTHER], (SP HYPER), -NORMAL-, <7KEYS INSANE> ...
_TAG_BODY = (r"(?:sp|dp|\d+\s*keys?|\d+k)?\s*(?:black\s*another|leggendaria|insane|extra\s*another|"
             r"another|hyper|normal|beginner|light|easy)(?:\s*(?:\d+|\d+\s*keys?|\d+k|sp|dp))?")
_TRAIL_TAG = re.compile(
    rf"\s*(?:\[\s*{_TAG_BODY}\s*\]|\(\s*{_TAG_BODY}\s*\)|<\s*{_TAG_BODY}\s*>|"
    rf"\u3010\s*{_TAG_BODY}\s*\u3011|-\s*{_TAG_BODY}\s*-|~\s*{_TAG_BODY}\s*~)\s*$", re.I)

# file names: song_7a.bme, song-hyper.bme, [ANOTHER].bms, 7n.bme ...
_SEP_L, _SEP_R = r"[_\-\s\[\(.]", r"(?:$|[_\-\s\]\).])"
_PREFIX = r"(?:sp|dp|7|14|5|10)?"


def _stem_rx(words: str, abbrevs: str):
    # full words may start the stem; short abbreviations need a separator before them
    return re.compile(
        rf"(?:(?:^|{_SEP_L}){_PREFIX}(?:{words}){_SEP_R}|{_SEP_L}{_PREFIX}(?:{abbrevs}){_SEP_R})", re.I)


_STEM_RE = [
    (_stem_rx(r"black\s*another|leggendaria", r"lgd|leg|l"), LEGGENDARIA),
    (_stem_rx(r"insane", r"ins|x"), INSANE),
    (_stem_rx(r"another", r"ano|a"), ANOTHER),
    (_stem_rx(r"hyper", r"hyp|h"), HYPER),
    (_stem_rx(r"normal", r"nor|n"), NORMAL),
    (_stem_rx(r"beginner", r"beg|b"), BEGINNER),
]
# "7a" / "14h" style stems without a separator
_SHORT_STEM = re.compile(r"^(?:7|14|5|10)([bnhaxl])$", re.I)
_SHORT_MAP = {"b": BEGINNER, "n": NORMAL, "h": HYPER, "a": ANOTHER, "x": INSANE, "l": LEGGENDARIA}


_BARE_TAG = re.compile(rf"[\[\(<\u3010\-~\s]*{_TAG_BODY}[\]\)>\u3011\-~\s]*", re.I)


def is_tag_only(text: str) -> bool:
    """True for subtitles like "ANOTHER", "[SP HYPER]", "-NORMAL-"."""
    return bool(text.strip()) and bool(_BARE_TAG.fullmatch(text.strip()))


def strip_tags(text: str) -> str:
    """Remove trailing difficulty tags ("Song [ANOTHER]" -> "Song")."""
    prev = None
    text = text.strip()
    while prev != text:
        prev = text
        text = _TRAIL_TAG.sub("", text).strip()
    return text


def _label_from_text(text: str) -> Optional[str]:
    for rx, lab in _WORD_RE:
        if rx.search(text):
            return lab
    return None


def detect_label(headers: Dict[str, str], stem: str) -> Optional[str]:
    d = headers.get("DIFFICULTY", "").strip()
    if d in _DIFFICULTY_HEADER:
        return _DIFFICULTY_HEADER[d]
    for key in ("TITLE", "SUBTITLE"):
        text = headers.get(key, "")
        tag = text[len(strip_tags(text)):] if text else ""
        if tag:
            lab = _label_from_text(tag)
            if lab:
                return lab
    sub = headers.get("SUBTITLE", "").strip()
    if is_tag_only(sub):
        lab = _label_from_text(sub)
        if lab:
            return lab
    m = _SHORT_STEM.match(stem)
    if m:
        return _SHORT_MAP[m.group(1).lower()]
    for rx, lab in _STEM_RE:
        if rx.search(stem):
            return lab
    return None


def format_level(level: str) -> str:
    level = level.strip()
    if not level:
        return ""
    if level[0] in "\u2605\u2606\u25c6\u25c7\u203b":  # ★ ☆ ◆ ◇ ※ (difficulty tables)
        return level
    return f"Lv.{level}"


# ------------------------------------------------------------------ OD / HP
# osu!mania 300 window = 64 - 3*OD ms. BMS judge ranks are mapped so that
# NORMAL (the most common rank) lands on OD 8, and stricter ranks go higher.
_RANK_OD = {"0": 9.0, "1": 8.5, "2": 8.0, "3": 7.0, "4": 6.0}  # VERY HARD .. VERY EASY
_DEFEX_POINTS = [(25.0, 9.5), (50.0, 9.0), (75.0, 8.5), (100.0, 8.0), (125.0, 7.0), (150.0, 6.0)]


def _interp(x: float, pts: Sequence[Tuple[float, float]]) -> float:
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def estimate_od(headers: Dict[str, str]) -> float:
    ex = headers.get("DEFEXRANK", "").strip()
    if ex:
        try:
            return round(_interp(float(ex), _DEFEX_POINTS) * 2) / 2
        except ValueError:
            pass
    return _RANK_OD.get(headers.get("RANK", "").strip(), 8.0)


def standard_total(notes: int) -> float:
    """TOTAL a chart with this many notes usually has (IIDX-like gauge)."""
    n = max(notes, 1)
    return 7.605 * n / (0.01 * n + 6.5)


def estimate_hp(headers: Dict[str, str], notes: int) -> float:
    """Generous gauge (high #TOTAL) -> lower HP drain, harsh gauge -> higher."""
    try:
        total = float(headers.get("TOTAL", ""))
    except ValueError:
        return 8.0
    if total <= 0 or notes <= 0:
        return 8.0
    ratio = total / standard_total(notes)
    hp = 8.0 - 2.0 * math.log2(ratio)
    return round(min(9.5, max(5.0, hp)) * 2) / 2


# ------------------------------------------------------------------ set level
@dataclass
class ChartInfo:
    version: str
    od: float
    hp: float
    label: Optional[str]
    level: str


def set_metadata(headers_list: Sequence[Dict[str, str]], fallback_title: str) -> Tuple[str, str]:
    """One title / artist for the whole beatmapset (difficulty tags removed)."""
    titles = [strip_tags(h.get("TITLE", "")) or fallback_title for h in headers_list]
    title = Counter(titles).most_common(1)[0][0]
    subs = {"" if is_tag_only(h.get("SUBTITLE", "")) else strip_tags(h.get("SUBTITLE", ""))
            for h in headers_list}
    sub = subs.pop() if len(subs) == 1 else ""
    if sub and sub.lower() not in title.lower():
        title = f"{title} {sub}"
    artists = [h.get("ARTIST", "").strip() for h in headers_list if h.get("ARTIST", "").strip()]
    artist = Counter(artists).most_common(1)[0][0] if artists else "Unknown"
    return title, artist


def chart_infos(charts: Sequence[Tuple[Dict[str, str], str, int]]) -> List[ChartInfo]:
    """charts: (headers, file stem, BMS note count). Returns unique osu! difficulty names."""
    infos = []
    for headers, stem, notes in charts:
        label = detect_label(headers, stem)
        level = headers.get("PLAYLEVEL", "").strip()
        lv = format_level(level)
        if label:
            version = f"{label} {lv}".strip()
        else:
            version = lv or stem
        infos.append(ChartInfo(version, estimate_od(headers), estimate_hp(headers, notes), label, level))
    counts = Counter(i.version.lower() for i in infos)
    for info, (_h, stem, _n) in zip(infos, charts):
        if counts[info.version.lower()] > 1:
            info.version = f"{info.version} ({stem})"
    return infos
