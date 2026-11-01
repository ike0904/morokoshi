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

### v2.8.11 (2026-11-01) ← 最新（プロンプト直接指示）
- A・B（マーカーへ移動）と Ear Mode アイコンのツールチップを日本語化（訳の不足・未訳）
- 言語の選択（Help の右クリック）: ✓ を固定幅の列に分け、「English」「日本語」の左端を揃えた
- 最下段のメッセージ: 表示しきれない長さのときは横スクロール（NSF タイトルと同じ部品 _NsfMarquee を文字色指定付きで流用）。
  幅は従来の最大 230px から、音量バーの手前までに広げた
- 確認: ツールチップの訳、長いメッセージでスクロールが動くこと、言語ポップアップの表示（画面を撮影）
- APP_VERSION v2.8.11

### v2.8.10 (2026-11-01)（プロンプト直接指示）
- 表示言語の切り替えに対応（English / 日本語）。Help アイコンの右クリックで選択、設定に保存（settings の "lang"）。
  初回は OS の言語が日本語なら日本語、それ以外は English
  - 構成: src/lang/__init__.py（tr()・言語一覧 LANGUAGES）、src/lang/ja.py（英語の文字列 → 日本語の辞書）。
    第 3 言語は lang/ja.py をコピーして訳し、LANGUAGES に 1 行足すだけで追加できる。訳が無い文字列は英語のまま
  - ソースの英語をキーにして、表示する場所（ツールチップの show_tt、メッセージ欄の _status_sig）で訳す方式。
    ファイル名や数値が入る文は {0} の雛形で照合（固定部分の長い雛形を優先）。
    画面作成時に直接書く文字列（MIDI options、ボタン、ダイアログのタイトル、履歴なし など）は tr() で囲んだ
  - 画面上のパラメータ名（Tempo / Key / Fine / Speed / Beat / Bar / A<->B / Rew/FF）はマニュアルと合わせるため英語のまま
  - 言語を変えたら _rebuild_window で画面を作り直して反映
  - 確認: 雛形の訳（マーカー・保存・テンポ検出・読み込み失敗）、MIDI オプション画面（日本語で撮影しレイアウト確認）、
    English ⇔ 日本語の切り替え、言語ポップアップ
- マニュアル（md のみ）: Help アイコンの説明に右クリックでの言語切り替えを追記（JP/EN）
- APP_VERSION v2.8.10

### v2.8.9 (2026-11-01)（プロンプト直接指示）
- テンキー Enter の押しっぱなしも Enter+キー として扱う（従来の「押した直後 1.5 秒以内」も併用）
  - KeyRelease をアプリのイベントフィルターで拾って押下状態を管理。ウィンドウが非アクティブになったら解除（押したまま切り替えた場合の保険）
- タップテンポ中はテンキー 8 だけでタップ（従来は毎回 Enter が必要で、押し忘れると自動のテンポ検出が動いていた）
- 確認: キーイベントを送って、Enter 押しっぱなし＋4 → Set、離した後の 4 → 移動、Enter+8 → 8 → 8 で 3 タップ、タップテンポ外の 8 → テンポ検出
- マニュアル（md のみ）: タップテンポの手順と、テンキー Enter の注記を更新（JP/EN）
- APP_VERSION v2.8.9

### v2.8.8 (2026-11-01)（プロンプト直接指示）
- テンキー ＊ の Zoom を廃止し Save に割り当て（Z キーと最大化ボタンの Zoom はそのまま）。キー入力を送って Save が呼ばれることを確認
- MIDI options「No quantize」→「Quantize」（既定オン）。旧設定 no_quantize は反転して読み込む
  - nsf2mid 本体も v0.1.22 で GUI を「クオンタイズする」（既定オン）に変更し同期。nsf2mid のマニュアル・PDF も更新（v0.1.22、24 ページ）
- マニュアル（md・PDF 再生成 57 ページ、表紙は v2.8.0 のまま・確認用）: ショートカット表（Z のテンキー欄を「対応無し」、S に ＊）、
  オプション表・対処表の Quantize（JP/EN）
- APP_VERSION v2.8.8

### v2.8.7 (2026-11-01)（プロンプト直接指示）
- MIDI options「Keep pitch-drop drums as notes」→「Pitch-drop drums」（半音の閾値、既定 3、0 = 分けない）
  - nsf2mid 本体 v0.1.21 を同期: 閾値指定（--drop-drums）＋「鳴り始めから下がり続ける音」だけをドラムとする形の条件
    （グラディウスII のメロディのグリッサンドを除外、ロックマンの三角波タム・バルーンファイト 1ch の 2 フレーム 43→39 を拾う）
  - 旧設定の no_drop_drums / no_tri_drums=True は 0 として読み込む
  - 確認: 引数生成（3 / 0）、バルーンファイト #1 の 1ch 164 音 → ch 11
- マニュアル（md のみ）: オプション表の該当行を更新（JP/EN）
- APP_VERSION v2.8.7
- （追加指示）確認用にマニュアル PDF を再生成（57 ページ、表紙は v2.8.0 のまま）。dist の配布物は差し替えていない
  - MIDI options 表を画面の並び順に（Pitch-drop drums を Triplets の次へ）、出力される MIDI 表の列幅を調整（「11 / 12 / 13」の折り返し解消）

### v2.8.6 (2026-11-01)（プロンプト直接指示）
- MIDI 変換: 三角波キックに加え、矩形波（1ch・2ch）のタムも下降音ドラムとして分離。元の音程のまま MIDI ch 11/12/13（1ch/2ch/3ch）に出力
  - nsf2mid 本体 v0.1.20 で実装し tools/sync_nsf2mid.py で同期（詳細は nsf2mid の作業記録）
  - バルーンファイト・レッキングクルー（1ch のタム）、ファンタジーゾーン サンソフト版（1ch・2ch）で確認
- MIDI options「Keep triangle drums as notes」→「Keep pitch-drop drums as notes」（1〜3ch 共通、--no-drop-drums）。旧設定 no_tri_drums を引き継ぐ
- マニュアル（md のみ）: 変換の特徴・オプション表・出力される MIDI の表（ch 10 と ch 11〜13 に分けて記載）を更新（JP/EN）
- APP_VERSION v2.8.6

### v2.8.5 (2026-11-01)（プロンプト直接指示）
- MIDI options から Time signature を削除（拍子は常に自動判定）
  - 区間（テンポが変わる所で区切った部分）ごとの指定だが、もろこしでは区間を確認する手段が無いため
  - 書式チェック（赤枠・OK/保存の中止）も削除。旧設定の time_sig は無視される。nsf2mid 本体の拍子指定はそのまま
- マニュアル（md のみ）: オプション表・対処表の Time signature の行を削除（JP/EN）
- APP_VERSION v2.8.5

### v2.8.4 (2026-11-01)（プロンプト直接指示）
- MIDI options から Drum map を削除（もろこしではドラムの種類を確認する手段が無く、実質使えないため）
  - 旧設定に保存された drum_map は無視される。nsf2mid 本体（ログで種類を確認できる）の Drum map はそのまま
- マニュアル（md のみ）: オプション表・対処表の Drum map の行と「Drum map の書き方」節を削除（JP/EN）
- APP_VERSION v2.8.4

### v2.8.3 (2026-11-01)（プロンプト直接指示）
- MIDI options の「Rows per beat」を「Tempo」（Auto / Half / Double）に変更
  - nsf2mid 本体を v0.1.19 に改修（--tempo auto/half/double・--loops 0 = ループ検出なし、GUI も同じ仕様）し、
    tools/sync_nsf2mid.py で nsf2mid_core に同期。自動検出の結果を区間ごとに半分/2倍にするので、区間・3連・シャッフルの検出はそのまま
  - Loops=0 は nsf2mid に --loops 0 をそのまま渡す（v2.8.2 の --loops 1 --no-loop から変更）。旧設定の rows は無視（Tempo = Auto）
  - 確認: オプション画面の引数生成、Castlevania 2 を Loops=0・Tempo=Half で変換（56 BPM、ループ検出なし）
- マニュアル（md のみ。PDF は次の正式ビルド時）: 一般公開しない nsf2mid の名前をすべて削除
  - 「姉妹ツール nsf2mid と同じ変換エンジン」・末尾の nsf2mid 案内・更新履歴 v2.8.0 の記載を削除（JP/EN）
  - Drum map の書き方を nsf2mid マニュアル参照から、本マニュアル内の「Drum map の書き方」節に移した
  - オプション表: Rows per beat → Tempo、No loop detection を削除し Loops に「0 = ループ検出なし」を追記、対処表も合わせて修正
- APP_VERSION v2.8.3

### v2.8.2 (2026-11-01)（プロンプト直接指示）
- MIDI options の「No loop detection」を廃止し、Loops=0 で同じ動作（ループ検出なしで Max seconds 分を変換）に
  - Loops の範囲を 0〜16 に、ツールチップに「0: no loop detection」を追記
  - nsf2mid には Loops=0 のとき --loops 1 --no-loop を渡す
  - 旧設定で no_loop=True が保存されていた場合は Loops=0 として読み込む
  - マニュアルの該当記述は次の公開バージョンで更新する（今回は未変更）
- マニュアル PDF: MIDI options 表の「既定値」列が狭く「（空欄）」が2行になっていたのを修正（JP/EN とも列幅を調整）。
  指示により v2.8.0 のまま PDF を再生成（57 ページ）、dist/morokoshi280 の PDF・zip を差し替え
- APP_VERSION v2.8.2

### v2.8.1 (2026-11-01)（プロンプト直接指示）
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
