# SuperCheck Builder

Turbo HAMLOG の CSV から国内局のスーパー・チェック用リスト（zLog/CTESTWIN 形式 .spc / .pck）を生成するツールです。GUI と CLI の両方を提供します。一般ユーザーは Windows 用実行ファイル（.exe）を Releases からダウンロードしてそのまま使うことを推奨します。

---

## 目次
- [特徴](#特徴)
- [前提条件](#前提条件)
- [ダウンロード（Windows）](#ダウンロードwindows)
- [使い方（GUI）](#使い方gui)
- [使い方（CLI）](#使い方cli)
- [配布ファイルの検証方法（SHA256）](#配布ファイルの検証方法sha256)
- [ソースからのビルド（開発者向け）](#ソースからのビルド開発者向け)
- [ビルドメタ情報の記録](#ビルドメタ情報の記録)
- [貢献・報告](#貢献報告)
- [著者 / 連絡先](#著者--連絡先)
- [ライセンス](#ライセンス)

---

## 特徴
- Turbo HAMLOG の CSV から、zLog / CTESTWIN 形式のスーパー・チェックリストを生成します。  
- GUI（tkinter）で直感的に操作可能。  
- CLI でバッチ処理やスクリプト組み込みが可能。  
- 配布用 Windows 実行ファイル（.exe）を Releases に添付。

---

## 前提条件
- 実行ファイルを使う場合: Windows（.exe をダブルクリックで実行可能）  
- ソースから実行する場合（開発者向け）:
  - Python 3.9 以上（3.14 など新しいバージョンでも動作確認済み）  
  - tkinter（GUI を使う場合）
  - 推奨: 仮想環境（venv）

---

## ダウンロード（Windows）
最新版の Windows 実行ファイルは GitHub Releases からダウンロードしてください：  
[最新版をダウンロードする](https://github.com/jp1lrt/hamlog-supercheck-builder/releases/latest)

配布ファイル（リリース）にはビルドのトレーサビリティ情報（ビルド元コミット、SHA256、ビルド日時）をリリースノートに記載しています。

---

## 使い方（GUI）
1. Releases からダウンロードした `supercheck_builder.exe` をダブルクリックして起動します。  
2. GUI 上で Turbo HAMLOG の CSV ファイルを選択します。  
3. 出力形式（.spc / .pck 等）や保存先を選択して「生成」ボタンを押します。  
4. 出力ファイルが指定したフォルダに作成されます。

（GUI の詳細な操作手順やスクリーンショットは今後 README に追記します）

---

## 使い方（CLI）
ソースから直接実行する場合の例：

1. 仮想環境の作成と依存インストール
```bash
python -m venv venv
source venv/bin/activate    # Windows (Git Bash / WSL) の場合
# Windows PowerShell の場合: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt   # requirements.txt がある場合
```

2. ヘルプ表示（例）
```bash
python supercheck_builder.py --help
```

3. バッチ実行の例（入力 CSV → 出力ファイル指定）
```bash
python supercheck_builder.py --input input.csv --output out.spc --format spc
```

（実際の CLI オプションはスクリプトの `--help` を参照してください）

---

## 配布ファイルの検証方法（SHA256）
ダウンロードした実行ファイルの整合性は SHA256 ハッシュで確認してください。Windows の例:

PowerShell / CMD（certutil）
```powershell
certutil -hashfile supercheck_builder.exe SHA256
```

表示されたハッシュがリリースノートに記載されている SHA256 と一致することを確認してください。

例（本リポジトリの最新リリース時の参照値）
- SHA256: 8e5007908832703ec9d6f4019cc44e9387b8ae7a55b5bd469e82ac0a3e000ab3  
- ビルド元コミット: 96605c7  
- ビルド日時 (UTC): 2025-12-29T09:35:17Z

（上記はリリースごとに更新されます。必ず該当リリースのノートを参照してください）

---

## ソースからのビルド（開発者向け）
PyInstaller を使って Windows 用の単一 exe を作成できます（Windows 上で実行してください）。

1. 仮想環境を作る・有効化して依存をインストール
```bash
python -m venv venv
.\venv\Scripts\activate     # PowerShell の場合
pip install -r requirements.txt
pip install pyinstaller
```

2. ビルド実行（例）
```bash
pyinstaller --onefile --windowed supercheck_builder.py
```

3. 出力は `dist/supercheck_builder.exe` に生成されます。生成後は SHA256 を取得し、リリースに添付してください。

---

## ビルドメタ情報の記録
配布のトレーサビリティを確保するため、ビルドごとに次の情報を保存しておくことを推奨します：
- ビルド元コミット（短縮コミット ID）  
- 実行ファイルの SHA256  
- ビルド日時（UTC）

例: `dist/build_info.txt`
```
commit: 96605c7
sha256: 8e5007908832703ec9d6f4019cc44e9387b8ae7a55b5bd469e82ac0a3e000ab3
built: 2025-12-29T09:35:17Z
```

リリース作成時には、上の情報をリリースノートに記載し、実行ファイルを添付してください。

---

## 貢献・報告
バグ報告や機能要望は GitHub Issues で受け付けています。プルリクエスト歓迎。  
貢献の際はできるだけ小さな変更単位で、変更点を明記して送ってください。

---

## 著者 / 連絡先
津久浦 慶治 (Yoshiharu Tsukuura) — コールサイン: JP1LRT  
GitHub: https://github.com/jp1lrt

---

## ライセンス
このプロジェクトは MIT License のもとで公開されています。詳しくは `LICENSE` ファイルを参照してください。

---

## 連絡
問題や質問があれば Issues を開いてください。リリースや配布に関する重要な変更はリリースノートにて告知します。
