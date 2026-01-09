# supercheck_builder_v3.py
# CTESTWIN 向け「パーシャルチェックリスト」を作る簡易ツール（Turbo HAMLOG CSV + 既存リストをマージ）
#
# 目的:
# - Turbo HAMLOG が出力した CSV から「国内局(JCC/JCG が入っている行)」だけ拾う
# - 既存のパーシャルチェックリスト(txt/spc/pck)とマージ（既存は任意）
# - コールサインでソートし、重複を整理
#   - 同一コールの扱いは GUI で選択:
#       1) 上書き（CSV優先。ただし既存がより詳細なら既存を残すオプションあり）
#       2) 追加（既存優先：既存が空の時だけCSVで補完）
#       3) 併記（既存+CSVを両方残す：同一CALLは複数行出力 / 既存→CSV順）
#
# 追加機能:
# - レポートTXT出力（任意）
# - 既存の不完全行（CALLのみ/都道府県2桁）をCSVで補完、無ければ削除（任意）
# - 詳細優先クリーンアップ（任意）:
#     - 同一CALL内に完全JCC/JCGがあれば都道府県2桁は削除
#     - 同一ベース(数字部分が同一)で 09003 と 09003J があれば 09003 を削除（詳細優先）
#     - 上書き時、既存の方が詳細なら既存を残す（任意）
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
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# --- 正規表現（ゆるめに） -------------------------------------------------

_CALL_CAND_RE = re.compile(r"^[A-Z0-9/]+$")
_HAS_ALPHA_RE = re.compile(r"[A-Z]")
_HAS_DIGIT_RE = re.compile(r"\d")

# digits 4-6 + optional alpha
_JCCJCG_RE = re.compile(r"^(?P<num>\d{4,6})(?P<suf>[A-Z]?)$")

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$|^\d{4}/\d{2}/\d{2}$")
_PREF2_RE = re.compile(r"^\d{2}$")  # 都道府県2桁だけ（例: 10）

_CALL_HEADERS = {"CALL", "CALLSIGN", "CALLSIGN ", "CALLSIGN\t", "コール", "コールサイン", "CALLSIGN1"}
_QTH_HEADERS = {"JCC", "JCG", "JCC/JCG", "JCCJCG", "QTH", "市郡", "QTH1", "QRA", "LOC"}

# 複数QTH対応: CALL -> [exch1, exch2, ...]
ExchMap = Dict[str, List[str]]


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


def _is_pref2(s: str) -> bool:
    s = _norm_exch(s)
    return bool(_PREF2_RE.match(s))


def _is_jccjcg(s: str) -> bool:
    """
    JCC/JCG 判定:
    - 空文字は False
    - 日付パターンにマッチするものは False
    - 4〜6桁の数字 + 末尾英字(任意) を有効
    - ただし "0000" 相当のゼロだけは除外
    """
    if not s:
        return False
    s = _norm_exch(s)
    if _DATE_RE.match(s):
        return False
    if "/" in s or ":" in s:
        return False
    m = _JCCJCG_RE.match(s)
    if not m:
        return False
    num = m.group("num")
    # 0だけの文字列（"0000"等）を除外
    if set(num) == {"0"}:
        return False
    return True


def _split_num_suffix(exch: str) -> Tuple[str, str]:
    """
    exch を (数字部, 末尾英字部) に分ける。
    _is_jccjcg を満たすものだけ渡す想定。
    """
    exch = _norm_exch(exch)
    m = _JCCJCG_RE.match(exch)
    if not m:
        return "", ""
    return m.group("num"), m.group("suf") or ""


def _normalize_base_digits(num: str) -> str:
    """
    数字部の「ベース」を正規化:
    - 6桁で 先頭2桁(都道府県)の次が 0 の場合、PP0NNN -> PPNNN に変換（よくある揺れ対策）
      例: 290012 -> 29012（pref=29, '0' を落とす）
    - それ以外はそのまま
    """
    if len(num) == 6 and num[2] == "0":
        return num[:2] + num[3:]
    return num


def _base_key(exch: str) -> Tuple[int, str]:
    """
    比較用キー: (正規化ベースをint化, suffix)
    suffixはそのまま。ベースintで同一判定しやすくする。
    """
    num, suf = _split_num_suffix(exch)
    base = _normalize_base_digits(num)
    try:
        return int(base), suf
    except ValueError:
        return 0, suf


def _detail_score(exch: str) -> int:
    """
    詳細度スコア:
    - 末尾英字ありを強く優先
    - 数字部は正規化ベース長で微調整
    """
    num, suf = _split_num_suffix(exch)
    base = _normalize_base_digits(num)
    score = len(base)
    if suf:
        score += 100
    return score


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


def _add_exch(mapping: ExchMap, call: str, exch: str) -> None:
    """call に exch を重複なしで追加（順序保持）"""
    call = _norm_call(call)
    exch = _norm_exch(exch)
    lst = mapping.setdefault(call, [])
    if not exch:
        return
    if exch not in lst:
        lst.append(exch)


def _fmt_exchs(exchs: List[str]) -> str:
    return ", ".join(exchs) if exchs else ""


def _only_incomplete(exchs: List[str]) -> Tuple[bool, str]:
    """
    既存の交換情報が「不完全のみ」なら True を返す。
    - []          -> True, "blank"
    - ["10"]      -> True, "pref2"
    - ["10","11"] -> True, "pref2"
    - ["100115"]  -> False, ""
    - ["10","100115"] -> False, ""  (完全が混じるなら不完全扱いしない)
    """
    if not exchs:
        return True, "blank"
    has_full = any(_is_jccjcg(x) for x in exchs)
    if has_full:
        return False, ""
    if all(_is_pref2(x) for x in exchs):
        return True, "pref2"
    # その他（形式不明）は安全側で「不完全扱いしない」
    return False, ""


def cleanup_incomplete_existing(existing_map: ExchMap, new_map: ExchMap) -> Tuple[ExchMap, List[str], List[str]]:
    """
    既存に「CALLのみ」または「都道府県2桁のみ」しかない局を処理する:
      a. CSVにJCC/JCGがあれば補完（置換）
      b. CSVにJCC/JCGがなければ削除
    戻り値: (更新済existing_map, 補完されたCALL一覧, 削除されたCALL一覧)
    """
    updated: ExchMap = {k: list(v) for k, v in existing_map.items()}
    filled: List[str] = []
    removed: List[str] = []

    for call in list(updated.keys()):
        exchs = updated.get(call, [])
        is_incomp, _kind = _only_incomplete(exchs)
        if not is_incomp:
            continue

        csv_exchs = new_map.get(call, [])
        fulls = [x for x in csv_exchs if _is_jccjcg(x)]
        if fulls:
            updated[call] = []
            for x in fulls:
                _add_exch(updated, call, x)
            filled.append(call)
        else:
            del updated[call]
            removed.append(call)

    return updated, filled, removed


def detail_cleanup_map(mapping: ExchMap) -> Tuple[ExchMap, Dict[str, Dict[str, List[str]]]]:
    """
    詳細優先クリーンアップ（CALLごと）:
    - 同一CALL内に完全JCC/JCGがあれば都道府県2桁は削除
    - 同一ベース（正規化ベース）が同じで、suffix付きがあれば suffix無しは削除
    - PP0NNN のような揺れはベース同一として扱い、より妥当な表記を残す（同一詳細なら短い方を優先）
    戻り値: (cleaned_map, changes)
      changes[call] = {"removed_pref2": [...], "removed_less_detail": [...]} など
    """
    cleaned: ExchMap = {}
    changes: Dict[str, Dict[str, List[str]]] = {}

    for call, exchs in mapping.items():
        removed_pref2: List[str] = []
        removed_less_detail: List[str] = []

        fulls = [x for x in exchs if _is_jccjcg(x)]
        pref2s = [x for x in exchs if _is_pref2(x)]
        others = [x for x in exchs if (not _is_jccjcg(x) and not _is_pref2(x))]

        # 1) fullがあるならpref2を削除
        if fulls and pref2s:
            removed_pref2.extend(pref2s)
            pref2s = []

        # 2) fullsの中で「同一ベース」はまとめて詳細優先
        #   - ベースごとに (suffixあり群, suffixなし群) を分け
        #   - suffixありが1つでもあれば suffixなしは削除
        #   - suffixなしだけの場合、同一ベースで表記揺れ(6桁/5桁等)があれば
        #       detailスコア同一なら「文字列が短い方」を優先して1つに絞る
        by_base: Dict[int, List[str]] = {}
        for x in fulls:
            base_int, _suf = _base_key(x)
            by_base.setdefault(base_int, []).append(x)

        kept_fulls: List[str] = []
        for base_int, items in by_base.items():
            with_suf = [x for x in items if _split_num_suffix(x)[1]]
            no_suf = [x for x in items if not _split_num_suffix(x)[1]]

            if with_suf:
                # suffix付きは全て残す（複数あってもOK）
                kept_fulls.extend(_stable_unique(with_suf))
                # suffixなしは削除
                removed_less_detail.extend(no_suf)
            else:
                # suffixなしのみ：表記揺れがある場合は「より良い1つ」を選ぶ
                if len(no_suf) <= 1:
                    kept_fulls.extend(no_suf)
                else:
                    # detailスコア（通常は同じ）→短い表記優先→辞書順
                    best = sorted(
                        no_suf,
                        key=lambda s: (-_detail_score(s), len(s), s),
                    )[0]
                    kept_fulls.append(best)
                    for x in no_suf:
                        if x != best:
                            removed_less_detail.append(x)

        # 3) 元の順序をなるべく維持しつつ、残すものを構築
        #    - まず元exchsの順に、残す対象だけ追加（stable）
        keep_set = set(pref2s) | set(kept_fulls) | set(others)
        new_list: List[str] = []
        for x in exchs:
            if x in keep_set and x not in new_list:
                new_list.append(x)

        cleaned[call] = new_list

        if removed_pref2 or removed_less_detail:
            changes[call] = {
                "removed_pref2": removed_pref2,
                "removed_less_detail": removed_less_detail,
            }

    return cleaned, changes


def _stable_unique(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def read_existing_supercheck(path: Path) -> Tuple[ExchMap, List[str]]:
    """
    既存の .txt/.spc/.pck を読み込み、CALL -> [exch...] を返す。
    """
    mapping: ExchMap = {}
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

        rest = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if not rest:
            mapping.setdefault(call, [])
            continue

        tokens = [t for t in re.split(r"[,\s;]+", rest) if t]
        picked = []
        for t in tokens:
            nt = _norm_exch(t)
            if _is_jccjcg(nt) or _is_pref2(nt):
                picked.append(nt)

        if picked:
            for nt in picked:
                _add_exch(mapping, call, nt)
        else:
            # 形式が見つからない場合は、そのまま1要素として保持（互換性）
            _add_exch(mapping, call, rest)

    return mapping, header


def _header_index(row: List[str], candidates: Iterable[str]) -> Optional[int]:
    norm = [_strip_cell(c).upper() for c in row]
    cand = {c.upper() for c in candidates}
    for i, v in enumerate(norm):
        if v in cand:
            return i
    return None


def read_hamlog_csv_calls(csv_path: Path, keep_domestic_only: bool = True) -> ExchMap:
    """
    Turbo HAMLOG CSV を読み、CALL -> [JCC/JCG...] の dict を返す。
    - ヘッダがある場合はヘッダで CALL / QTH を探す
    - ヘッダが無い/不確実でも強く拾えるように、HAMLOG典型(固定列)も優先:
        CALL = A列(0), QTH(JCC/JCG) = H列(7)
      それでも取れない場合は行内スキャンで拾う
    """
    text = _read_text_any_encoding(csv_path)
    lines = text.splitlines()
    if not lines:
        return {}

    delim = _sniff_delimiter("\n".join(lines[:30]))
    reader = csv.reader(lines, delimiter=delim)

    out: ExchMap = {}
    call_idx: Optional[int] = None
    qth_idx: Optional[int] = None

    for ridx, row in enumerate(reader):
        if not row:
            continue
        row = [_strip_cell(c) for c in row]

        if ridx == 0 and any(_strip_cell(c).upper() in {"CALL", "CALLSIGN", "コールサイン"} for c in row):
            call_idx = _header_index(row, _CALL_HEADERS)
            qth_idx = _header_index(row, _QTH_HEADERS)
            continue

        call: Optional[str] = None
        exch: str = ""

        # 1) HAMLOG典型(固定列)
        if len(row) >= 1:
            cand_call = _norm_call(row[0])
            if _is_callsign(cand_call):
                call = cand_call
        if len(row) >= 8:
            cand_ex = _norm_exch(row[7])
            if _is_jccjcg(cand_ex):
                exch = cand_ex

        # 2) ヘッダ位置
        if call is None and call_idx is not None and call_idx < len(row):
            cand = _norm_call(row[call_idx])
            if _is_callsign(cand):
                call = cand

        if not exch and qth_idx is not None and qth_idx < len(row):
            cand = _norm_exch(row[qth_idx])
            if _is_jccjcg(cand):
                exch = cand

        # 3) 行内スキャン
        if call is None:
            for c in row:
                cand = _norm_call(c)
                if _is_callsign(cand):
                    call = cand
                    break
        if call is None:
            continue

        if not exch:
            for c in row:
                cand = _norm_exch(c)
                if "/" in cand or ":" in cand:
                    continue
                if _is_jccjcg(cand):
                    exch = cand
                    break

        if keep_domestic_only and not exch:
            continue

        out.setdefault(call, [])
        if exch:
            _add_exch(out, call, exch)

    return out


def write_supercheck(path: Path, mapping: ExchMap, header_lines: Optional[List[str]] = None) -> None:
    """
    出力:
      - 1CALLに複数exchがある場合は複数行にする
        JP1LRT 100115
        JP1LRT 100101
    """
    header_lines = header_lines or []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for h in header_lines:
            f.write(h.rstrip("\n") + "\n")

        for call in sorted(mapping.keys()):
            exchs = mapping.get(call, [])
            if not exchs:
                f.write(f"{call}\n")
            else:
                for exch in exchs:
                    exch = exch.strip()
                    if exch:
                        f.write(f"{call} {exch}\n")
                    else:
                        f.write(f"{call}\n")


def write_merge_report(
    report_path: Path,
    csv_path: Path,
    exist_path: Optional[Path],
    out_path: Path,
    mode: str,
    keep_domestic_only: bool,
    existing_map_before_cleanup: ExchMap,
    existing_map_after_incomplete_cleanup: ExchMap,
    incomplete_cleanup_enabled: bool,
    incomplete_filled: List[str],
    incomplete_removed: List[str],
    detail_cleanup_enabled: bool,
    detail_changes: Dict[str, Dict[str, List[str]]],
    new_map: ExchMap,
    merged: ExchMap,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    existing_calls = set(existing_map_after_incomplete_cleanup.keys())
    new_calls = sorted([c for c in new_map.keys() if c not in existing_calls])

    mode_label = {
        "overwrite": "上書き（CSV優先）",
        "append": "追加（既存優先/空欄のみ補完）",
        "merge": "併記（既存+CSVを両方残す / 既存→CSV順）",
    }.get(mode, mode)

    with report_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("SuperCheck Builder - Merge Report\n")
        f.write("=================================\n")
        f.write(f"CSV        : {csv_path}\n")
        f.write(f"EXISTING   : {exist_path if exist_path else '(none)'}\n")
        f.write(f"OUTPUT     : {out_path}\n")
        f.write(f"MODE       : {mode_label}\n")
        f.write(f"DOMESTIC   : {'ON' if keep_domestic_only else 'OFF'}\n")
        f.write("\n")

        f.write("Counts (CALL)\n")
        f.write(f"  Existing(before incomplete cleanup): {len(existing_map_before_cleanup)}\n")
        f.write(f"  Existing(after  incomplete cleanup): {len(existing_map_after_incomplete_cleanup)}\n")
        f.write(f"  CSV                            : {len(new_map)}\n")
        f.write(f"  Merged                         : {len(merged)}\n")
        f.write("\n")

        f.write("[不完全行の整理]\n")
        f.write(f"  enabled: {'ON' if incomplete_cleanup_enabled else 'OFF'}\n")
        if incomplete_cleanup_enabled:
            f.write(f"  補完されたCALL: {len(incomplete_filled)}\n")
            for call in sorted(incomplete_filled):
                f.write(f"    {call}  -> { _fmt_exchs(existing_map_after_incomplete_cleanup.get(call, [])) }\n")
            f.write(f"  削除されたCALL: {len(incomplete_removed)}\n")
            for call in sorted(incomplete_removed):
                f.write(f"    {call}\n")
        f.write("\n")

        f.write("[詳細優先クリーンアップ]\n")
        f.write(f"  enabled: {'ON' if detail_cleanup_enabled else 'OFF'}\n")
        if detail_cleanup_enabled:
            calls = sorted(detail_changes.keys())
            f.write(f"  対象CALL: {len(calls)}\n")
            for call in calls:
                ch = detail_changes[call]
                rp = ch.get("removed_pref2", [])
                rl = ch.get("removed_less_detail", [])
                if rp:
                    f.write(f"    {call} removed pref2: {', '.join(rp)}\n")
                if rl:
                    f.write(f"    {call} removed less detail: {', '.join(rl)}\n")
        f.write("\n")

        f.write("[新たにマージした局一覧]  (CSVにあり、既存(after incomplete cleanup)になかったCALL)\n")
        f.write(f"  件数: {len(new_calls)}\n")
        for call in new_calls:
            f.write(f"  {call}  { _fmt_exchs(new_map.get(call, [])) }\n")
        f.write("\n")


def choose_overwrite_call(
    existing_exchs: List[str],
    csv_exchs: List[str],
    protect_existing_if_more_detailed: bool,
) -> List[str]:
    """
    上書き（CSV優先）でのCALLごとの決定:
    - 基本はCSVのfullsで置換
    - ただし protect_existing_if_more_detailed=True の場合、
      同一ベース(正規化ベース)について既存の方が詳細なら既存を残す
    """
    csv_fulls = [x for x in csv_exchs if _is_jccjcg(x)]
    if not csv_fulls:
        # CSVに完全が無いなら、既存をそのまま（国内のみなら通常ここに来ない）
        return list(existing_exchs)

    if not protect_existing_if_more_detailed:
        return list(_stable_unique(csv_fulls))

    ex_fulls = [x for x in existing_exchs if _is_jccjcg(x)]

    # ベースごとに最良候補を決める（CSVが基本、既存が勝てば置換）
    best_by_base: Dict[int, str] = {}
    src_by_base: Dict[int, str] = {}

    def consider(x: str, src: str):
        base_int, _suf = _base_key(x)
        if base_int == 0:
            return
        cur = best_by_base.get(base_int)
        if cur is None:
            best_by_base[base_int] = x
            src_by_base[base_int] = src
            return
        # 詳細度比較
        cur_score = _detail_score(cur)
        new_score = _detail_score(x)
        if new_score > cur_score:
            best_by_base[base_int] = x
            src_by_base[base_int] = src
        elif new_score == cur_score:
            # 同点ならCSV優先（overwrite本来の意味）
            if src == "csv" and src_by_base.get(base_int) != "csv":
                best_by_base[base_int] = x
                src_by_base[base_int] = src

    for x in csv_fulls:
        consider(x, "csv")
    for x in ex_fulls:
        consider(x, "existing")

    # 出力順は「既存→CSV」のような意味ではなく、結果の安定性重視で
    # まずCSVの登場順で採用（ただし既存が勝った場合は既存値が入っている）
    out: List[str] = []
    used = set()
    for x in csv_fulls:
        base_int, _ = _base_key(x)
        chosen = best_by_base.get(base_int)
        if chosen and chosen not in used:
            out.append(chosen)
            used.add(chosen)
    # CSVに無かったベース（基本ないが）を追加
    for chosen in best_by_base.values():
        if chosen not in used:
            out.append(chosen)
            used.add(chosen)
    return out


# --- GUI -------------------------------------------------------------------

@dataclass
class Paths:
    hamlog_csv: Path
    existing_list: Path
    out_list: Path


def _pick_file(title: str, filetypes: List[Tuple[str, str]]) -> Optional[str]:
    from tkinter import filedialog
    return filedialog.askopenfilename(title=title, filetypes=filetypes)


def _pick_save(
    title: str,
    defaultextension: str,
    filetypes: List[Tuple[str, str]],
    initialdir: Optional[str] = None,
    initialfile: Optional[str] = None,
) -> Optional[str]:
    from tkinter import filedialog
    return filedialog.asksaveasfilename(
        title=title,
        defaultextension=defaultextension,
        filetypes=filetypes,
        initialdir=initialdir,
        initialfile=initialfile,
    )


def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("SuperCheck Builder (Turbo HAMLOG CSV → CTESTWIN パーシャル)")

    v_csv = tk.StringVar()
    v_exist = tk.StringVar()
    v_out = tk.StringVar()
    v_domestic = tk.BooleanVar(value=True)
    v_out_fmt = tk.StringVar(value=".spc")

    # マージモード
    v_merge_mode = tk.StringVar(value="overwrite")

    # レポート出力（任意）
    v_report_enable = tk.BooleanVar(value=True)
    v_report = tk.StringVar()

    # 不完全行の整理（互換性のためデフォルトOFF）
    v_cleanup_incomplete = tk.BooleanVar(value=False)

    # NEW: 詳細優先クリーンアップ（デフォルトON）
    v_detail_cleanup = tk.BooleanVar(value=True)

    # NEW: 上書き時に「既存がより詳細なら既存を残す」（デフォルトON）
    v_protect_existing_detail = tk.BooleanVar(value=True)

    pad = {"padx": 8, "pady": 6}
    frm = tk.Frame(root)
    frm.pack(fill="both", expand=True, **pad)

    def row(y: int, label: str, var: tk.StringVar, btn_text: str, cmd):
        tk.Label(frm, text=label, anchor="w").grid(row=y, column=0, sticky="w")
        tk.Entry(frm, textvariable=var, width=70).grid(row=y, column=1, sticky="we", padx=6)
        tk.Button(frm, text=btn_text, command=cmd).grid(row=y, column=2, sticky="e")

    frm.columnconfigure(1, weight=1)

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

    def _default_report_path(out_path_str: str) -> str:
        if not out_path_str:
            return "merge_report.txt"
        try:
            p = Path(out_path_str)
            return str(p.with_suffix("")) + "_merge_report.txt"
        except Exception:
            return out_path_str + "_merge_report.txt"

    def on_out_format_change(*_args):
        cur = v_out.get()
        new = _replace_out_ext(cur, v_out_fmt.get())
        v_out.set(new)
        if not v_report.get().strip():
            v_report.set(_default_report_path(new))

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
                    if not v_report.get().strip():
                        v_report.set(_default_report_path(new_out))
            except Exception:
                pass

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
                    if not v_report.get().strip():
                        v_report.set(_default_report_path(v_out.get()))
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
            if not v_report.get().strip():
                v_report.set(_default_report_path(p))

    def pick_report():
        initialdir = None
        initialfile = None
        cur = v_report.get().strip()
        if cur:
            try:
                p = Path(cur)
                if p.parent.exists():
                    initialdir = str(p.parent)
                initialfile = p.name
            except Exception:
                initialfile = Path(cur).name
        else:
            initialfile = "merge_report.txt"

        p = _pick_save(
            "レポートTXTの出力先を指定（任意）",
            ".txt",
            [("Text (*.txt)", "*.txt"), ("All files", "*.*")],
            initialdir=initialdir,
            initialfile=initialfile,
        )
        if p:
            v_report.set(p)

    row(0, "① HAMLOG CSV（今回の追加分）", v_csv, "参照…", pick_csv)
    row(1, "② 既存パーシャルリスト（マージ元、任意）", v_exist, "参照…", pick_exist)
    tk.Button(frm, text="クリア", command=lambda: v_exist.set("")).grid(row=1, column=3, padx=4)
    row(2, "③ 出力ファイル（上書き/新規）", v_out, "保存先…", pick_out)

    # ④ レポート
    row(3, "④ レポートTXT（任意）", v_report, "保存先…", pick_report)
    tk.Checkbutton(frm, text="レポートを出力する", variable=v_report_enable).grid(row=3, column=3, sticky="w", padx=4)

    frm_fmt = tk.Frame(frm)
    frm_fmt.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 2))
    tk.Label(frm_fmt, text="出力形式:").pack(side="left")
    tk.Radiobutton(frm_fmt, text="zLog (.spc)", variable=v_out_fmt, value=".spc", command=on_out_format_change).pack(side="left", padx=6)
    tk.Radiobutton(frm_fmt, text="CTESTWIN (.pck)", variable=v_out_fmt, value=".pck", command=on_out_format_change).pack(side="left", padx=6)

    v_row = 5
    tk.Checkbutton(frm, text="国内局のみ（JCC/JCG がある行だけ採用）", variable=v_domestic).grid(row=v_row, column=1, sticky="w", pady=4)

    # 不完全行の整理
    tk.Checkbutton(
        frm,
        text="既存の不完全行（CALLのみ/都道府県2桁）を整理（CSVで補完、無ければ削除）",
        variable=v_cleanup_incomplete,
    ).grid(row=v_row + 1, column=1, sticky="w", pady=2)

    # 詳細優先
    tk.Checkbutton(
        frm,
        text="詳細優先クリーンアップ（09003J優先・完全があれば都道府県2桁削除）",
        variable=v_detail_cleanup,
    ).grid(row=v_row + 2, column=1, sticky="w", pady=2)

    # 既存詳細保護（overwrite時）
    tk.Checkbutton(
        frm,
        text="上書き時、既存の方が詳細なら既存を残す（例: 29012A を保護）",
        variable=v_protect_existing_detail,
    ).grid(row=v_row + 3, column=1, sticky="w", pady=2)

    frm_merge = tk.Frame(frm)
    frm_merge.grid(row=v_row, column=2, columnspan=2, sticky="e")
    tk.Label(frm_merge, text="マージ方式:").pack(side="left")
    tk.Radiobutton(frm_merge, text="上書き（CSV優先）", variable=v_merge_mode, value="overwrite").pack(side="left", padx=4)
    tk.Radiobutton(frm_merge, text="追加（既存優先/空欄のみ補完）", variable=v_merge_mode, value="append").pack(side="left", padx=4)
    tk.Radiobutton(frm_merge, text="併記（既存+CSVを両方残す）", variable=v_merge_mode, value="merge").pack(side="left", padx=4)

    log = tk.Text(frm, height=10, width=90)
    log.grid(row=v_row + 4, column=0, columnspan=4, sticky="nsew", pady=6)
    frm.rowconfigure(v_row + 4, weight=1)

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
            exist_path: Optional[Path] = None

            existing_map: ExchMap = {}
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

            out_path.parent.mkdir(parents=True, exist_ok=True)

            write_log(f"[2] CSV 読込: {csv_path}")
            new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=bool(v_domestic.get()))
            write_log(f"    CSV抽出: {len(new_map)} 件")

            existing_before_cleanup = {k: list(v) for k, v in existing_map.items()}
            incomplete_filled: List[str] = []
            incomplete_removed: List[str] = []

            # 不完全行の整理（任意）
            if bool(v_cleanup_incomplete.get()):
                write_log("[2.5] 不完全行の整理: ON（CSVで補完、無ければ削除）")
                existing_map, incomplete_filled, incomplete_removed = cleanup_incomplete_existing(existing_map, new_map)
                write_log(f"    補完: {len(incomplete_filled)} / 削除: {len(incomplete_removed)}")
            else:
                write_log("[2.5] 不完全行の整理: OFF（従来通り）")

            mode = v_merge_mode.get()

            # merged 初期化（existingをコピー）
            merged: ExchMap = {k: list(v) for k, v in existing_map.items()}

            if mode == "overwrite":
                write_log("[3] マージ方式: 上書き（CSV 優先）")
                for call, exchs in new_map.items():
                    merged[call] = choose_overwrite_call(
                        existing_exchs=merged.get(call, []),
                        csv_exchs=exchs,
                        protect_existing_if_more_detailed=bool(v_protect_existing_detail.get()),
                    )

            elif mode == "append":
                write_log("[3] マージ方式: 追加（既存優先/空欄のみ補完）")
                added = 0
                for call, exchs in new_map.items():
                    fulls = [x for x in exchs if _is_jccjcg(x)]
                    if not fulls:
                        merged.setdefault(call, merged.get(call, []))
                        continue
                    if call not in merged or not merged.get(call):
                        merged[call] = []
                        for x in fulls:
                            _add_exch(merged, call, x)
                        added += 1
                write_log(f"    追加されたCALL件数: {added}")

            else:
                write_log("[3] マージ方式: 併記（既存+CSVを両方残す / 既存→CSV順）")
                added = 0
                for call, exchs in new_map.items():
                    fulls = [x for x in exchs if _is_jccjcg(x)]
                    for exch in fulls:
                        before = len(merged.get(call, []))
                        _add_exch(merged, call, exch)
                        after = len(merged.get(call, []))
                        if after > before:
                            added += 1
                write_log(f"    追加された交換情報数: {added}")

            # 詳細優先クリーンアップ（任意）
            detail_changes: Dict[str, Dict[str, List[str]]] = {}
            if bool(v_detail_cleanup.get()):
                write_log("[3.5] 詳細優先クリーンアップ: ON（09003J優先・完全があれば都道府県2桁削除）")
                merged, detail_changes = detail_cleanup_map(merged)
                write_log(f"    影響CALL数: {len(detail_changes)}")
            else:
                write_log("[3.5] 詳細優先クリーンアップ: OFF（従来通り）")

            write_log(f"[4] マージ後総件数: {len(merged)} 件（CALL数）")

            write_log(f"[5] 書き出し: {out_path}")
            write_supercheck(out_path, merged, header_lines=[])
            write_log("    完了")

            # レポート出力
            if bool(v_report_enable.get()):
                report_str = v_report.get().strip()
                if not report_str:
                    report_str = _default_report_path(str(out_path))
                    v_report.set(report_str)
                report_path = Path(report_str).expanduser()
                write_log(f"[6] レポート出力: {report_path}")
                write_merge_report(
                    report_path=report_path,
                    csv_path=csv_path,
                    exist_path=exist_path if exist_val else None,
                    out_path=out_path,
                    mode=mode,
                    keep_domestic_only=bool(v_domestic.get()),
                    existing_map_before_cleanup=existing_before_cleanup,
                    existing_map_after_incomplete_cleanup=existing_map,
                    incomplete_cleanup_enabled=bool(v_cleanup_incomplete.get()),
                    incomplete_filled=incomplete_filled,
                    incomplete_removed=incomplete_removed,
                    detail_cleanup_enabled=bool(v_detail_cleanup.get()),
                    detail_changes=detail_changes,
                    new_map=new_map,
                    merged=merged,
                )
                write_log("    レポート完了")

            messagebox.showinfo("完了", f"出力しました:\n{out_path}\n\nCALL件数: {len(merged)}")
        except Exception as e:
            messagebox.showerror("例外", f"{type(e).__name__}: {e}")
            write_log(f"!! {type(e).__name__}: {e}")

    btn = tk.Button(frm, text="生成（マージ→ソート→重複削除）", command=on_run, height=2)
    btn.grid(row=v_row + 5, column=0, columnspan=4, sticky="we", pady=8)

    root.minsize(900, 600)
    root.mainloop()


def main(argv: List[str]) -> int:
    if len(argv) == 1:
        run_gui()
        return 0

    # CLI互換維持（従来どおり4引数）
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

    out_path: Path
    if out_arg in ("", "-", "auto"):
        out_path = csv_path.with_suffix(".spc")
    elif out_arg.lower().startswith("auto."):
        ext = "." + out_arg.split(".", 1)[1]
        out_path = csv_path.with_suffix(ext)
    else:
        out_path = Path(out_arg)

    exist_path = Path(exist_arg) if exist_arg not in ("", "-") else None

    if exist_path and exist_path.exists():
        existing_map, _ = read_existing_supercheck(exist_path)
    else:
        existing_map = {}

    new_map = read_hamlog_csv_calls(csv_path, keep_domestic_only=True)

    # CLIは従来互換: 上書き（CSV優先）だが、既存の方が詳細なら既存保護 + 詳細クリーンアップはON
    merged: ExchMap = {k: list(v) for k, v in existing_map.items()}
    for call, exchs in new_map.items():
        merged[call] = choose_overwrite_call(
            existing_exchs=merged.get(call, []),
            csv_exchs=exchs,
            protect_existing_if_more_detailed=True,
        )

    merged, _detail_changes = detail_cleanup_map(merged)

    write_supercheck(out_path, merged, header_lines=[])
    print(f"OK: {out_path} ({len(merged)}件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
