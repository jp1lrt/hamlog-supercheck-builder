# SuperCheck Builder

Turbo HAMLOG の CSV から zLog/CTESTWIN 形式（.spc / .pck）のパーシャルチェックリストを生成するツールです。  
GUI と CLI の両方を提供します。ソース（.py）を公開しますが、一般的なユーザーは再ビルド不要で使える Windows 実行ファイル（.exe）を優先して利用することを推奨します。

---

## 概要
- Turbo HAMLOG が出力した CSV を読み、国内局（JCC/JCG を含む行）を抽出して出力します。  
- zLog の SuperCheck（.spc）/ CTESTWIN の Partial（.pck）形式で出力できます。  
- 既存のパーシャルチェックリスト（.spc/.pck/.txt 等）を任意で読み込み・マージ可能です。  
- GUI（Tkinter ベース）と CLI の両方を提供します。

## 推奨ユーザー
- 一般ユーザー（インストールや Python 環境の設定を行いたくない方）は、事前にビルドした exe をダウンロードして利用してください。  
- 開発者やカスタマイズしたい方はソース（.py）から実行・ビルドしてください。

## 主要機能
- GUI：出力形式選択（.spc / .pck）、出力ファイル拡張子の自動更新、既存リストの任意指定、出力ファイル名の自動生成  
- CLI：自動出力（`auto`）オプション、既存ファイル引数の任意化（- を指定して未指定扱い）  
- 既存リストが無い場合は新規作成扱いで続行可能（確認ダイアログあり）

## 動作条件
- Windows（exe を配布します）  
- Python を使う場合：Python 3.9 以上、Tkinter（GUI を使う場合）

---

## クイックスタート（exe を使う）
1. Release ページから最新の `supercheck_builder.exe` をダウンロード（Release に添付）  
2. exe をダブルクリックして起動  
3. GUI で「① HAMLOG CSV」を指定 → （任意）「② 既存パーシャルリスト」 → 「③ 出力ファイル」を確認して「生成」

クイックスタート（ソースから）
```bash
# クローン
git clone https://github.com/jp1lrt/hamlog-supercheck-builder.git
cd hamlog-supercheck-builder

# （推奨）仮想環境
python -m venv venv
venv\Scripts\activate

# GUI 実行
python supercheck_builder.py

# CLI 実行例
python supercheck_builder_v3.py hamlog.csv - auto
```

## GUI の操作（簡単）
1. ① HAMLOG CSV：Turbo HAMLOG が出力した CSV ファイルを選択  
2. ② 既存パーシャルリスト（任意）：既存の .spc/.pck/.txt を選ぶとマージされます（空欄可）  
3. ③ 出力ファイル：出力先と形式（.spc/.pck）を設定。形式を変えると拡張子を自動更新します。  
4. 「生成」ボタンでファイルを作成。既存ファイルがない場合は新規作成として処理されます。

## CLI の主な使い方
- 基本:
  python supercheck_builder_v3.py <hamlog.csv> <existing.txt_or_-> <out.txt_or_auto>
- 例: CSV から自動で .spc を生成
  python supercheck_builder_v3.py hamlog.csv - auto
- 既存ファイルを指定してマージ
  python supercheck_builder_v3.py hamlog.csv existing.spc out.spc

---

## ビルド（Windows exe）
ローカルで exe を作る場合は pyinstaller を推奨します（Windows 環境で実行）。
```bash
pip install pyinstaller
pyinstaller --onefile --windowed supercheck_builder.py
# 生成物: dist\supercheck_builder.exe
```
生成後に必ず動作確認（実際に CSV を読み込んで .spc/.pck を出力）してください。

## リリース手順（簡易）
1. main を最新にする:
   git checkout main
   git pull origin main
2. バージョンタグを付ける:
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
3. GitHub の Release を作成し、dist の exe を添付

---

## テスト（確認手順）
- GUI: 少量の HAMLOG CSV を使って .spc/.pck を生成し、zLog / CTESTWIN で読み込めるか確認する。  
- CLI: 上述の CLI 例で自動生成とマージを試す。

---

## 著者 / 連絡先
津久浦 慶治 (Yoshiharu Tsukuura) — コールサイン: JP1LRT  
GitHub: https://github.com/jp1lrt

## ライセンス
このプロジェクトは MIT ライセンスの下で公開します。LICENSE ファイルを参照してください。

---
