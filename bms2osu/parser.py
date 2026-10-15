"""Minimal but practical BMS / BME / BML parser (base-36 object ids)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_CHANNEL_RE = re.compile(r"^#(\d{3})([0-9A-Za-z]{2})\s*:\s*(.*)$")
_HEADER_RE = re.compile(r"^#([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.*))?$")
_TABLE_RE = re.compile(r"^(BPM|EXBPM|STOP|WAV)([0-9A-Z]{2})$")

_ENCODINGS = ("utf-8-sig", "cp932", "cp949", "gb18030")


def read_text(path: Path, encoding: Optional[str] = None) -> str:
    raw = Path(path).read_bytes()
    if encoding:
        return raw.decode(encoding, errors="replace")
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp932", errors="replace")


@dataclass
class BmsObject:
    measure: int
    channel: str
    pos: float  # 0.0 <= pos < 1.0 inside the measure
    value: str  # two-char base-36 id, upper-case, never "00"


@dataclass
class BmsChart:
    path: Path
    headers: Dict[str, str] = field(default_factory=dict)
    bpm_table: Dict[str, float] = field(default_factory=dict)
    stop_table: Dict[str, float] = field(default_factory=dict)
    wav_table: Dict[str, str] = field(default_factory=dict)
    measure_len: Dict[int, float] = field(default_factory=dict)
    objects: List[BmsObject] = field(default_factory=list)

    @property
    def initial_bpm(self) -> float:
        try:
            bpm = float(self.headers.get("BPM", "120"))
        except ValueError:
            return 120.0
        return bpm if bpm > 0 else 120.0


def _split_data(data: str):
    data = re.sub(r"\s+", "", data)
    n = len(data) // 2
    out = []
    for i in range(n):
        val = data[2 * i : 2 * i + 2].upper()
        if val != "00":
            out.append((i / n, val))
    return out


def parse_bms(path, encoding: Optional[str] = None) -> BmsChart:
    p = Path(path)
    chart = BmsChart(path=p)
    random_value = 1  # #RANDOM is resolved deterministically to 1
    if_stack: List[bool] = []

    for line in read_text(p, encoding).splitlines():
        line = line.strip()
        if not line.startswith("#"):
            continue

        m = _CHANNEL_RE.match(line)
        if m:
            if not all(if_stack):
                continue
            measure = int(m.group(1))
            channel = m.group(2).upper()
            data = m.group(3)
            if channel == "02":
                try:
                    v = float(data.strip())
                    if v > 0:
                        chart.measure_len[measure] = v
                except ValueError:
                    pass
                continue
            for pos, val in _split_data(data):
                chart.objects.append(BmsObject(measure, channel, pos, val))
            continue

        h = _HEADER_RE.match(line)
        if not h:
            continue
        key = h.group(1).upper()
        value = (h.group(2) or "").strip()

        if key in ("RANDOM", "RONDOM"):
            random_value = 1
            continue
        if key == "IF":
            try:
                if_stack.append(int(value) == random_value)
            except ValueError:
                if_stack.append(False)
            continue
        if key == "ELSE":
            if if_stack:
                if_stack[-1] = not if_stack[-1]
            continue
        if key in ("ENDIF", "END"):
            if if_stack:
                if_stack.pop()
            continue
        if not all(if_stack):
            continue

        t = _TABLE_RE.match(key)
        if t:
            kind, ident = t.group(1), t.group(2)
            if kind == "WAV":
                chart.wav_table[ident] = value
            else:
                try:
                    num = float(value)
                except ValueError:
                    continue
                if kind == "STOP":
                    chart.stop_table[ident] = num
                else:
                    chart.bpm_table[ident] = num
        else:
            chart.headers[key] = value

    return chart
