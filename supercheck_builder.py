# supercheck_builder_v3.py
# CTESTWIN 向け「パーシャルチェックリスト」を作る簡易ツール（Turbo HAMLOG CSV + 既存リストをマージ）
#
# 目的:
# - Turbo HAMLOG が出力した CSV から「国内局(JCC/JCG が入っている行)」だけ拾う
# - 既存のパーシャルチェックリスト(txt)とマージ（既存は任意）
# - コールサインでソートし、重複を削除（同一コールは最新(=CSV側)で上書き）
#
# 動作要件:
# - Windows + Python 3.9+ 推奨
# - Tkinter が入っている Python（通常の python.org 版はOK）
#
# 出力形式（CTESTWINのパーシャルチェック）:
# CALL<space>JCC/JCG
# 例: 7J1ADJ/6 47003G

from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# --- 正規表現（ゆるめに） -------------------------------------------------

_CALL_CAND_RE = re.compile(r"^[A-Z0-9/]+$")
_HAS_ALPHA_RE = re.compile(r"[A-Z]")
_HAS_DIGIT_RE = re.compile(r"\d")
_JCCJCG_RE = re.compile(r"^\d{4,6}[A-Z]?$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$|^\d{4}/\d{2}/\d{2}$")
_CALL_HEADERS = {"CALL", "CALLSIGN", "CALLSIGN ", "CALLSIGN\t", "コール", "コールサイン", "CALLSIGN1"}
_QTH_HEADERS  = {"JCC", "JCG", "JCC/JCG", "JCCJCG", "QTH", "市郡", "QTH1", "QRA", "LOC"}


def _strip_cell(s: str) -> str:
    return s.strip().strip('"').strip()


def _norm_call(s: str) -> str:
    return _strip_cell(s).upper()


def _norm_exch(s: str) -> str:
    t = _strip_cell(s).upper()
    t = t.strip(",;")
    return t


def _is_callsign(s: str) -> bool:
    if not s:
        return False
    if not _CALL_CAND_RE.match(s):
        return False
    if not _HAS_ALPHA_RE.search(s) or not _HAS_DIGIT_RE.search(s):
        return False
    return True


def _is_jccjcg(s: str) -> bool:
    if not s:
        return False
    if _DATE_RE.match(s):
        return False
    if _JCCJCG_RE.match(s):
        if set(s.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) == {"0"}:
            return False
        return True
    return False


def _sniff_delimiter(sample: str) -> str:
    for cand in [",", "\t", ";"]:
        if sample.count(cand) >= 3:
            return cand
    return ","


def _read_text_any_encoding(path: Path) -> str:
    for enc in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def read_existing_supercheck(path: Path) -> Tuple[Dict[str, str], List[str]]:
    mapping: Dict[str, str] = {}
    header: List[str] = []
    if not path.exists():
        return mapping, header
    for raw in _read_text_any_encoding(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//") or line.startswith("#") or line.startswith(";"):
            header.append(raw.rstrip("\n"))
            continue
        parts = line.split()
        call = _norm_call(parts[0])
        if not _is_callsign(call):
            continue
        exch = _norm_exch(" ".join(parts[1:])) if len(parts) > 1 else ""
        mapping[call] = exch
    return mapping, header


def _header_index(row: List[str], candidates: Iterable[str]) -> Optional[int]:
    norm = [_strip_cell(c).upper() for c in row]
    cand = {c.upper() for c in candidates}
    for i, v in enumerate(norm):
        if v in cand:
            return i
    return None


def read_hamlog_csv_calls(csv_path: Path, keep_domestic_only: bool = True) -> Dict[str, str]:
    text = _read_text_any_encoding(csv_path)
    lines = text.splitlines()
    if not lines:
        return {}
    delim = _sniff_delimiter("\n".join(lines[:30]))
    reader = csv.reader(lines, delimiter=delim)
    out: Dict[str, str] = {}
    header_row: Optional[List[str]] = None
    call_idx: Optional[int] = None
    qth_idx: Optional[int] = None
    for ridx, row in enumerate(reader):
        if not row:
            continue
        row = [_strip_cell(c) for c in row]
        if ridx == 0:
            if any(_strip_cell(c).upper() in {"CALL", "CALLSIGN", "コールサイン"} for c in row):
                header_row = row
                call_idx = _header_index(header_row, _CALL_HEADERS)
                qth_idx  = _header_index(header_row, _QTH_HEADERS)
                continue
        call: Optional[str] = None
        if call_idx is not None and call_idx < len(row):
            cand = _norm_call(row[call_idx])
            if _is_callsign(cand):
                call = cand
        if call is None:
            for c in row:
                cand = _norm_call(c)
                if _is_callsign(cand):
                    call = cand
                    break
        if call is None:
            continue
        exch: str = ""
        if qth_idx is not None and qth_idx < len(row):
            cand = _norm_exch(row[qth_idx])
            if _is_jccjcg(cand):
                exch = cand
        if not exch:
            for c in row:
                cand = _norm_exch(c)
                if _is_jccjcg(cand):
                    exch = cand
                    break
        if keep_domestic_only and not exch:
            continue
        if exch:
            out[call] = exch
        else:
            out.setdefault(call, "")
    return out


def write_supercheck(path: Path, mapping: Dict[str, str], header_lines: Optional[List[str]] = None) -> None:
    header_lines = header_lines or []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for h in header_lines:
            f.write(h.rstrip("\n") + "\n")
        for call in sorted(mapping.keys()):
            exch = mapping[call].strip()
            if exch:
                f.write(f"{call} {exch}\n")
            else:
                f.write(f"{call}\n")


# --- GUI -------------------------------------------------------------------

@dataclass
class Paths:
    hamlog_csv: Path
    existing_list: Path
    out_list: Path


def _pick_file(title: str, filetypes: List[Tuple[str, str]]) -> Optional[str]:
    from tkinter import filedialog
    return filedialog.askopenfilename(title=title, filetypes=filetypes)


def _pick_save(title: str, defaultextension: str, filetypes: List[Tuple[str, str]], initialdir: Optional[str] = None, initialfile: Optional[str] = None) -> Optional[str]:
    from tkinter import filedialog
    return filedialog.asksaveasfilename(title=title, defaultextension=defaultextension, filetypes=filetypes, initialdir=initialdir, initialfile=initialfile)


def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("SuperCheck Builder (Hamlog CSV → CTESTWIN パーシャル)")

    v_csv = tk.StringVar()
    v_exist = tk.StringVar()
    v_out = tk.StringVar()
    v_domestic = tk.BooleanVar(value=True)
    v_out_fmt = tk.StringVar(value=".spc")

    pad = {"padx": 8, "pady": 6}
    frm = tk.Frame(root)
    frm.pack(fill="both", expand=True, **pad)

    def row(y: int, label: str, var: tk.StringVar, btn_text: str, cmd):
        tk.Label(frm, text=label, anchor="w").grid(row=y, column=0, sticky="w")
        tk.Entry(frm, textvariable=var, width=70).grid(row=y, column=1, sticky="we", padx=6)
        tk.Button(frm, text=btn_text, command=cmd).grid(row=y, column=2, sticky="e")

    frm.columnconfigure(1, weight=1)

    # 既存ファイル用の filetypes（.spc/.pck を先頭に、txt と All files は残す）
    def _filetypes_for_existing() -> List[Tuple[str, Tuple[str, ...]]]:
        return [
            ("SuperCheck/CTESTWIN (*.spc, *.pck)", ("*.spc", "*.pck")),
            ("Text (*.txt, *.lst, *.dat)", ("*.txt", "*.lst", "*.dat")),
            ("All files", ("*.*",)),
        ]

    def _filetypes_for_ext(ext: str) -> List[Tuple[str, str]]:
        if ext == ".spc":
            return [("zLog SuperCheck (*.spc)", "*.spc"), ("CTESTWIN Partial (*.pck)", "*.pck"), ("All files", "*.*")]
        else:
            return [("CTESTWIN Partial (*.pck)", "*.pck"), ("zLog SuperCheck (*.spc)", "*.spc"), ("All files", "*.*")]

    def _replace_out_ext(path_str: str, new_ext: str) -> str:
        if not path_str:
            return "supercheck" + new_ext
        try:
            p = Path(path_str)
            return str(p.with_suffix(new_ext))
        except Exception:
            if "." in path_str:
                return path_str.rsplit(".", 1)[0] + new_ext
            else:
                return path_str + new_ext

    def on_out_format_change(*_args):
        cur = v_out.get()
        new = _replace_out_ext(cur, v_out_fmt.get())
        v_out.set(new)

    def pick_csv():
        p = _pick_file("Turbo HAMLOG CSV を選択", [("CSV", ("*.csv",)), ("All files", ("*.*",))])
        if p:
            v_csv.set(p)
            cur_out = v_out.get().strip()
            ext = v_out_fmt.get()
            default_name = "supercheck" + ext
            try:
                if not cur_out or Path(cur_out).name == default_name:
                    ppath = Path(p)
                    new_out = str(ppath.with_suffix(ext))
                    v_out.set(new_out)
            except Exception:
                pass

    # 既存選択: .spc/.pck を優先表示、選択時に拡張子を検出して出力形式を合わせる
    def pick_exist():
        filetypes = _filetypes_for_existing()
        p = _pick_file("既存のパーシャルチェックリストを選択（任意）", filetypes)
        if p:
            v_exist.set(p)
            try:
                ext = Path(p).suffix.lower()
                if ext in (".spc", ".pck"):
                    v_out_fmt.set(ext)
                    v_out.set(_replace_out_ext(v_out.get(), ext))
            except Exception:
                pass

    def pick_out():
        ext = v_out_fmt.get()
        def_ext = ext
        filetypes = _filetypes_for_ext(ext)
        initialdir = None
        initialfile = None
        cur = v_out.get().strip()
        if cur:
            try:
                p = Path(cur)
                if p.parent.exists():
                    initialdir = str(p.parent)
                initialfile = p.name
            except Exception:
                initialfile = Path(cur).name
        else:
            initialfile = "supercheck" + ext
        p = _pick_save("出力先を指定", def_ext, filetypes, initialdir=initialdir, initialfile=initialfile)
        if p:
            v_out.set(p)

    row(0, "① HAMLOG CSV（今回の追加分）", v_csv, "参照…", pick_csv)
    row(1, "② 既存パーシャルリスト（マージ元、任意）", v_exist, "参照…", pick_exist)
    tk.Button(frm, text="クリア", command=lambda: v_exist.set("")).grid(row=1, column=3, padx=4)
    row(2, "③ 出力ファイル（上書き/新規）", v_out, "保存先…", pick_out)

    frm_fmt = tk.Frame(frm)
    frm_fmt.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 2))
    tk.Label(frm_fmt, text="出力形式:").pack(side="left")
    tk.Radiobutton(frm_fmt, text="zLog (.spc)", variable=v_out_fmt, value=".spc", command=on_out_format_change).pack(side="left", padx=6)
    tk.Radiobutton(frm_fmt, text="CTESTWIN (.pck)", variable=v_out_fmt, value=".pck", command=on_out_format_change).pack(side="left", padx=6)

    v_domestic_cb_row = 4
    tk.Checkbutton(frm, text="国内局のみ（JCC/JCG がある行だけ採用）", variable=v_domestic).grid(row=v_domestic_cb_row, column=1, sticky="w", pady=4)

    log = tk.Text(frm, height=10, width=90)
    log.grid(row=v_domestic_cb_row + 1, column=0, columnspan=4, sticky="nsew", pady=6)
    frm.rowconfigure(v_domestic_cb_row + 1, weight=1)

    def write_log(s: str):
        log.insert("end", s + "\n")
        log.see("end")

    def on_run():
        try:
            csv_path = Path(v_csv.get()).expanduser()
            out_path = Path(v_out.get()).expanduser()

            if not csv_path.exists():
                messagebox.showerror("エラー", "HAMLOG CSV が見つかりません。")
                return

            exist_val = v_exist.get().strip()
            existing_map: Dict[str, str] = {}
            header: List[str] = []
            if exist_val:
                exist_path = Path(exist_val).expanduser()
                if exist_path.exists():
                    write_log(f"[1] 既存リスト読込: {exist_path}")
                    existing_map, header = read_existing_supercheck(exist_path)
                    write_log(f"    既存: {len(existing_map)} 件")
                else:
                    resp = messagebox.askyesno("確認", f"既存リスト {exist_path} が見つかりません。\n新規作成として続行しますか？")
                    if not resp:
                        return
                    write_log(f"[1] 既存リストが見つからなかったため、新規作成扱いで続行します: {exist_path}")
                    existing_map, header = {}, []
            else:
                write_log("[1] 既存リスト未指定 → 新規作成扱い (初回作成)")

            if not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)

            write_log(f"[2] CSV 読込: {csv_path}")
            new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=bool(v_domestic.get()))
            write_log(f"    CSV抽出: {len(new_map)} 件")

            merged = dict(existing_map)
            merged.update(new_map)

            write_log(f"[3] マージ後: {len(merged)} 件（重複は自動で整理）")

            write_log(f"[4] 書き出し: {out_path}")
            write_supercheck(out_path, merged, header_lines=[])
            write_log("    完了")

            messagebox.showinfo("完了", f"出力しました:\n{out_path}\n\n件数: {len(merged)}")
        except Exception as e:
            messagebox.showerror("例外", f"{type(e).__name__}: {e}")
            write_log(f"!! {type(e).__name__}: {e}")

    btn = tk.Button(frm, text="生成（マージ→ソート→重複削除）", command=on_run, height=2)
    btn.grid(row=v_domestic_cb_row + 2, column=0, columnspan=4, sticky="we", pady=8)

    root.minsize(900, 450)
    root.mainloop()


def main(argv: List[str]) -> int:
    if len(argv) == 1:
        run_gui()
        return 0

    if len(argv) != 4:
        print("使い方: python supercheck_builder_v3.py <hamlog.csv> <existing.txt_or_empty_or-> <out.txt_or_auto>")
        print("  - 既存ファイルは任意です。存在しない場合は新規作成扱いになります。")
        print("  - 出力ファイルに 'auto' を指定すると CSV 名を元に自動生成 (.spc)。")
        print("  - 'auto.pck' を指定すると CSV 名に .pck を付けたファイルが生成されます。")
        return 2

    csv_path = Path(argv[1])
    exist_arg = argv[2]
    out_arg = argv[3]

    if not csv_path.exists():
        print("ERROR: hamlog.csv が見つかりません。")
        return 2

    # 出力自動生成ロジック（CLI）
    out_path: Path
    if out_arg in ("", "-", "auto"):
        out_path = csv_path.with_suffix(".spc")
    elif out_arg.lower().startswith("auto."):
        ext = "." + out_arg.split(".", 1)[1]
        out_path = csv_path.with_suffix(ext)
    else:
        out_path = Path(out_arg)

    # 既存ファイルは任意。存在しない場合は新規扱い。
    exist_path = Path(exist_arg) if exist_arg not in ("", "-") else None

    if exist_path and exist_path.exists():
        existing_map, _ = read_existing_supercheck(exist_path)
    else:
        existing_map = {}

    new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=True)

    merged = dict(existing_map)
    merged.update(new_map)
    write_supercheck(out_path, merged, header_lines=[])
    print(f"OK: {out_path} ({len(merged)}件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))