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

### v2.7.2 (2026-11-01) ← 最新（プロンプト直接指示）
- Zoom アイコンを廃止し、ウィンドウ枠の最大化ボタン（タイトルバーのダブルクリックも）で Zoom(1x⇔2x) 切り替えに変更
  - 固定サイズのため Qt が外す WS_MAXIMIZEBOX を Win32 API で付け直し、最大化された状態変化(changeEvent)を検出して通常状態に戻し Zoom を実行
  - nativeEvent のオーバーライドは PyQt6 でアクセス違反クラッシュしたため不採用
  - Z キー・テンキー * の Zoom はそのまま
- 空いた位置に Save アイコンを配置（ショートカット S）。再生中の音声を曲全体で WAV / MP3 / M4A 保存
  - Speed/Key/Fine を反映（ゲーム音楽はテンポ焼き込み済みのため Key/Fine のみ変換）、フィルターは反映しない
  - サンプリングレートは再生中のもの、WAV は 16bit PCM、MP3(libmp3lame)/M4A(AAC) は 192kbps 固定（ffmpeg 使用）
  - 初期ファイル名は読み込みファイル名（ゲーム音楽は _トラック番号＋曲名）
- テストスクリプトで最大化→Zoom切替、3形式の保存（ffprobeで 44100Hz/192kbps 確認）を確認済み
- APP_VERSION v2.7.2

### v2.7.1 save.png 色調整 (2026-11-01)（プロンプト直接指示）
- docs/icons/save.png の色を黒(#000000)→他アイコンと同じ #333333 に変更（アルファ保持）。元画像は docs/icons/bkup/save.png
- save.png を 150x150 → 96x96 にリサイズ（他アイコンとサイズ統一、余白の比率も同等）
- save アイコンはアプリ未使用（埋め込みBase64に無し）のため、ソース・バージョン変更なし

### v2.7.1 (2026-11-01)（プロンプト直接指示）
- アプリアイコン icon/morokoshi.ico を docs/icons/morokoshi.ico へ移動（icon/ フォルダは削除）
- morokoshi.spec: アイコンパスを SPECPATH 基準の絶対パス（ICON_PATH）で解決し、カレントディレクトリに依存しないよう変更。
  ファイルが見つからない場合はビルドをエラー停止（アイコン無しのexeが出来るのを防止）
- morokoshi.py: 開発実行時のアイコン検索先を ../docs/icons/morokoshi.ico に変更
- APP_VERSION を v2.7.1 に更新（ビルドは未実施）

### v2.7.0 マニュアル修正 (2026-10-10)（プロンプト直接指示）
- JP 更新履歴の文体を言い切り（体言止め）に統一（v1.4・v1.6.0 に残っていた「〜ます」も含む）
- あとがきと更新履歴の間の空白ページを削除（日英）。原因: あとがき末尾の区切り線がページからはみ出し、直後の改ページdivでさらに改ページ。
  区切り線と改ページdivを削除し、更新履歴見出し自体に page-break-before を指定
- PDF 再生成（53→51ページ）、dist/morokoshi270 内のPDF差し替え・zip再作成（exeは変更なし）

### v2.7.0 (2026-10-10)
- APP_VERSION を v2.7.0 に更新（ビルド前に確認済み・exeのウィンドウタイトルで v2.7.0 表示を確認）
- v2.6.1〜v2.6.14 の変更を公開: 波形上部の時間目盛り（全モード表示）、ズーム上限を表示幅1秒に変更、
  フィルター処理のFFT畳み込み化（フィルター再生時の音声出力遅れを解消）、アイコン枠・最下段レイアウト等の軽微な修正
- マニュアル更新（表紙・JP/EN 対象バージョン・波形エリアの時間目盛りとズーム上限・JP/EN 更新履歴 v2.7.0追加）・PDF 再生成
- exe ビルド・morokoshi270.zip リリース
- git tag v2.7.0
