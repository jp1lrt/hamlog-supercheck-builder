# supercheck_builder_v3.py
# CTESTWIN 向け「パーシャルチェックリスト」を作る簡易ツール（Turbo HAMLOG CSV + 既存リストをマージ）
#
# 目的:
# - Turbo HAMLOG が出力した CSV から「国内局(JCC/JCG が入っている行)」だけ拾う
# - 既存のパーシャルチェックリスト(txt)とマージ
# - コールサインでソートし、重複を削除（同一コールは最新(=CSV側)で上書き）
#
# ※ 以前の版で「日付 25/11/16 みたいなのが JCC/JCG の位置に入ってしまう」問題は、
#    CSVの列位置固定(2列目=exchange扱い)だったのが原因です。
#    この版では “行の中から JCC/JCG っぽい値を探索” するため、列順に依存しません。
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

# コールサイン候補:
# - 英字と数字を最低1文字ずつ含む（=日付"25/11/16"は弾ける）
# - 英数と'/'のみ
_CALL_CAND_RE = re.compile(r"^[A-Z0-9/]+$")
_HAS_ALPHA_RE = re.compile(r"[A-Z]")
_HAS_DIGIT_RE = re.compile(r"\d")

# JCC/JCG候補:
# 例: 1338 / 2715 / 110118 / 47003G / 10006A / 100002C 等を許容
# (4〜6桁 + 任意の英字1文字)
_JCCJCG_RE = re.compile(r"^\d{4,6}[A-Z]?$")

# 日付候補（誤検出の代表）
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$|^\d{4}/\d{2}/\d{2}$")

# HAMLOG CSV ヘッダ（あり得そうなもの）
_CALL_HEADERS = {"CALL", "CALLSIGN", "CALLSIGN ", "CALLSIGN\t", "コール", "コールサイン", "CALLSIGN1"}
_QTH_HEADERS  = {"JCC", "JCG", "JCC/JCG", "JCCJCG", "QTH", "市郡", "QTH1", "QRA", "LOC"}


def _strip_cell(s: str) -> str:
    return s.strip().strip('"').strip()


def _norm_call(s: str) -> str:
    return _strip_cell(s).upper()


def _norm_exch(s: str) -> str:
    # 余計な記号を軽く落とす（必要なら調整）
    t = _strip_cell(s).upper()
    # 先頭末尾のカンマ/セミコロン等を除去
    t = t.strip(",;")
    return t


def _is_callsign(s: str) -> bool:
    if not s:
        return False
    if not _CALL_CAND_RE.match(s):
        return False
    # 日付系は弾く（スラッシュがあるだけだとコールにもあり得るので、英字必須）
    if not _HAS_ALPHA_RE.search(s) or not _HAS_DIGIT_RE.search(s):
        return False
    return True


def _is_jccjcg(s: str) -> bool:
    if not s:
        return False
    if _DATE_RE.match(s):
        return False
    if _JCCJCG_RE.match(s):
        # 0000 や 000000 みたいな明らかに無効も弾く
        if set(s.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) == {"0"}:
            return False
        return True
    return False


def _sniff_delimiter(sample: str) -> str:
    """
    ざっくり区切り文字を推定（HAMLOG CSVは通常カンマだが、念のため）
    """
    for cand in [",", "\t", ";"]:
        if sample.count(cand) >= 3:
            return cand
    return ","


def _read_text_any_encoding(path: Path) -> str:
    """
    CSV をなるべく開けるように、よくあるエンコーディングを順番に試す。
    """
    for enc in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    # 最後の手段
    return path.read_text(encoding="utf-8", errors="replace")


def read_existing_supercheck(path: Path) -> Tuple[Dict[str, str], List[str]]:
    """
    既存のパーシャルチェックリストを読む。
    戻り値:
      - mapping: CALL -> exchange（無い場合は空文字）
      - header_lines: コメント行など（必要なら保持。通常は空でOK）
    """
    mapping: Dict[str, str] = {}
    header: List[str] = []

    if not path.exists():
        return mapping, header

    for raw in _read_text_any_encoding(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        # コメント行（必要なら保持）
        if line.startswith("//") or line.startswith("#") or line.startswith(";"):
            header.append(raw.rstrip("\n"))
            continue

        parts = line.split()
        call = _norm_call(parts[0])
        if not _is_callsign(call):
            # 変な行は無視（安全側）
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
    """
    Turbo HAMLOG の CSV から CALL -> JCC/JCG を抽出する。

    keep_domestic_only=True の場合:
      - “JCC/JCGっぽい値が見つかった行” だけを採用（DXは基本捨てる）
    """
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
        # すべて strip
        row = [_strip_cell(c) for c in row]

        # 1行目がヘッダっぽい場合は拾う（CALL が含まれる等）
        if ridx == 0:
            if any(_strip_cell(c).upper() in {"CALL", "CALLSIGN", "コールサイン"} for c in row):
                header_row = row
                call_idx = _header_index(header_row, _CALL_HEADERS)
                qth_idx  = _header_index(header_row, _QTH_HEADERS)
                continue  # ヘッダ行はデータではない

        # --- CALL を決める ---
        call: Optional[str] = None
        if call_idx is not None and call_idx < len(row):
            cand = _norm_call(row[call_idx])
            if _is_callsign(cand):
                call = cand

        if call is None:
            # 行内を総当たり
            for c in row:
                cand = _norm_call(c)
                if _is_callsign(cand):
                    call = cand
                    break

        if call is None:
            continue

        # --- exchange (JCC/JCG) を決める ---
        exch: str = ""
        # まず “QTH/JCC列” が特定できていれば優先
        if qth_idx is not None and qth_idx < len(row):
            cand = _norm_exch(row[qth_idx])
            if _is_jccjcg(cand):
                exch = cand

        # 次に、行内を総当たり（列順に依存しない）
        if not exch:
            for c in row:
                cand = _norm_exch(c)
                if _is_jccjcg(cand):
                    exch = cand
                    break

        # 国内だけ採用するなら、exch が無い行は捨てる
        if keep_domestic_only and not exch:
            continue

        # “最新を優先（CSV側で上書き）”
        if exch:
            out[call] = exch
        else:
            # 国内限定でない場合のみ、exchange無しでも残す
            out.setdefault(call, "")

    return out


def write_supercheck(path: Path, mapping: Dict[str, str], header_lines: Optional[List[str]] = None) -> None:
    """
    CTESTWIN パーシャルチェック形式で保存。
    """
    header_lines = header_lines or []
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="\n") as f:
        # 既存ヘッダを残したい場合（通常は空）
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


def _pick_save(title: str, defaultextension: str, filetypes: List[Tuple[str, str]], initialfile: str = "") -> Optional[str]:
    from tkinter import filedialog
    return filedialog.asksaveasfilename(
        title=title,
        defaultextension=defaultextension,
        filetypes=filetypes,
        initialfile=initialfile
    )


def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("SuperCheck Builder (Hamlog CSV → CTESTWIN パーシャル)")

    # variables
    v_csv = tk.StringVar()
    v_exist = tk.StringVar()
    v_out = tk.StringVar()
    v_domestic = tk.BooleanVar(value=True)
    v_format = tk.StringVar(value=".spc")  # Output format: .spc or .pck

    # layout
    pad = {"padx": 8, "pady": 6}

    frm = tk.Frame(root)
    frm.pack(fill="both", expand=True, **pad)

    def row(y: int, label: str, var: tk.StringVar, btn_text: str, cmd, btn2_text: str = None, cmd2 = None):
        tk.Label(frm, text=label, anchor="w").grid(row=y, column=0, sticky="w")
        tk.Entry(frm, textvariable=var, width=70).grid(row=y, column=1, sticky="we", padx=6)
        tk.Button(frm, text=btn_text, command=cmd).grid(row=y, column=2, sticky="e")
        if btn2_text and cmd2:
            tk.Button(frm, text=btn2_text, command=cmd2).grid(row=y, column=3, sticky="e")

    frm.columnconfigure(1, weight=1)

    def update_output_extension():
        """Update output file extension based on selected format"""
        out_path = v_out.get()
        if out_path:
            p = Path(out_path)
            new_ext = v_format.get()
            new_path = p.with_suffix(new_ext)
            v_out.set(str(new_path))

    def pick_csv():
        p = _pick_file("Turbo HAMLOG CSV を選択", [("CSV", "*.csv"), ("All files", "*.*")])
        if p:
            v_csv.set(p)
            # Auto-generate output path based on CSV name
            csv_path = Path(p)
            out_ext = v_format.get()
            out_path = csv_path.with_suffix(out_ext)
            v_out.set(str(out_path))

    def pick_exist():
        p = _pick_file("既存のパーシャルチェックリストを選択", [
            ("SuperCheck", "*.spc;*.pck"),
            ("Text", "*.txt;*.lst;*.dat"),
            ("All files", "*.*")
        ])
        if p:
            v_exist.set(p)
            # Auto-select format based on existing file extension
            ext = Path(p).suffix.lower()
            if ext in [".spc", ".pck"]:
                v_format.set(ext)
                update_output_extension()

    def clear_exist():
        v_exist.set("")

    def pick_out():
        out_ext = v_format.get()
        # Generate initial filename based on CSV if available
        initial_name = ""
        if v_csv.get():
            csv_path = Path(v_csv.get())
            initial_name = csv_path.stem + out_ext
        
        p = _pick_save(
            "出力先を指定",
            out_ext,
            [("SuperCheck .spc", "*.spc"), ("SuperCheck .pck", "*.pck"), ("Text", "*.txt"), ("All files", "*.*")],
            initialfile=initial_name
        )
        if p:
            v_out.set(p)

    row(0, "① HAMLOG CSV（今回の追加分）", v_csv, "参照…", pick_csv)
    row(1, "② 既存パーシャルリスト（任意）", v_exist, "参照…", pick_exist, "クリア", clear_exist)
    row(2, "③ 出力ファイル（上書き/新規）", v_out, "保存先…", pick_out)

    # Output format radio buttons
    fmt_frame = tk.Frame(frm)
    fmt_frame.grid(row=3, column=1, sticky="w", pady=4)
    tk.Label(fmt_frame, text="出力形式:").pack(side="left", padx=(0, 10))
    tk.Radiobutton(fmt_frame, text=".spc", variable=v_format, value=".spc", command=update_output_extension).pack(side="left", padx=5)
    tk.Radiobutton(fmt_frame, text=".pck", variable=v_format, value=".pck", command=update_output_extension).pack(side="left", padx=5)

    tk.Checkbutton(frm, text="国内局のみ（JCC/JCG がある行だけ採用）", variable=v_domestic).grid(row=4, column=1, sticky="w", pady=4)

    log = tk.Text(frm, height=10, width=90)
    log.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=6)
    frm.rowconfigure(5, weight=1)

    def write_log(s: str):
        log.insert("end", s + "\n")
        log.see("end")

    def on_run():
        try:
            csv_path = Path(v_csv.get()).expanduser()
            exist_path = Path(v_exist.get()).expanduser() if v_exist.get().strip() else None
            out_path = Path(v_out.get()).expanduser()

            if not csv_path.exists():
                messagebox.showerror("エラー", "HAMLOG CSV が見つかりません。")
                return
            
            # Check if existing file is specified and exists
            existing_map = {}
            header = []
            is_initial_creation = False
            
            if exist_path and exist_path != Path("."):
                if not exist_path.exists():
                    # Show confirmation dialog for missing existing file
                    result = messagebox.askyesno(
                        "確認",
                        f"既存パーシャルリストが見つかりません:\n{exist_path}\n\n新規作成で続行しますか？"
                    )
                    if not result:
                        return
                    is_initial_creation = True
                    write_log(f"[1] 既存リストなし（初回作成）")
                else:
                    write_log(f"[1] 既存リスト読込: {exist_path}")
                    existing_map, header = read_existing_supercheck(exist_path)
                    write_log(f"    既存: {len(existing_map)} 件")
            else:
                is_initial_creation = True
                write_log(f"[1] 既存リストなし（初回作成）")

            if not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)

            write_log(f"[2] CSV 読込: {csv_path}")
            new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=bool(v_domestic.get()))
            write_log(f"    CSV抽出: {len(new_map)} 件")

            # merge（CSV側を優先）
            merged = dict(existing_map)
            merged.update(new_map)

            write_log(f"[3] マージ後: {len(merged)} 件（重複は自動で整理）")

            write_log(f"[4] 書き出し: {out_path}")
            # CTESTWINのパーシャルはヘッダ無しの方が安全なので header は基本捨てる
            write_supercheck(out_path, merged, header_lines=[])
            write_log("    完了")

            messagebox.showinfo("完了", f"出力しました:\n{out_path}\n\n件数: {len(merged)}")
        except Exception as e:
            messagebox.showerror("例外", f"{type(e).__name__}: {e}")
            write_log(f"!! {type(e).__name__}: {e}")

    btn = tk.Button(frm, text="生成（マージ→ソート→重複削除）", command=on_run, height=2)
    btn.grid(row=6, column=0, columnspan=4, sticky="we", pady=8)

    root.minsize(900, 450)
    root.mainloop()


def main(argv: List[str]) -> int:
    # CLI でも動かせるように。基本は GUI でOK。
    if len(argv) == 1:
        run_gui()
        return 0

    # CLI mode with flexible arguments
    # Usage patterns:
    # 1. python supercheck_builder.py <csv>                        -> auto-generate output as csv_name.spc
    # 2. python supercheck_builder.py <csv> <out>                  -> output to specified file
    # 3. python supercheck_builder.py <csv> <existing> <out>       -> merge with existing
    # 4. python supercheck_builder.py <csv> auto                   -> auto-generate .spc output
    # 5. python supercheck_builder.py <csv> auto.pck               -> auto-generate .pck output
    # 6. python supercheck_builder.py <csv> -                      -> output to stdout
    # 7. python supercheck_builder.py <csv> <existing> auto        -> merge and auto-generate .spc
    # 8. python supercheck_builder.py <csv> <existing> auto.pck    -> merge and auto-generate .pck
    # 9. python supercheck_builder.py <csv> <existing> -           -> merge and output to stdout

    csv_path = Path(argv[1])
    existing_map = {}
    out_path = None
    
    if len(argv) == 2:
        # Pattern 1: auto-generate .spc output
        out_path = csv_path.with_suffix(".spc")
    elif len(argv) == 3:
        # Pattern 2, 4, 5, 6
        arg2 = argv[2]
        if arg2 == "auto":
            out_path = csv_path.with_suffix(".spc")
        elif arg2 == "auto.pck":
            out_path = csv_path.with_suffix(".pck")
        elif arg2 == "-":
            out_path = None  # stdout
        else:
            out_path = Path(arg2)
    elif len(argv) == 4:
        # Pattern 3, 7, 8, 9
        exist_path = Path(argv[2])
        if exist_path.exists():
            existing_map, _ = read_existing_supercheck(exist_path)
        
        arg3 = argv[3]
        if arg3 == "auto":
            out_path = csv_path.with_suffix(".spc")
        elif arg3 == "auto.pck":
            out_path = csv_path.with_suffix(".pck")
        elif arg3 == "-":
            out_path = None  # stdout
        else:
            out_path = Path(arg3)
    else:
        print("使い方:")
        print("  python supercheck_builder.py                           # GUI起動")
        print("  python supercheck_builder.py <csv>                     # auto生成 (.spc)")
        print("  python supercheck_builder.py <csv> <out>               # 出力先指定")
        print("  python supercheck_builder.py <csv> <existing> <out>    # マージして出力")
        print("")
        print("  <out> には以下を指定可能:")
        print("    auto      : CSV名ベースで .spc を自動生成")
        print("    auto.pck  : CSV名ベースで .pck を自動生成")
        print("    -         : 標準出力")
        print("    ファイル名 : 指定したファイルに出力")
        return 2

    new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=True)

    merged = dict(existing_map)
    merged.update(new_map)
    
    if out_path is None:
        # Output to stdout
        for call in sorted(merged.keys()):
            exch = merged[call].strip()
            if exch:
                print(f"{call} {exch}")
            else:
                print(f"{call}")
    else:
        write_supercheck(out_path, merged, header_lines=[])
        print(f"OK: {out_path} ({len(merged)}件)")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
