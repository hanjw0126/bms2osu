"""Command line interface: drag & drop friendly batch converter."""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

from . import __version__
from .batch import GroupResult, Options, process_group
from .osu import safe_filename

BMS_EXTS = {".bms", ".bme", ".bml"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bms2osu",
        description="BMS/BME/BML 채보를 osu!mania(.osu / .osz)로 일괄 변환합니다. "
        "BMS 파일이 들어 있는 폴더 하나가 비트맵셋(.osz) 하나가 됩니다.",
    )
    p.add_argument("inputs", nargs="*", help="BMS 파일 또는 폴더 (여러 개 가능, 폴더는 하위까지 검색)")
    p.add_argument("-o", "--output", default="output", help="출력 폴더 (기본: ./output)")
    p.add_argument("--remove-scratch", action="store_true",
                   help="스크래치 노트 제거 (7키 / 더블이면 14키). 지정하지 않으면 8키 / 16키")
    p.add_argument("--format", choices=("osz", "osu"), default="osz",
                   help="osz: 오디오 포함 패키지(기본), osu: 폴더에 .osu 파일로 출력")
    p.add_argument("--audio", help="오디오 파일명(폴더 기준) 또는 절대 경로. 생략하면 폴더에서 자동 선택")
    p.add_argument("--creator", default="bms2osu", help="채보 제작자 이름 (기본: bms2osu)")
    p.add_argument("--od", type=float, default=8.0, help="Overall Difficulty (기본 8)")
    p.add_argument("--hp", type=float, default=8.0, help="HP Drain (기본 8)")
    p.add_argument("--encoding", help="BMS 텍스트 인코딩 강제 지정 (기본: 자동 감지)")
    p.add_argument("-j", "--jobs", type=int, default=0, help="병렬 처리 수 (기본: CPU 수, 최대 8)")
    p.add_argument("--no-recursive", action="store_true", help="폴더 하위를 검색하지 않음")
    p.add_argument("--version", action="version", version=f"bms2osu {__version__}")
    return p


def collect(inputs: List[str], recursive: bool) -> Tuple[Dict[Path, List[str]], List[str]]:
    groups: Dict[Path, set] = {}
    warnings: List[str] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            files = [f for f in it if f.is_file() and f.suffix.lower() in BMS_EXTS]
        elif p.is_file():
            files = [p] if p.suffix.lower() in BMS_EXTS else []
            if not files:
                warnings.append(f"지원하지 않는 확장자라 건너뜀: {raw}")
        else:
            warnings.append(f"찾을 수 없음: {raw}")
            continue
        for f in files:
            groups.setdefault(f.parent.resolve(), set()).add(str(f.resolve()))
    return {k: sorted(v) for k, v in groups.items()}, warnings


def _pause_if_needed() -> None:
    # Double-click / drag&drop on a Windows exe closes the console immediately.
    if getattr(sys, "frozen", False) and os.name == "nt" and sys.stdin and sys.stdin.isatty():
        input("\nEnter 키를 누르면 창이 닫힙니다...")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.inputs:
        parser.print_help()
        _pause_if_needed()
        return 2

    groups, warnings = collect(args.inputs, not args.no_recursive)
    for w in warnings:
        print(f"[경고] {w}")
    if not groups:
        print("변환할 BMS/BME/BML 파일을 찾지 못했습니다.")
        _pause_if_needed()
        return 1

    opts = Options(
        remove_scratch=args.remove_scratch, fmt=args.format, audio=args.audio,
        creator=args.creator, od=args.od, hp=args.hp, encoding=args.encoding,
    )

    # unique output names per folder
    used: Dict[str, int] = {}
    jobs_list = []
    for folder, files in groups.items():
        base = safe_filename(folder.name)
        n = used.get(base, 0)
        used[base] = n + 1
        jobs_list.append((str(folder), files, args.output, base if n == 0 else f"{base}_{n + 1}"))

    workers = args.jobs or min(os.cpu_count() or 1, 8)
    results: List[GroupResult] = []
    total = len(jobs_list)
    layout = "7키(스크래치 제거)" if args.remove_scratch else "8키(스크래치 포함)"
    print(f"{total}개 폴더, 파일 {sum(len(f) for _, f, _, _ in jobs_list)}개 변환 시작 - {layout}")

    def report(i: int, r: GroupResult) -> None:
        status = f"-> {r.output}" if r.output else f"실패: {r.error}"
        print(f"[{i}/{total}] {r.folder}\n        채보 {r.charts}개 {status}")
        for w in r.warnings:
            print(f"        [경고] {w}")

    if workers <= 1 or total == 1:
        for i, job in enumerate(jobs_list, 1):
            r = process_group(*job, opts)
            results.append(r)
            report(i, r)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(process_group, *job, opts): job for job in jobs_list}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    r = fut.result()
                except Exception as e:  # worker crashed
                    r = GroupResult(folder=futs[fut][0], error=f"{type(e).__name__}: {e}")
                results.append(r)
                report(i, r)

    ok = sum(1 for r in results if r.output)
    print(f"\n완료: 성공 {ok} / 실패 {total - ok} / 채보 {sum(r.charts for r in results)}개")
    _pause_if_needed()
    return 0 if ok == total else 1
