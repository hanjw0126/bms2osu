"""Render BMS keysounds (BGM + note sounds) into a single audio track.

BMS plays a separate sample for every note, while osu! plays one song file.
This module places every sample at its exact time and mixes them, so the
resulting audio is perfectly in sync with the converted notes.

Decoding/encoding uses `soundfile` (libsndfile: wav/ogg/flac/mp3) when it is
installed; otherwise only PCM .wav samples can be read and the mix is written
as .wav. Mixing requires numpy.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover - depends on the environment
    sf = None

SAMPLE_RATE = 44100
SAMPLE_EXTS = (".wav", ".ogg", ".flac", ".mp3")
TAIL_SECONDS = 0.5
PEAK = 0.98


class KeysoundError(Exception):
    pass


def available() -> Optional[str]:
    """None if rendering is possible, otherwise the reason it is not."""
    if np is None:
        return "numpy가 설치되어 있지 않아 키음 합성을 할 수 없음"
    return None


def output_extension() -> str:
    return ".ogg" if sf is not None else ".wav"


# ------------------------------------------------------------------ lookup
def build_index(folder: Path) -> Dict[str, Path]:
    """Case-insensitive index of every file in the folder (relative paths)."""
    index: Dict[str, Path] = {}
    for f in folder.rglob("*"):
        if f.is_file():
            index[f.relative_to(folder).as_posix().lower()] = f
    return index


def find_sample(index: Dict[str, Path], name: str) -> Optional[Path]:
    """BMS often says `kick.wav` while the file is `kick.ogg`: try every extension."""
    rel = name.strip().replace("\\", "/").lstrip("./").lower()
    if not rel:
        return None
    if rel in index:
        return index[rel]
    stem = rel.rsplit(".", 1)[0] if "." in rel.rsplit("/", 1)[-1] else rel
    for ext in SAMPLE_EXTS:
        p = index.get(stem + ext)
        if p is not None:
            return p
    return None


# ------------------------------------------------------------------ decode
def _read_wave(path: Path):
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        data = v.astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise KeysoundError(f"지원하지 않는 WAV 형식: {path.name}")
    return data.reshape(-1, ch), rate


def _read(path: Path):
    if sf is not None:
        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        return data, rate
    if path.suffix.lower() != ".wav":
        raise KeysoundError(f"{path.suffix} 파일을 읽으려면 soundfile 설치 필요")
    return _read_wave(path)


def _to_stereo_44k(data, rate: int):
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if rate != SAMPLE_RATE and len(data) > 1:
        n = max(1, int(round(len(data) * SAMPLE_RATE / rate)))
        x_old = np.arange(len(data), dtype=np.float64)
        x_new = np.linspace(0, len(data) - 1, n)
        data = np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(2)], axis=1)
    return np.ascontiguousarray(data, dtype=np.float32)


def load_sample(path: Path, cache: Dict[Path, object]):
    if path not in cache:
        try:
            data, rate = _read(path)
            cache[path] = _to_stereo_44k(data, rate) if len(data) else None
        except Exception:
            cache[path] = None
    return cache[path]


# ------------------------------------------------------------------ mix
def resolve_events(
    sounds: Sequence[Tuple[float, str]], wav_table: Dict[str, str], index: Dict[str, Path]
) -> Tuple[List[Tuple[int, str, Path]], List[str]]:
    """(start_sample, wav id, file) for every sound, plus names of missing files."""
    events, missing = [], set()
    for ms, wid in sounds:
        name = wav_table.get(wid)
        if not name:
            continue
        path = find_sample(index, name)
        if path is None:
            missing.add(name)
            continue
        events.append((max(0, int(round(ms * SAMPLE_RATE / 1000.0))), wid, path))
    events.sort(key=lambda e: e[0])
    return events, sorted(missing)


def signature(events) -> tuple:
    """Two charts with the same signature produce the same mix (reuse the file)."""
    return tuple((s, str(p)) for s, _wid, p in events)


def mix(events, cache: Dict[Path, object], volume: float = 1.0):
    """Mix events. Re-triggering the same wav id cuts the previous one (BMS behaviour)."""
    if not events:
        return None
    next_same: Dict[int, int] = {}
    last_by_id: Dict[str, int] = {}
    for i in range(len(events) - 1, -1, -1):
        s, wid, _ = events[i]
        if wid in last_by_id:
            next_same[i] = events[last_by_id[wid]][0]
        last_by_id[wid] = i

    placed = []
    end = 0
    for i, (s, _wid, path) in enumerate(events):
        smp = load_sample(path, cache)
        if smp is None:
            continue
        n = len(smp)
        if i in next_same:
            n = min(n, next_same[i] - s)
        if n <= 0:
            continue
        placed.append((s, smp, n))
        end = max(end, s + n)
    if not placed:
        return None

    out = np.zeros((end + int(TAIL_SECONDS * SAMPLE_RATE), 2), dtype=np.float32)
    for s, smp, n in placed:
        out[s:s + n] += smp[:n]
    if volume != 1.0:
        out *= volume
    peak = float(np.abs(out).max())
    if peak > PEAK:
        out *= PEAK / peak
    return out


def write_audio(data, path: Path) -> Path:
    """Write the mix as OGG Vorbis (soundfile) or 16-bit WAV (fallback)."""
    path = path.with_suffix(output_extension())
    if sf is not None:
        # chunked writes: libsndfile's vorbis encoder dislikes huge single writes
        with sf.SoundFile(str(path), "w", SAMPLE_RATE, 2, format="OGG", subtype="VORBIS") as f:
            step = SAMPLE_RATE * 5
            for i in range(0, len(data), step):
                f.write(data[i:i + step])
    else:
        pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
    return path


def chart_volume(headers: Dict[str, str]) -> float:
    try:
        v = float(headers.get("VOLWAV", "100"))
    except ValueError:
        return 1.0
    return v / 100.0 if v > 0 else 1.0
