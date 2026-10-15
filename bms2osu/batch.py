"""Folder-level processing: one folder of BMS charts -> one osu! beatmapset."""
from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import difficulty, keysound
from .converter import convert_chart
from .osu import render_osu, safe_filename, version_name
from .parser import parse_bms

AUDIO_EXTS = {".ogg", ".mp3", ".wav"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class Options:
    remove_scratch: bool = False
    fmt: str = "osz"  # "osz" or "osu"
    audio: Optional[str] = None
    creator: str = "bms2osu"
    od: Optional[float] = None  # None = automatic (from BMS when fix_difficulty, else 8)
    hp: Optional[float] = None
    encoding: Optional[str] = None
    fix_difficulty: bool = True  # BMS difficulty -> osu! name / OD / HP / set title
    render_keysounds: bool = True  # mix BMS keysounds into one audio file


@dataclass
class GroupResult:
    folder: str
    output: Optional[str] = None
    charts: int = 0
    skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


def pick_audio(folder: Path, chart_stems, explicit: Optional[str], keysound_names=()) -> Tuple[Optional[Path], Optional[str]]:
    if explicit:
        p = Path(explicit)
        cand = p if p.is_absolute() else folder / p
        if cand.is_file():
            return cand, None
        return None, f"지정한 오디오 파일을 찾을 수 없음: {explicit}"
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    if not files:
        return None, "폴더에서 오디오 파일을 찾지 못함 (BMS 키음을 하나로 렌더링한 파일이 필요, --audio 참고)"
    stems = {s.lower() for s in chart_stems}
    # files used as keysounds (#WAVxx) are single sounds, not the full song
    used = {Path(n.replace("\\", "/")).stem.lower() for n in keysound_names}
    pool = ([f for f in files if f.stem.lower() in stems]
            or [f for f in files if f.stem.lower() not in used]
            or files)
    best = max(pool, key=lambda f: f.stat().st_size)
    note = None
    if len(files) > 1:
        note = f"오디오 자동 선택: {best.name} (후보 {len(files)}개, 틀렸다면 --audio 사용)"
    return best, note


def pick_background(folder: Path, charts) -> Optional[Path]:
    for chart in charts:
        for key in ("STAGEFILE", "BACKBMP"):
            name = chart.headers.get(key, "").strip()
            if not name:
                continue
            p = folder / name
            if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                return p
    return None


def process_group(folder: str, files: List[str], out_dir: str, out_stem: str, opts: Options) -> GroupResult:
    folder_p = Path(folder)
    res = GroupResult(folder=str(folder_p))
    tmp = None
    try:
        parsed = []
        for f in sorted(files):
            name = Path(f).name
            chart = parse_bms(f, opts.encoding)
            conv = convert_chart(chart, opts.remove_scratch)
            if not conv.notes:
                res.skipped += 1
                res.warnings.append(f"{name}: 노트가 없어 건너뜀")
                continue
            res.warnings.extend(f"{name}: {w}" for w in conv.warnings)
            parsed.append((chart, conv))
        if not parsed:
            res.error = "변환 가능한 채보가 없음"
            return res

        bg = pick_background(folder_p, [c for c, _ in parsed])
        tmp = tempfile.TemporaryDirectory(prefix="bms2osu_")
        tmp_dir = Path(tmp.name)
        # per chart audio name, plus audio files to ship: (name in set, path on disk)
        chart_audio: Dict[int, str] = {}
        media: List[Tuple[str, Path]] = []

        if opts.render_keysounds and not opts.audio:
            reason = keysound.available()
            if reason:
                res.warnings.append(reason)
            else:
                _render_keysounds(folder_p, parsed, tmp_dir, chart_audio, media, res)

        if len(chart_audio) < len(parsed):
            names = [n for c, _ in parsed for n in c.wav_table.values()]
            audio, audio_msg = pick_audio(
                folder_p, [c.path.stem for c, _ in parsed], opts.audio, names)
            if audio_msg:
                res.warnings.append(audio_msg)
            fallback = audio.name if audio else "audio.mp3"
            if audio and all(m[0].lower() != audio.name.lower() for m in media):
                media.append((audio.name, audio))
            for i in range(len(parsed)):
                chart_audio.setdefault(i, fallback)
        if bg:
            media.append((bg.name, bg))

        built = []
        used = set()
        if opts.fix_difficulty:
            infos = difficulty.chart_infos(
                [(c.headers, c.path.stem, conv.bms_notes) for c, conv in parsed])
            set_title, set_artist = difficulty.set_metadata(
                [c.headers for c, _ in parsed], folder_p.name)
        for i, (chart, conv) in enumerate(parsed):
            if opts.fix_difficulty:
                info = infos[i]
                version, title, artist = info.version, set_title, set_artist
                od = opts.od if opts.od is not None else info.od
                hp = opts.hp if opts.hp is not None else info.hp
                tags = " ".join(t for t in (
                    chart.headers.get("GENRE", ""), "BMS",
                    info.label or "", f"lv{info.level}" if info.level else "") if t)
            else:
                version = version_name(chart, conv.keys)
                title = artist = tags = None
                od = opts.od if opts.od is not None else 8.0
                hp = opts.hp if opts.hp is not None else 8.0
            text = render_osu(
                chart, conv,
                audio_name=chart_audio[i],
                bg_name=bg.name if bg else None,
                creator=opts.creator, od=od, hp=hp, version=version,
                title=title, artist=artist, tags=tags,
            )
            name_artist = artist or chart.headers.get("ARTIST", "Unknown")
            name_title = title or chart.headers.get("TITLE", chart.path.stem)
            base = safe_filename(f"{name_artist} - {name_title} ({opts.creator}) [{version}]")
            fname, n = base + ".osu", 2
            while fname.lower() in used:
                fname = f"{base}_{n}.osu"
                n += 1
            used.add(fname.lower())
            built.append((fname, text))
            res.charts += 1

        out = Path(out_dir)
        if opts.fmt == "osz":
            out.mkdir(parents=True, exist_ok=True)
            target = out / f"{out_stem}.osz"
            with zipfile.ZipFile(target, "w") as z:
                for fname, text in built:
                    z.writestr(fname, text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
                for arc, path in media:
                    z.write(path, arc, compress_type=zipfile.ZIP_STORED)
        else:
            target = out / out_stem
            target.mkdir(parents=True, exist_ok=True)
            for fname, text in built:
                (target / fname).write_text(text, encoding="utf-8")
            for arc, path in media:
                (target / arc).write_bytes(path.read_bytes())
        res.output = str(target)
    except Exception as e:  # keep batch going
        res.error = f"{type(e).__name__}: {e}"
    finally:
        if tmp is not None:
            tmp.cleanup()
    return res


def _render_keysounds(folder: Path, parsed, tmp_dir: Path, chart_audio, media, res) -> None:
    """Mix each chart's keysounds into one file; identical mixes share one file."""
    index = keysound.build_index(folder)
    cache: Dict[Path, object] = {}
    by_signature: Dict[tuple, str] = {}
    for i, (chart, conv) in enumerate(parsed):
        name = chart.path.name
        events, missing = keysound.resolve_events(conv.sounds, chart.wav_table, index)
        if missing:
            ex = ", ".join(missing[:3]) + (" 등" if len(missing) > 3 else "")
            res.warnings.append(f"{name}: 키음 파일 {len(missing)}개를 찾지 못함 ({ex})")
        sig = keysound.signature(events)
        if sig in by_signature:
            chart_audio[i] = by_signature[sig]
            continue
        try:
            data = keysound.mix(events, cache, keysound.chart_volume(chart.headers))
        except MemoryError:
            res.warnings.append(f"{name}: 메모리 부족으로 키음 합성 실패, 폴더 오디오 사용")
            continue
        if data is None:
            res.warnings.append(f"{name}: 합성할 키음이 없어 폴더의 오디오 파일을 사용")
            continue
        stem = "audio" if not by_signature else f"audio_{len(by_signature) + 1}"
        path = keysound.write_audio(data, tmp_dir / stem)
        by_signature[sig] = path.name
        chart_audio[i] = path.name
        media.append((path.name, path))
    cache.clear()
