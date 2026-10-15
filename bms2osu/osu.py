"""Render an osu!mania .osu file (format v14)."""
from __future__ import annotations

import re
from typing import Optional

from .converter import Converted
from .parser import BmsChart

DIFF_NAMES = {"1": "BEGINNER", "2": "NORMAL", "3": "HYPER", "4": "ANOTHER", "5": "INSANE"}


def version_name(chart: BmsChart, keys: int) -> str:
    label = DIFF_NAMES.get(chart.headers.get("DIFFICULTY", "").strip()) or chart.path.stem
    name = f"{label} {keys}K"
    level = chart.headers.get("PLAYLEVEL", "").strip()
    if level:
        name += f" Lv.{level}"
    return name


def safe_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s).strip(" .") or "beatmap"


def _fmt(x: float) -> str:
    return format(x, ".12g")


def render_osu(
    chart: BmsChart,
    conv: Converted,
    *,
    audio_name: str,
    bg_name: Optional[str] = None,
    creator: str = "bms2osu",
    od: float = 8.0,
    hp: float = 8.0,
    version: Optional[str] = None,
) -> str:
    h = chart.headers
    title = h.get("TITLE", chart.path.stem)
    subtitle = h.get("SUBTITLE", "")
    if subtitle:
        title = f"{title} {subtitle}"
    artist = h.get("ARTIST", "Unknown")
    version = version or version_name(chart, conv.keys)

    out = [
        "osu file format v14",
        "",
        "[General]",
        f"AudioFilename: {audio_name}",
        "AudioLeadIn: 0",
        "PreviewTime: -1",
        "Countdown: 0",
        "SampleSet: Soft",
        "StackLeniency: 0.7",
        "Mode: 3",
        "LetterboxInBreaks: 0",
        "SpecialStyle: 0",
        "WidescreenStoryboard: 0",
        "",
        "[Editor]",
        "DistanceSpacing: 1",
        "BeatDivisor: 4",
        "GridSize: 4",
        "TimelineZoom: 1",
        "",
        "[Metadata]",
        f"Title:{title}",
        f"TitleUnicode:{title}",
        f"Artist:{artist}",
        f"ArtistUnicode:{artist}",
        f"Creator:{creator}",
        f"Version:{version}",
        "Source:BMS",
        f"Tags:{h.get('GENRE', '')}",
        "BeatmapID:0",
        "BeatmapSetID:-1",
        "",
        "[Difficulty]",
        f"HPDrainRate:{_fmt(hp)}",
        f"CircleSize:{conv.keys}",
        f"OverallDifficulty:{_fmt(od)}",
        "ApproachRate:5",
        "SliderMultiplier:1.4",
        "SliderTickRate:1",
        "",
        "[Events]",
        "//Background and Video events",
    ]
    if bg_name:
        out.append(f'0,0,"{bg_name}",0,0')
    out += ["", "[TimingPoints]"]
    for ms, bpm in conv.timing:
        out.append(f"{ms},{_fmt(60000.0 / bpm)},4,1,0,100,1,0")
    out += ["", "[HitObjects]"]
    for n in conv.notes:
        x = int((n.lane + 0.5) * 512 / conv.keys)
        if n.end is None:
            out.append(f"{x},192,{n.time},1,0,0:0:0:0:")
        else:
            out.append(f"{x},192,{n.time},128,0,{n.end}:0:0:0:0:")
    return "\n".join(out) + "\n"
