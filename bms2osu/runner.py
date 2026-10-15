"""Shared batch runner used by both the CLI and the GUI."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .batch import GroupResult, Options, process_group
from .osu import safe_filename

BMS_EXTS = {".bms", ".bme", ".bml"}

Job = Tuple[str, List[str], str, str]  # (folder, files, out_dir, out_stem)


def collect(inputs: Iterable[str], recursive: bool) -> Tuple[Dict[Path, List[str]], List[str]]:
    """Group BMS files by their parent folder (one folder = one beatmapset)."""
    groups: Dict[Path, set] = {}
    warnings: List[str] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            files = [f for f in it if f.is_file() and f.suffix.lower() in BMS_EXTS]
            if not files:
                warnings.append(f"BMS 파일이 없는 폴더: {raw}")
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


def plan_jobs(groups: Dict[Path, List[str]], out_dir: str) -> List[Job]:
    """Assign a unique output name to every folder."""
    used: Dict[str, int] = {}
    jobs: List[Job] = []
    for folder, files in groups.items():
        base = safe_filename(folder.name)
        n = used.get(base, 0)
        used[base] = n + 1
        jobs.append((str(folder), files, out_dir, base if n == 0 else f"{base}_{n + 1}"))
    return jobs


def default_workers() -> int:
    return min(os.cpu_count() or 1, 8)


def run_jobs(
    jobs: List[Job],
    opts: Options,
    workers: int = 0,
    on_result: Optional[Callable[[int, int, GroupResult], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> List[GroupResult]:
    """Run jobs (in parallel when useful). on_result(done, total, result) is called per folder."""
    workers = workers or default_workers()
    total = len(jobs)
    results: List[GroupResult] = []

    def emit(r: GroupResult) -> None:
        results.append(r)
        if on_result:
            on_result(len(results), total, r)

    if workers <= 1 or total <= 1:
        for job in jobs:
            if cancel is not None and cancel.is_set():
                break
            emit(process_group(*job, opts))
        return results

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_group, *job, opts): job for job in jobs}
        for fut in as_completed(futs):
            if cancel is not None and cancel.is_set():
                for f in futs:
                    f.cancel()
            if fut.cancelled():
                continue
            try:
                r = fut.result()
            except Exception as e:  # worker crashed
                r = GroupResult(folder=futs[fut][0], error=f"{type(e).__name__}: {e}")
            emit(r)
    return results
