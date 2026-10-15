"""Folder-level processing: one folder of BMS charts -> one osu! beatmapset."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

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
    od: float = 8.0
    hp: float = 8.0
    encoding: Optional[str] = None


@dataclass
class GroupResult:
    folder: str
    output: Optional[str] = None
    charts: int = 0
    skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


def pick_audio(folder: Path, chart_stems, explicit: Optional[str]) -> Tuple[Optional[Path], Optional[str]]:
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
    pool = [f for f in files if f.stem.lower() in stems] or files
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

        audio, audio_msg = pick_audio(folder_p, [c.path.stem for c, _ in parsed], opts.audio)
        if audio_msg:
            res.warnings.append(audio_msg)
        bg = pick_background(folder_p, [c for c, _ in parsed])
        audio_name = audio.name if audio else "audio.mp3"

        built = []
        used = set()
        for chart, conv in parsed:
            version = version_name(chart, conv.keys)
            text = render_osu(
                chart, conv,
                audio_name=audio_name,
                bg_name=bg.name if bg else None,
                creator=opts.creator, od=opts.od, hp=opts.hp, version=version,
            )
            artist = chart.headers.get("ARTIST", "Unknown")
            title = chart.headers.get("TITLE", chart.path.stem)
            base = safe_filename(f"{artist} - {title} ({opts.creator}) [{version}]")
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
                for media in (audio, bg):
                    if media:
                        z.write(media, media.name, compress_type=zipfile.ZIP_STORED)
        else:
            target = out / out_stem
            target.mkdir(parents=True, exist_ok=True)
            for fname, text in built:
                (target / fname).write_text(text, encoding="utf-8")
            if audio:
                (target / audio.name).write_bytes(audio.read_bytes())
            if bg:
                (target / bg.name).write_bytes(bg.read_bytes())
        res.output = str(target)
    except Exception as e:  # keep batch going
        res.error = f"{type(e).__name__}: {e}"
    return res
