SuperCheck Builder  (Turbo HAMLOG CSV -> SuperCheck list)

GitHub:
https://github.com/jp1lrt/hamlog-supercheck-builder

Latest Release (Windows EXE):
https://github.com/jp1lrt/hamlog-supercheck-builder/releases/latest


[What is this?]
Turbo HAMLOG が出力した CSV から、国内局（JCC/JCG がある行）を抽出し、
zLog / CTESTWIN の「スーパー・チェック（パーシャルチェック）」用リストを生成します。

- 既存のパーシャルチェックリスト（任意）とマージできます
- コールサインでソートします
- 重複は自動削除します（同一CALLはCSV側の情報で上書き）


[Important: Output extension]
出力形式は 2種類あります。

1) zLog 用:    *.spc
2) CTESTWIN用: *.pck

※中身の形式は同じです。
  「.spc で出力したファイルを .pck にリネームして CTESTWIN で使う」
  ことも可能です。


[Input files]
(1) Turbo HAMLOG の CSV
    - 国内局は JCC/JCG が入っている前提
    - 海外局は DXCC 等になりがち（必要なら後で手動で削除してください）

(2) 既存パーシャルチェック（任意）
    - 過去に作った .spc / .pck / .txt など


[How to use (GUI)]
1) supercheck_builder.exe を起動
2) 入力（HAMLOG CSV）を選択
3) 既存パーシャル（任意）を選択
4) 出力先を指定（.spc / .pck）
5) [作成する] をクリック


[SHA256 verification (recommended)]
配布ファイルの改ざんチェックとして SHA256 を照合できます。

Windows (PowerShell / CMD):
  certutil -hashfile supercheck_builder.exe SHA256

Git Bash / Linux / macOS:
  shasum -a 256 supercheck_builder.exe

同梱の .sha256 がある場合:
  shasum -a 256 -c supercheck_builder.exe.sha256
  -> "supercheck_builder.exe: OK" と出れば一致


[Troubleshooting]
- SmartScreen の警告が出る場合があります。
  SHA256 が一致していれば、配布元と同一ファイルであることを確認できます。

- 出力に海外局が混ざる場合:
  入力CSV内に JCC/JCG 以外の情報しか無い局が含まれている可能性があります。
  基本は「JCC/JCG がある行のみ採用」ですが、必要なら手動で削除してください。


[License]
MIT License (see LICENSE)


[Author]
Yoshiharu Tsukuura / JP1LRT
https://github.com/jp1lrt
