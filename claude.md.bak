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

## 作業記録

### v2.8.1 (2026-11-01) ← 最新（プロンプト直接指示）
- NSF の曲頭ノイズ再発を修正（一部chをミュート/ソロにした時、曲頭約20〜50msに他chの音が漏れる。例: Dragon Warrior の 005 で ch2 ソロ）
  - 原因: libgme の start_track は無音検出のため曲頭を先読み生成しており、その時点ではミュート前なので全ch入り。
    v2.7.3 で gme_clear_blip_buffer を外したため、この先読み分がそのまま出ていた
  - gme_clear_blip_buffer の単純復活は不可: ミュート状態で無音検出をやり直すため、ソロ時に曲がずれる（約18%）・
    Dragon Warrior の ch1 ソロが全編無音になる
  - 改造DLLに gme_refresh_lookahead を追加: start_track の先読みチャンク数を記録し、エミュレータを曲頭に戻して
    現在のミュートで同じ位置まで再生成 → 先読みバッファを差し替え（タイミングは start_track と同一）
  - _nsf_render で一部chミュート時のみ呼ぶ（set_tempo はその後に移動）。SPC/GBS は変更なし
  - 検証（NSF 1931ファイル）: 全ch再生は旧DLLと全ファイル完全一致、全ミュートは全ファイル完全無音（旧: 1851ファイルで漏れ）、
    各chソロの合計＝全ch再生（曲頭含む。例外10件は DMC 等の非線形合成による元々の誤差）、ソロ本体の差は最大1LSB
  - src/dll/libgme.dll を更新（game-music-emu-morokoshi で再ビルド）
- APP_VERSION v2.8.1

### v2.8.0 (2026-11-01)（プロンプト直接指示）
- APP_VERSION を v2.8.0 に更新（ビルド前に確認済み・exe のウィンドウタイトルで v2.8.0 表示を確認）
- v2.7.1〜v2.7.9 の変更を公開: Save（WAV/MP3/M4A、前回保存フォルダを記憶）、NSF の MIDI 保存（nsf2mid 統合、
  保存ダイアログ横のオプションパネル）、Zoom を最大化ボタンへ移動、Speed 直接入力の書式拡張、
  NSF 曲頭の音切れ修正・SPC/GBS 曲頭の余分な無音を削除、ツールチップの重なり修正など
- マニュアル更新: 表紙・対象バージョン、特徴に Save/MIDI を追加、アイコン表の Zoom → Save（Zoom は最大化ボタンの説明に）、
  Speed の直接入力、ffmpeg の用途、「5. 保存（Save）・MIDI 変換」を新設（欠番だった 5 章。MIDI 部分は nsf2mid マニュアルの
  特徴・オプション・対処表・出力 MIDI を流用し、ラベルをもろこしのダイアログ表記に合わせた）、制限事項に MIDI 変換の範囲、
  ショートカットに S、更新履歴 v2.8.0（JP/EN）。PDF 再生成（57 ページ）
  - Main_Capture.png / GameMode_Capture.png: Zoom アイコンを現在のアプリの Save ボタン画像で置き換え、
    タイトルバーの最大化ボタンを有効表示に修正（元画像は docs/icons/bkup/）
- exe ビルド・dist/morokoshi280（exe・dll/・license.txt・PDF）と morokoshi280.zip を作成
- git tag v2.8.0
