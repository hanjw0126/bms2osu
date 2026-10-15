"""BMS chart -> osu!mania notes + timing points."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .parser import BmsChart

_KEY_UNIT = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 8: 6, 9: 7}  # channel unit digit -> key no.


@dataclass
class Note:
    lane: int
    time: int  # ms
    end: Optional[int] = None  # ms, long note only


@dataclass
class Converted:
    keys: int
    notes: List[Note]
    timing: List[Tuple[int, float]]  # (ms, bpm)
    double: bool
    warnings: List[str] = field(default_factory=list)
    # keysounds to play: (time_ms, wav id). BGM (ch 01) + every playable note,
    # including scratch notes that were removed from the playfield.
    sounds: List[Tuple[float, str]] = field(default_factory=list)


def classify_channel(ch: str):
    """Return (player, key, is_long) or None. key is 1..7 or 'S' (scratch)."""
    if len(ch) != 2 or not ch.isdigit():
        return None
    tens, unit = int(ch[0]), int(ch[1])
    if tens not in (1, 2, 5, 6):
        return None
    if unit == 6:
        key = "S"
    elif unit in _KEY_UNIT:
        key = _KEY_UNIT[unit]
    else:
        return None
    return (1 if tens in (1, 5) else 2, key, tens in (5, 6))


def _lane(player, key, per_side, remove_scratch, keys):
    if key == "S":
        if remove_scratch:
            return None
        return 0 if player == 1 else keys - 1
    if player == 1:
        return (key - 1) + (0 if remove_scratch else 1)
    return per_side + (key - 1)


def convert_chart(chart: BmsChart, remove_scratch: bool = False) -> Converted:
    warnings: List[str] = []

    # ---- 1. collect events per measure -------------------------------------
    events: Dict[int, list] = {}
    max_measure = max(
        [o.measure for o in chart.objects] + list(chart.measure_len.keys()) + [0]
    )
    missing = set()

    def add(measure, pos, order, kind, payload):
        events.setdefault(measure, []).append((pos, order, kind, payload))

    for o in chart.objects:
        ch = o.channel
        if ch == "03":
            try:
                v = int(o.value, 16)
            except ValueError:
                continue
            if v > 0:
                add(o.measure, o.pos, 0, "bpm", float(v))
        elif ch == "08":
            bpm = chart.bpm_table.get(o.value)
            if bpm is None:
                missing.add("BPM" + o.value)
            elif bpm > 0:
                add(o.measure, o.pos, 0, "bpm", bpm)
        elif ch == "09":
            stop = chart.stop_table.get(o.value)
            if stop is None:
                missing.add("STOP" + o.value)
            elif stop > 0:
                add(o.measure, o.pos, 2, "stop", stop)
        elif ch == "01":
            add(o.measure, o.pos, 1, "bgm", o.value)
        else:
            c = classify_channel(ch)
            if c:
                add(o.measure, o.pos, 1, "note", (c, o.value))
    for name in sorted(missing):
        warnings.append(f"정의되지 않은 #{name} 참조를 무시함")

    # ---- 2. walk the timeline (BPM changes, STOPs, measure length) ---------
    bpm = chart.initial_bpm
    t = 0.0
    timing = [(0.0, bpm)]
    raw = []  # (player, key, is_long, value, time_ms)
    sounds: List[Tuple[float, str]] = []
    for m in range(max_measure + 1):
        length = chart.measure_len.get(m, 1.0)
        prev = 0.0
        for pos, _order, kind, payload in sorted(
            events.get(m, []), key=lambda e: (e[0], e[1])
        ):
            t += (pos - prev) * 4 * length * 60000.0 / bpm
            prev = pos
            if kind == "bpm":
                bpm = payload
                timing.append((t, bpm))
            elif kind == "stop":
                t += payload / 48.0 * 60000.0 / bpm  # 192 units = 4 beats
            elif kind == "bgm":
                sounds.append((t, payload))
            else:
                (player, key, is_long), value = payload
                raw.append((player, key, is_long, value, t))
        t += (1.0 - prev) * 4 * length * 60000.0 / bpm

    # ---- 3. lane layout ------------------------------------------------------
    double = any(r[0] == 2 for r in raw)
    per_side = 7 + (0 if remove_scratch else 1)
    keys = per_side * (2 if double else 1)

    lanes: Dict[int, list] = {}
    for player, key, is_long, value, time in raw:
        lane = _lane(player, key, per_side, remove_scratch, keys)
        if lane is None:
            continue
        lanes.setdefault(lane, []).append((time, value, is_long))

    # ---- 4. build notes (normal / LN via ch5x,6x / LN via #LNOBJ) -----------
    lnobj = chart.headers.get("LNOBJ", "").strip().upper()
    notes: Dict[Tuple[int, int], Note] = {}
    for lane, objs in lanes.items():
        objs.sort(key=lambda x: x[0])
        pending: Optional[Note] = None
        last: Optional[Note] = None
        for time, value, is_long in objs:
            ms = int(round(time))
            if is_long:
                if pending is None:
                    pending = Note(lane, ms)
                else:
                    if ms > pending.time:
                        pending.end = ms
                    notes[(lane, pending.time)] = pending
                    pending = None
            elif lnobj and value == lnobj:
                if last is not None and last.end is None and ms > last.time:
                    last.end = ms
                last = None
            else:
                last = Note(lane, ms)
                notes[(lane, ms)] = last
        if pending is not None:
            notes[(lane, pending.time)] = pending
            warnings.append(f"레인 {lane}: 끝나지 않은 롱노트를 일반 노트로 처리함")

    # ---- 5. keysounds of playable notes (LN end / #LNOBJ end make no sound) --
    per_key: Dict[Tuple[int, object], list] = {}
    for player, key, is_long, value, time in raw:
        per_key.setdefault((player, key), []).append((time, value, is_long))
    for objs in per_key.values():
        objs.sort(key=lambda x: x[0])
        ln_open = False
        for time, value, is_long in objs:
            if is_long:
                if not ln_open:  # LN start plays, LN end is silent
                    sounds.append((time, value))
                ln_open = not ln_open
            elif lnobj and value == lnobj:
                continue
            else:
                sounds.append((time, value))
    sounds.sort()

    # ---- 6. timing points ----------------------------------------------------
    tp: Dict[int, float] = {}
    for ms, b in timing:
        tp[int(round(ms))] = b
    timing_out = sorted(tp.items())

    return Converted(
        keys=keys,
        notes=sorted(notes.values(), key=lambda n: (n.time, n.lane)),
        timing=timing_out,
        double=double,
        warnings=warnings,
        sounds=sounds,
    )
