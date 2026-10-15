"""Command line interface (python -m bms2osu --help)."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .batch import GroupResult, Options
from .runner import collect, plan_jobs, run_jobs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bms2osu",
        description="BMS/BME/BML 채보를 osu!mania(.osu / .osz)로 일괄 변환합니다. "
        "BMS 파일이 들어 있는 폴더 하나가 비트맵셋(.osz) 하나가 됩니다. "
        "인자 없이 실행하면 GUI 창이 열립니다.",
    )
    p.add_argument("inputs", nargs="*", help="BMS 파일 또는 폴더 (여러 개 가능, 폴더는 하위까지 검색)")
    p.add_argument("-o", "--output", default="output", help="출력 폴더 (기본: ./output)")
    p.add_argument("--remove-scratch", action="store_true",
                   help="스크래치 노트 제거 (7키 / 더블이면 14키). 지정하지 않으면 8키 / 16키")
    p.add_argument("--format", choices=("osz", "osu"), default="osz",
                   help="osz: 오디오 포함 패키지(기본), osu: 폴더에 .osu 파일로 출력")
    p.add_argument("--audio", help="오디오 파일명(폴더 기준) 또는 절대 경로. 지정하면 키음 합성 대신 이 파일 사용")
    p.add_argument("--no-keysound", action="store_true",
                   help="키음 합성을 하지 않고 폴더의 오디오 파일을 그대로 사용")
    p.add_argument("--creator", default="bms2osu", help="채보 제작자 이름 (기본: bms2osu)")
    p.add_argument("--od", type=float, default=None,
                   help="Overall Difficulty 직접 지정 (기본: BMS 판정 #RANK로 자동, 보정을 끄면 8)")
    p.add_argument("--hp", type=float, default=None,
                   help="HP Drain 직접 지정 (기본: BMS 게이지 #TOTAL로 자동, 보정을 끄면 8)")
    p.add_argument("--no-difficulty-fix", action="store_true",
                   help="BMS 난이도 보정 끄기 (난이도 이름·곡 제목·OD·HP를 예전 방식으로)")
    p.add_argument("--encoding", help="BMS 텍스트 인코딩 강제 지정 (기본: 자동 감지)")
    p.add_argument("-j", "--jobs", type=int, default=0, help="병렬 처리 수 (기본: CPU 수, 최대 8)")
    p.add_argument("--no-recursive", action="store_true", help="폴더 하위를 검색하지 않음")
    p.add_argument("--version", action="version", version=f"bms2osu {__version__}")
    return p


def main(argv=None) -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.inputs:
        parser.print_help()
        return 2

    groups, warnings = collect(args.inputs, not args.no_recursive)
    for w in warnings:
        print(f"[경고] {w}")
    if not groups:
        print("변환할 BMS/BME/BML 파일을 찾지 못했습니다.")
        return 1

    opts = Options(
        remove_scratch=args.remove_scratch, fmt=args.format, audio=args.audio,
        creator=args.creator, od=args.od, hp=args.hp, encoding=args.encoding,
        render_keysounds=not args.no_keysound,
        fix_difficulty=not args.no_difficulty_fix,
    )
    jobs = plan_jobs(groups, args.output)
    total = len(jobs)
    layout = "7키(스크래치 제거)" if args.remove_scratch else "8키(스크래치 포함)"
    print(f"{total}개 폴더, 파일 {sum(len(j[1]) for j in jobs)}개 변환 시작 - {layout}")

    def report(i: int, _total: int, r: GroupResult) -> None:
        status = f"-> {r.output}" if r.output else f"실패: {r.error}"
        print(f"[{i}/{total}] {r.folder}\n        채보 {r.charts}개 {status}")
        for w in r.warnings:
            print(f"        [경고] {w}")

    results = run_jobs(jobs, opts, args.jobs, on_result=report)
    ok = sum(1 for r in results if r.output)
    print(f"\n완료: 성공 {ok} / 실패 {total - ok} / 채보 {sum(r.charts for r in results)}개")
    return 0 if ok == total else 1
