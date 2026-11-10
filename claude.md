## ★ 再起動前のメモ（2026-11-09、v3.0.0 公開の時点）

- v3.0.0 で公開（ユーザー「きりがないので、いったんここまで」）。MIDI 変換の未確認・未対応の項目は docs/midi/meter_check.md の冒頭
  （v2.9.30・v2.9.33 で変わった曲の耳での確認、Hydlide 3 のテンポ、Business Wars の 6/4、Pooyan の冒頭）
- GBS・SPC の MIDI 変換はマニュアル上「β版」（未検証）

---

・C:\Users\ike09\.claude\claude.md 初回起動時と更新あり時は必ず読むこと。

・v1.8.0としてのビルドリリースのはずだが、ウィンドウタイトルに表記されているバージョンがv1.7.2のまま。
　以前もあったので、確実にビルドバージョンを管理して。グローバルCLAUDE.mdにメモっておいて。（すでにメモってあった気もするが…）

　今回、以下のエラーも回避した上でv1.8.0としてもう一度リリースビルドして。

・タスクバーに表示されているアイコンがもろこしマークになっていない。デスクトップのアイコンはもろこしマークになっているのだが、ここは管理が異なる？

以下、他のAIによる指摘


PyInstallerでビルドしたアプリの場合、まさに先ほど紹介した「プログラム側（GUIコード側）でアイコンを読み込む処理」が欠けているか、PyInstallerのファイル展開の仕組み（`_MEIPASS`）に対応していないことが原因です。

PyInstallerの `--icon` オプション（または `.spec` ファイルでの指定）は、**「エクスプローラー用のリソースアイコン」を埋め込むだけ**なので、タスクバーのアイコンはPythonコード側で明示的に指定する必要があります。

以下の2つのステップでコードを修正すると解決します。

---

## 🛠️ 解決するための2つのステップ

### ステップ 1. Windowsに独自のアプリだと認識させる（AUMIDの設定）

PythonのGUIライブラリ（TkinterやPyQtなど）は、そのまま起動するとWindowsから「Pythonインタープリタ（python.exe）の仲間」と見なされてしまい、タスクバーのアイコンがデフォルト（またはPythonのロゴ）に強制上書きされる仕様になっています。

これを防ぐため、GUIを起動する前のメインコード（`if __name__ == '__main__':` の直後など）に以下のコードを追加してください。

```python
import sys
import os
import ctypes

# Windows用のタスクバーアイコンバグ回避処理
if sys.platform == 'win32':
    myappid = 'mycompany.myapp.v1.0'  # 任意のユニークな文字列
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

```

### ステップ 2. PyInstallerの一時フォルダ（_MEIPASS）からアイコンを読み込む

PyInstallerで「1つのexeファイル（`--onefile`）」にまとめる場合、起動時に中身のアイコン画像（`.ico`）がWindowsの一時フォルダ（`AppData\Local\Temp\_MEIxxxxxx`）に解凍されます。
コード側で単に `icon.ico` と相対パスで書いていると、この一時フォルダを見つけられず、読み込みに失敗してデフォルトアイコンに戻ってしまいます。

そのため、解凍先を正しく見つけるための関数を用意し、それをGUIのアイコン設定に渡します。

#### 【例：Tkinter をお使いの場合】

```python
def resource_path(relative_path):
    """ PyInstallerの一時フォルダから絶対パスを取得する関数 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 1. メインウィンドウを作成
root = tk.Tk()

# 2. 上記の関数を使ってアイコンの正しいパスを取得
icon_path = resource_path("app_icon.ico")  # あなたのアイコンファイル名

# 3. ウィンドウとタスクバーにアイコンを適用
root.iconbitmap(default=icon_path)

```

#### 【例：PyQt / PySide をお使いの場合】

```python
from PyQt6.QtGui import QIcon
# （上の resource_path 関数も同様に定義しておく）

app = QApplication(sys.argv)
main_win = QMainWindow()

# アイコンを設定
icon_path = resource_path("app_icon.ico")
main_win.setWindowIcon(QIcon(icon_path))
app.setWindowIcon(QIcon(icon_path)) # アプリ全体（タスクバー）にも適用

```

---

## 📦 PyInstallerでビルドする際の注意点

コード側で上記のように一時フォルダから読み込むように変更した後は、PyInstallerでビルドする際、`--icon` だけでなく **`--add-data` オプションを使って、exeの内部にアイコンファイルを同梱させる**必要があります。

**コマンド例：**

```bash
pyinstaller --onefile --windowed --icon=app_icon.ico --add-data "app_icon.ico;." your_script.py

```

*※ `--add-data "app_icon.ico;."` の部分で、exeの内部（一時フォルダのルート）にアイコンを埋め込む指示をしています（Windowsなので区切り文字はセミコロン `;` です）。*

この「AUMIDの設定」と「`--add-data` による内部同梱＋パスの書き換え」を行うことで、エクスプローラー上でもタスクバー上でも、正しく自作のアイコンが表示されるようになります！

---

## MIDI 変換（nsf2mid）の決まりごと（v2.9.25 で nsf2mid を統合）

- ソースは `src/nsf2mid_core/`（直接編集してよい。nsf2mid 本体との同期は不要になった）。バージョンは morokoshi の `APP_VERSION` だけで管理する
- 仕様書: `docs/midi/spec.md`。確認リスト: `docs/midi/meter_check.md`・`spc_check.md`。統合前の作業記録: `docs/midi/nsf2mid_history.md`
- CLI（調査用）: `python src/nsf2mid_core/nsf2mid.py FILE [-t TRACK] [-s SECONDS] [-o OUTDIR] ...`
- 回帰テスト: `python tools/regress.py > 結果.txt` → 前回の結果と diff。判定ロジックを変えたら必ず実行する
  （nsf2mid v0.1.9 で 12 曲しか確認せず、45 本でテンポ 2 倍の誤判定が出た前例あり）
- テストデータ: NSF 1934 本 `tmp/nsf_downloads/*.zip`、展開済みの確認用 `tmp/nsf2mid_test/`（出力は `tmp/nsf2mid_test/nsf2mid_out/`、12 曲は変更のたびに作り直すのが慣例）
- ユーザーの判断（確定）:
  - 三角波は APU の物理的な音高のまま（オクターブ移動しない）
  - 音色（プログラムチェンジ）は出力しない（Sibelius が音色から楽器を決めて並べ替えるため）
  - トラック名は楽器名と紛らわしくない名前にする（「Triangle」は Sibelius で打楽器トライアングルになった）
  - ループ確定は 3 回連続一致（2 回繰り返した後にサビが入る曲がある）
  - 冒頭の空白は保持する。3 連ノリ（シャッフル）は 3 連として出す
  - テンポの半分・2 倍は許容（MIDI オプションで調整できる）

---

## 作業記録

### v3.0.0 マニュアル修正 (2026-11-10)（プロンプト直接指示: マニュアルの「MIDI options（変換オプション）」を日本語化し、PDF と dist を作り直す）
- 日本語マニュアル 5 章の MIDI options 表: 項目名に日本語の意味を併記（例: Loops（ループ回数））、Auto（自動）など既定値も日本語を併記。
  「画面上の項目名は英語で表示されます」の一文を追加。「うまく変換できないとき」の表と「Defaults（初期値に戻す）」も同様に併記
- PDF 再生成（61 ページ）。dist/morokoshi300 の PDF を差し替えて morokoshi300.zip を作り直した（exe は変更なし、アプリのバージョンは v3.0.0 のまま）

### v3.0.0 (2026-11-09) ← 最新（プロンプト直接指示: v2.9.33 の 3 曲は OK。v3.0.0 でリリース、マニュアル更新。SPC・GBS は未検証なので β版、NSF は MIDI の検出精度大幅向上と書く）
- 公開バージョン v3.0.0 としてリリース（v2.9.x の作業記録は消去。nsf2mid 統合前の記録は docs/midi/nsf2mid_history.md、MIDI の仕様は docs/midi/spec.md）
  - APP_VERSION を v3.0.0 に更新してからビルド。exe のウィンドウタイトルで「Morokoshi Time v3.0.0」を確認
  - dist/morokoshi300（exe・dll/（libgme.dll は v2.9.21 の改造版）・license.txt・PDF）と morokoshi300.zip を作成
- マニュアル（JP/EN）: 表紙・対象バージョン・末尾を v3.0.0 に。更新履歴に v3.0.0 を追加
  - 特徴: NSF の MIDI 変換は「テンポ・拍子・小節頭の検出精度が大幅に向上」、変拍子・前打ち・拡張音源に対応。GBS・SPC の MIDI 変換は β版
  - 5 章: MIDI は NSF・GBS・SPC（β版の注意書き）、進み具合の表示、変拍子・前打ち・音程付き DPCM・ループ・拡張音源の説明、
    オプション表に Detect odd meters・Arpeggios as chords、出力 MIDI の ch 表を更新（ノイズ 4・DPCM 5・ドラム 1〜3・拡張音源 6〜13、GBS・SPC の割り当て）
  - 7 章: MIDI 変換の対応範囲を更新。PDF 再生成（61 ページ）
- docs/midi/meter_check.md: v2.9.33 の 3 曲を回答済み（OK）に、冒頭に未確認・未対応の項目をまとめた
