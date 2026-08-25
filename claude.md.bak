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

### v2.0.13 (2026-08-25) ← 最新
- 【Python修正】NSF/GBS の総時間スタートを 1:00 に固定・下限仕様を整理
  - 初期ロード時 `natural_end=True` かつ `actual_dur > 10` → wav をゼロパディング（60秒）、view_sec=1:00
  - `has_m3u=True`（GBS メタ曲時間あり）→ スタート = メタ時間（下限 = メタ時間）
  - `initial_view_sec` フィールドを track_data に追加（スタート値 = 絶対下限）
  - extend_track のクランプを `lower = max(initial_view_sec, trim_sec or 0)` に変更
  - これにより：スタートからのデクリメント不可・終端検出時はその位置が下限に昇格

### v2.0.12 (2026-08-25)
- 【Python修正】総再生時間のステップを常に「0:10 + 1分単位」に固定
  - `_dur_step_list` から initial_sec を特別追加する処理を削除
- 【Python修正】終端検出後の下限を「1分単位切り上げ」に変更
  - 3:20で終端検出 → 下限は4:00（ceil(200/60)*60=240秒）
  - NSF/SPC/GBS 全 extend_track で `math.ceil(trim_sec/60)*60` でクランプ

### v2.0.11 (2026-08-25)
- 【Python修正】NSF/SPC/GBS の `extend_track` に終端検出後の下限ガード追加
  - 一度 `trim_sec` が確定した後は `new_view_sec = max(new_view_sec, trim_sec)` で下回れないよう制限
  - 例：3:20で終端検出→3:20が最短下限。4:00に延長可能、戻すときは3:20まで

### v2.0.10 (2026-08-25)
- 【Python修正】`gbs_extend_track` に `trim_sec`/`user_extended`/`no_trim` ロジックを追加
  - NSF/SPC と同様のパターンで GBS も終端検出バイパス機能に対応
  - `no_trim=True` 時は `view_sec = new_view_sec`（ユーザー指定秒をそのまま保持）
  - ch 再検出後の再レンダリングブロックにも `no_trim` を引き継ぐよう修正
- 【Python修正】`silence_max` 撤廃・tempo スケーリング修正・速度ロード時の gme_tempo チェック追加
  （v2.0.10 でまとめてコミット）
- 【Python修正】`_nsf_render`/`_spc_render`/`_gbs_render` に `no_trim=False` パラメータ追加
- 【Python修正】全 `track_data` 初期化に `trim_sec`/`user_extended` フィールド追加
- 【Python修正】`nsf_extend_track`/`spc_extend_track`/`gbs_extend_track` を更新

### v2.0.9 (2026-08-24)
- 【DLL修正】ch2 頭削りバグ修正（根本原因特定・1行修正）
  - 根本原因: `before_silence_detection_()` の burn loop 終了後、Multi_Buffer に PLAY フレームの音データが残存
  - この残存データを `redo_silence_detection_()` の最初の `fill_buf()` が「即音」として検出し `silence_count=0` → 頭削り
  - 修正: `Classic_Emu::clear_buf_impl_()` で `before_silence_detection_()` の直後に `buf->clear()` を追加（1行）
  - 効果: ch2 の頭削り解消（silence_count が正しく蓄積される）

### v2.0.8 (2026-08-24) ※ v2.0.9 で頭削りバグ修正
- 【DLL修正】NSF INIT ノイズ根本修正（DW3 track7/9/26 ch2/ch4 等）
  - `Classic_Emu::clear_buf_impl_()` に `before_silence_detection_()` 仮想フックを追加
  - `Nsf_Emu::before_silence_detection_()` でINITフレームを全チャンネルミュートで焼き切り後、APUレジスタを無音化（$4000/$4004=0x10, $4008=0x80, $400C=0x10）
  - `Music_Emu::redo_silence_detection_()` のループ後 `silence_count` / `emu_time` リセットを廃止し、曲頭の本来の無音区間をPlayback出力に保持
  - 効果: INIT ノイズ消滅 + 曲頭無音（PLAY以降）を正確に保持（INITフレーム67ms分は除外されるが誤差範囲）

### v2.0.7 (2026-08-24)
- 【リバート】v2.0.5/v2.0.6 の Python 側 INIT ノイズ除去コードを全廃
  - v2.0.6 のバースト検出ロジックが「冒頭の短い音符→無音」のパターンを誤検知し他の曲の頭を削る副作用があった
  - gme_clear_blip_buffer (DLL) がINITノイズを担当する設計に戻す
  - NSF ch2 (DW3 track7) の INIT ノイズ残留問題は未解決だが、他の曲を壊す修正は行わない

### v2.0.6 (2026-08-24)
- 【失敗】バースト検出で他の曲の頭を誤って削る副作用 → v2.0.7 でリバート

### v2.0.5 (2026-08-24)
- 【失敗】_GAP_MIN=500ms 設定ミスで全件スキップ → v2.0.6→v2.0.7 でリバート

### v2.0.4 (2026-08-24)
- 【バグ2修正】NSF ZIP ファイルのセッション保存/復元が機能しない問題を修正
  - 原因: `_load_nsf_zip` が ZIP を一時ディレクトリに展開して `_load_nsf` を呼ぶため、`_file_hash` が毎回異なる一時パスのハッシュになっていた
  - 修正: `_load_nsf` 呼び出し後に `_file_hash` と `nsf.path` を ZIP ファイルのパスで上書き
- 【潜在バグ修正】ファイルロード時に `_played_orig` がリセットされない問題を修正
  - 修正: 全ロード関数（NSF/SPC/GBS/WAV等）に `with self._rt_lock: self._played_orig = 0` を追加
  - これにより「前のファイルの再生位置が ch solo 時の seek_sec に影響する」問題を解消
- 【デバッグログ追加】`_apply_new_wav`・各 `_start_ch_render` に seek_sec の詳細ログを追加
- 【NSF レンダリングログ】head_silence（頭の無音長さ）をログ出力に追加

### v2.0.3 (2026-08-24)
- ゲームモードで無音始まりのchを単独選択すると無音が削られるバグを修正
- 原因: ch切替レンダリング（バックグラウンドスレッド）完了時に `current_sec()` を参照していたため、レンダリング中に再生位置が進んでしまい、無音頭部をスキップした位置に移動していた
- 修正: NSF/SPC/GBS 各 `_start_ch_render` でクリック時点の `current_sec()` を `seek_sec` として記録し、シグナル経由で `_apply_new_wav` に渡すよう変更

### v2.0.2 (2026-08-23)
- 波形ツールチップから「Drag←→ pos/A/B line: Move it」を削除

### v2.0.1 (2026-08-23)
- 波形左右ドラッグを「スクロール」から「A-B範囲ドラッグ設定」に変更（スクロールは波形下部スクロールバーで行う）
- スピード調整を4段階（×1/1・×1/2・×1/4・×1/8）のみに変更

### v2.0.0 (2026-08-17)
- マニュアル更新（JP/EN 更新履歴・表紙バージョン）・PDF 再生成
- exe ビルド・morokoshi200.zip リリース
- ※ v1.9.0 → v2.0.0 の間の中間バージョン（右端インクリメント）は未発行。次回以降は作業のたびにインクリメントすること。

### v2.0.0 実装内容（v1.9.0 からの変更）
- ゲーム音楽（NSF/SPC/GBS）の低速再生を gme_set_tempo に切り替え（音質劣化なし）
- NSF/SPC/GBS のトラックごとに Speed・Key・Fine・AB 等を独立保存
- ch ON/OFF 時に gme_tempo を引き継ぐよう修正

### v1.9.0 (2026-08-09)
- SPEED_VALUES に 0.1・0.15 を追加（9段階に拡張）
- マニュアル更新（JP/EN Speed欄・更新履歴）
- PDF 再生成・exe ビルド・morokoshi190.zip リリース
