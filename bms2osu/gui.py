"""Desktop GUI: drag & drop BMS folders, tick options, press convert."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .batch import GroupResult, Options
from .runner import collect, default_workers, plan_jobs, run_jobs

try:  # native drag & drop (optional dependency)
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - depends on the environment
    TkinterDnD = None
    DND_FILES = None

ENCODINGS = ("utf-8", "cp932", "cp949", "gb18030")


def default_output_dir() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "bms2osu_output"


def open_in_file_manager(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk, initial: Optional[List[str]] = None) -> None:
        self.root = root
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.cancel = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.paths: List[str] = []

        root.title(f"bms2osu {__version__} - BMS → osu!mania 변환기")
        root.minsize(640, 640)
        root.geometry("760x760")

        main = ttk.Frame(root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)

        self._build_drop_area(main)
        self._build_list(main)
        self._build_options(main)
        self._build_actions(main)
        self._build_log(main)

        if initial:
            self.add_paths(initial)
        self._update_state()
        root.after(100, self._poll)

    # ---------------------------------------------------------------- layout
    def _build_drop_area(self, parent) -> None:
        text = "BMS 폴더를 여기로 끌어다 놓으세요"
        if TkinterDnD is None:
            text = "드래그 앤 드롭을 사용할 수 없습니다 (tkinterdnd2 미설치)\n'폴더 추가' 버튼을 이용하세요"
        self.drop = tk.Label(
            parent, text=text, relief="groove", borderwidth=2, height=4, cursor="hand2",
        )
        self.drop.grid(row=0, column=0, sticky="ew")
        self._drop_bg = self.drop.cget("background")
        self.drop.bind("<Button-1>", lambda _e: self.browse_folder())
        if TkinterDnD is not None:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
            self.drop.dnd_bind("<<DropEnter>>", lambda e: self._highlight(True) or e.action)
            self.drop.dnd_bind("<<DropLeave>>", lambda e: self._highlight(False) or e.action)

    def _build_list(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="변환할 폴더", padding=6)
        box.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(box, selectmode="extended", height=6, activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)
        btns = ttk.Frame(box)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="폴더 추가...", command=self.browse_folder).pack(side="left")
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="모두 지우기", command=self.clear_paths).pack(side="left")
        self.count_label = ttk.Label(btns, text="")
        self.count_label.pack(side="right")
        self.listbox.bind("<Delete>", lambda _e: self.remove_selected())
        if TkinterDnD is not None:  # the list also accepts drops
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

    def _build_options(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="옵션", padding=8)
        box.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(1, weight=1)

        self.v_scratch = tk.BooleanVar(value=False)
        self.v_recursive = tk.BooleanVar(value=True)
        self.v_osz = tk.BooleanVar(value=True)
        self.v_parallel = tk.BooleanVar(value=True)
        self.v_open = tk.BooleanVar(value=True)
        self.v_keysound = tk.BooleanVar(value=True)

        simple = ttk.Frame(box)
        simple.grid(row=0, column=0, columnspan=3, sticky="ew")
        for i, (var, label) in enumerate([
            (self.v_keysound, "키음을 하나의 음원으로 합성 (권장)"),
            (self.v_scratch, "스크래치 제거 (7키 / 더블 14키)"),
            (self.v_recursive, "하위 폴더까지 검색"),
            (self.v_osz, ".osz 패키지로 저장 (해제 시 .osu 폴더)"),
            (self.v_parallel, "병렬 처리 (빠름)"),
            (self.v_open, "변환 후 출력 폴더 열기"),
        ]):
            ttk.Checkbutton(simple, text=label, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=2)

        ttk.Separator(box).grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)

        # optional values: checkbox enables the field
        self.v_out_on = tk.BooleanVar(value=False)
        self.v_out = tk.StringVar(value=str(default_output_dir()))
        self.v_creator_on = tk.BooleanVar(value=False)
        self.v_creator = tk.StringVar(value="bms2osu")
        self.v_diff_on = tk.BooleanVar(value=False)
        self.v_od = tk.DoubleVar(value=8.0)
        self.v_hp = tk.DoubleVar(value=8.0)
        self.v_audio_on = tk.BooleanVar(value=False)
        self.v_audio = tk.StringVar(value="")
        self.v_enc_on = tk.BooleanVar(value=False)
        self.v_enc = tk.StringVar(value=ENCODINGS[1])

        self._toggles = []
        row = 2

        def add_row(var, label, widgets):
            nonlocal row
            ttk.Checkbutton(box, text=label, variable=var, command=self._update_state).grid(
                row=row, column=0, sticky="w", pady=2)
            frame = ttk.Frame(box)
            frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
            made = [w(frame) for w in widgets]
            self._toggles.append((var, made))
            row += 1

        add_row(self.v_out_on, "출력 폴더 지정", [
            lambda f: _pack(ttk.Entry(f, textvariable=self.v_out), fill="x", expand=True),
            lambda f: _pack(ttk.Button(f, text="찾아보기", command=self.browse_output), padx=(6, 0)),
        ])
        add_row(self.v_creator_on, "제작자 이름 지정", [
            lambda f: _pack(ttk.Entry(f, textvariable=self.v_creator, width=24)),
        ])
        add_row(self.v_diff_on, "OD / HP 직접 지정", [
            lambda f: _pack(ttk.Label(f, text="OD")),
            lambda f: _pack(ttk.Spinbox(f, from_=0, to=10, increment=0.5, width=6,
                                        textvariable=self.v_od), padx=(4, 12)),
            lambda f: _pack(ttk.Label(f, text="HP")),
            lambda f: _pack(ttk.Spinbox(f, from_=0, to=10, increment=0.5, width=6,
                                        textvariable=self.v_hp), padx=(4, 0)),
        ])
        add_row(self.v_audio_on, "오디오 파일 지정", [
            lambda f: _pack(ttk.Entry(f, textvariable=self.v_audio), fill="x", expand=True),
            lambda f: _pack(ttk.Label(f, text="(각 폴더 기준 파일명, 키음 합성 대신 사용)", foreground="gray"), padx=(6, 0)),
        ])
        add_row(self.v_enc_on, "인코딩 강제 지정", [
            lambda f: _pack(ttk.Combobox(f, textvariable=self.v_enc, values=ENCODINGS,
                                         width=12, state="readonly")),
        ])
        hint = "체크하지 않은 항목은 기본값 사용: 출력 폴더 " + str(default_output_dir()) + \
               ", 제작자 bms2osu, OD/HP 8, 인코딩 자동"
        ttk.Label(box, text=hint, foreground="gray", wraplength=680).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_actions(self, parent) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        bar.columnconfigure(2, weight=1)
        self.btn_start = ttk.Button(bar, text="▶  변환 시작", command=self.start)
        self.btn_start.grid(row=0, column=0, ipadx=12, ipady=4)
        self.btn_stop = ttk.Button(bar, text="중지", command=self.stop)
        self.btn_stop.grid(row=0, column=1, padx=6, ipady=4)
        self.progress = ttk.Progressbar(bar, mode="determinate")
        self.progress.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.status = ttk.Label(parent, text="대기 중")
        self.status.grid(row=4, column=0, sticky="w", pady=(4, 0))

    def _build_log(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="로그", padding=6)
        box.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log = tk.Text(box, height=8, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("err", foreground="#c0392b")
        self.log.tag_configure("warn", foreground="#b9770e")
        self.log.tag_configure("ok", foreground="#1e8449")

    # ----------------------------------------------------------- list ops
    def _highlight(self, on: bool) -> None:
        self.drop.configure(background="#d6eaf8" if on else self._drop_bg)

    def _on_drop(self, event):
        self._highlight(False)
        self.add_paths(self.root.tk.splitlist(event.data))
        return event.action

    def add_paths(self, paths) -> None:
        if self._busy():
            return
        added = 0
        for p in paths:
            p = str(Path(p))
            if p and p not in self.paths:
                self.paths.append(p)
                self.listbox.insert("end", p)
                added += 1
        if added:
            self.write(f"{added}개 항목 추가됨")
        self._update_state()

    def browse_folder(self) -> None:
        d = filedialog.askdirectory(title="BMS 폴더 선택", mustexist=True)
        if d:
            self.add_paths([d])

    def browse_output(self) -> None:
        d = filedialog.askdirectory(title="출력 폴더 선택")
        if d:
            self.v_out.set(d)
            self.v_out_on.set(True)
            self._update_state()

    def remove_selected(self) -> None:
        if self._busy():
            return
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.paths[i]
        self._update_state()

    def clear_paths(self) -> None:
        if self._busy():
            return
        self.listbox.delete(0, "end")
        self.paths.clear()
        self._update_state()

    # ------------------------------------------------------------ helpers
    def _busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _update_state(self) -> None:
        busy = self._busy()
        for var, widgets in self._toggles:
            st = "normal" if var.get() and not busy else "disabled"
            for w in widgets:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if st == "normal" else "disabled")
                elif not isinstance(w, ttk.Label):
                    w.configure(state=st)
        self.btn_start.configure(state="disabled" if busy or not self.paths else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.count_label.configure(text=f"{len(self.paths)}개")

    def write(self, msg: str, tag: str = "") -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _options(self) -> Optional[Options]:
        try:
            od = float(self.v_od.get()) if self.v_diff_on.get() else 8.0
            hp = float(self.v_hp.get()) if self.v_diff_on.get() else 8.0
        except (tk.TclError, ValueError):
            messagebox.showerror("bms2osu", "OD / HP 값은 숫자여야 합니다.")
            return None
        audio = self.v_audio.get().strip() if self.v_audio_on.get() else None
        creator = self.v_creator.get().strip() if self.v_creator_on.get() else ""
        return Options(
            remove_scratch=self.v_scratch.get(),
            fmt="osz" if self.v_osz.get() else "osu",
            audio=audio or None,
            creator=creator or "bms2osu",
            od=max(0.0, min(10.0, od)),
            hp=max(0.0, min(10.0, hp)),
            encoding=self.v_enc.get() if self.v_enc_on.get() else None,
            render_keysounds=self.v_keysound.get(),
        )

    def _output_dir(self) -> Path:
        if self.v_out_on.get() and self.v_out.get().strip():
            return Path(self.v_out.get().strip())
        return default_output_dir()

    # ------------------------------------------------------------ convert
    def start(self) -> None:
        if self._busy() or not self.paths:
            return
        opts = self._options()
        if opts is None:
            return
        out = self._output_dir()
        groups, warnings = collect(self.paths, self.v_recursive.get())
        for w in warnings:
            self.write(f"[경고] {w}", "warn")
        if not groups:
            self.write("변환할 BMS/BME/BML 파일을 찾지 못했습니다.", "err")
            messagebox.showwarning("bms2osu", "변환할 BMS/BME/BML 파일을 찾지 못했습니다.")
            return
        jobs = plan_jobs(groups, str(out))
        workers = default_workers() if self.v_parallel.get() else 1
        layout = "7키(스크래치 제거)" if opts.remove_scratch else "8키(스크래치 포함)"
        self.write(f"── {len(jobs)}개 폴더 변환 시작 - {layout}, 출력: {out}")
        self.progress.configure(maximum=len(jobs), value=0)
        self.status.configure(text=f"변환 중... 0 / {len(jobs)}")
        self.cancel.clear()
        self._out = out
        self._total = len(jobs)

        def work():
            try:
                res = run_jobs(jobs, opts, workers,
                               on_result=lambda i, t, r: self.queue.put(("result", i, t, r)),
                               cancel=self.cancel)
                self.queue.put(("done", res))
            except Exception as e:  # pragma: no cover
                self.queue.put(("fatal", f"{type(e).__name__}: {e}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._update_state()

    def stop(self) -> None:
        if self._busy():
            self.cancel.set()
            self.status.configure(text="중지하는 중... (진행 중인 폴더는 마무리됩니다)")

    def _poll(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "result":
                    _, i, t, r = msg
                    self._show_result(r)
                    self.progress.configure(value=i)
                    self.status.configure(text=f"변환 중... {i} / {t}")
                elif msg[0] == "done":
                    self._finish(msg[1])
                elif msg[0] == "fatal":
                    self.write(f"[오류] {msg[1]}", "err")
                    self.status.configure(text="오류로 중단됨")
        except queue.Empty:
            pass
        if self.worker is not None and not self.worker.is_alive() and self.queue.empty():
            self.worker = None
            self._update_state()
        self.root.after(100, self._poll)

    def _show_result(self, r: GroupResult) -> None:
        name = Path(r.folder).name
        if r.output:
            self.write(f"✔ {name}: 채보 {r.charts}개 → {Path(r.output).name}", "ok")
        else:
            self.write(f"✘ {name}: {r.error}", "err")
        for w in r.warnings:
            self.write(f"    [경고] {w}", "warn")

    def _finish(self, results: List[GroupResult]) -> None:
        ok = sum(1 for r in results if r.output)
        charts = sum(r.charts for r in results)
        stopped = self.cancel.is_set() and len(results) < self._total
        head = "중지됨" if stopped else "완료"
        summary = f"{head}: 성공 {ok} / 실패 {len(results) - ok} / 채보 {charts}개"
        self.write(f"── {summary}", "ok" if ok == len(results) else "warn")
        self.status.configure(text=summary)
        if ok and self.v_open.get():
            open_in_file_manager(self._out)


def _pack(widget, **kw):
    widget.pack(side="left", **kw)
    return widget


def main(argv: Optional[List[str]] = None) -> int:
    paths = list(sys.argv[1:] if argv is None else argv)
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if sys.platform.startswith("win") else
                                  "aqua" if sys.platform == "darwin" else "clam")
    except tk.TclError:
        pass
    App(root, paths)
    root.mainloop()
    return 0
