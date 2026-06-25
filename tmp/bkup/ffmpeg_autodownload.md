# ffmpeg 自動ダウンロード実装指示書

## 概要

exe(pl)と同じフォルダに `ffmpeg.exe` が無い場合、
BtbN の LGPL ビルドから自動的にダウンロード・展開する。
libgme.dll の探索パターンと同じ設計にする。

ライセンス: BtbN LGPL ビルドは LGPL 2.1 のため、
もろこしタイムのクローズドソース配布と組み合わせて問題ない。

---

## 変更箇所

### 1. ffmpegの探索・ダウンロード関数を追加

`_load_gme_lib()` の近く（ファイル上部のユーティリティ関数群）に追加する。

```python
# ─── ffmpeg 自動取得 ──────────────────────────────────────────────────────────

_FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)
_FFMPEG_EXE_IN_ZIP = "ffmpeg-master-latest-win64-lgpl/bin/ffmpeg.exe"

def _get_app_dir() -> str:
    """exeまたはスクリプトが置かれているディレクトリを返す。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _find_ffmpeg() -> str | None:
    """
    ffmpeg.exe のパスを返す。見つからなければ None。
    探索順: exeと同フォルダ → dist/ → PATH
    """
    base = _get_app_dir()
    candidates = [
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(base, "dist", "ffmpeg.exe"),
        "ffmpeg",  # PATH上のffmpeg（開発時のフォールバック）
    ]
    for p in candidates:
        try:
            r = subprocess.run(
                [p, "-version"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0,
            )
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None

def _download_ffmpeg(scb=None) -> str:
    """
    BtbN LGPL ビルドから ffmpeg.exe をダウンロードして
    exeと同じフォルダに展開する。
    scb: ステータスコールバック(str) または None。
    戻り値: 展開した ffmpeg.exe の絶対パス。
    失敗時は RuntimeError を送出。
    """
    import urllib.request, zipfile, io

    dest_dir = _get_app_dir()
    dest_path = os.path.join(dest_dir, "ffmpeg.exe")

    if scb: scb("ffmpeg をダウンロード中... (約40MB、初回のみ)")
    _log(f"ffmpeg download: {_FFMPEG_URL}")

    try:
        with urllib.request.urlopen(_FFMPEG_URL, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            buf = io.BytesIO()
            chunk_size = 65536
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                buf.write(chunk)
                downloaded += len(chunk)
                if scb and total:
                    pct = downloaded * 100 // total
                    scb(f"ffmpeg をダウンロード中... {pct}%")
    except Exception as e:
        raise RuntimeError(f"ffmpeg のダウンロードに失敗しました: {e}")

    if scb: scb("ffmpeg を展開中...")
    _log(f"ffmpeg extract: {len(buf.getvalue())} bytes")

    try:
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            # zip内の ffmpeg.exe だけを取り出す
            zf.extract(_FFMPEG_EXE_IN_ZIP, path=dest_dir + "/_ffmpeg_tmp")
        # 展開先から移動
        tmp_path = os.path.join(dest_dir, "_ffmpeg_tmp", _FFMPEG_EXE_IN_ZIP)
        import shutil
        shutil.move(tmp_path, dest_path)
        shutil.rmtree(os.path.join(dest_dir, "_ffmpeg_tmp"), ignore_errors=True)
    except Exception as e:
        raise RuntimeError(f"ffmpeg の展開に失敗しました: {e}")

    _log(f"ffmpeg installed: {dest_path}")
    if scb: scb("ffmpeg のインストール完了")
    return dest_path

def _ensure_ffmpeg(scb=None) -> str:
    """
    ffmpeg.exe が使用可能な状態にして、そのパスを返す。
    存在すればそのパス、なければダウンロードして返す。
    失敗時は RuntimeError を送出。
    """
    path = _find_ffmpeg()
    if path:
        return path
    return _download_ffmpeg(scb=scb)

# ─────────────────────────────────────────────────────────────────────────────
```

---

### 2. `Engine.load()` の ffmpeg 呼び出しを修正

現在:
```python
cmd = ["ffmpeg", "-y", "-i", path, "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", wtmp]
try:
    _cf = subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
    r = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=_cf)
    if r.returncode != 0: raise RuntimeError(r.stderr.decode(errors="replace")[-400:])
except FileNotFoundError:
    raise RuntimeError("ffmpeg が見つかりません")
```

変更後:
```python
ffmpeg_path = _ensure_ffmpeg(scb=scb)
cmd = [ffmpeg_path, "-y", "-i", path, "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", wtmp]
try:
    _cf = subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
    r = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=_cf)
    if r.returncode != 0: raise RuntimeError(r.stderr.decode(errors="replace")[-400:])
except FileNotFoundError:
    raise RuntimeError("ffmpeg が見つかりません（ダウンロードを再試行してください）")
```

---

## 動作フロー

```
音楽ファイルを開く
↓
_ensure_ffmpeg() を呼ぶ
↓
ffmpeg.exe が exe(pl)と同フォルダ or dist/ or PATH にある？
  → Yes: そのパスを使って変換処理を開始（従来通り）
  → No:  BtbN LGPL ビルドをダウンロード（約40MB）
          ↓
          exeと同フォルダに ffmpeg.exe を展開
          ↓
          変換処理を開始
```

---

## 補足事項

**ダウンロード失敗時の挙動**
- `RuntimeError` を送出 → 呼び出し元（`_load_th`）がエラーとして表示する
- 現在のエラー表示の仕組みをそのまま流用する

**2回目以降の起動**
- `_find_ffmpeg()` でローカルの ffmpeg.exe が見つかるため、ダウンロードは走らない

**exeが無くスクリプトで実行している場合**
- `_get_app_dir()` はスクリプトのあるディレクトリを返す
- 開発時は PATH 上の ffmpeg が `_find_ffmpeg()` で先に見つかることが多い

**zip内のパス**
- BtbN の zip 内の ffmpeg.exe は `ffmpeg-master-latest-win64-lgpl/bin/ffmpeg.exe`
- URL が変わった場合は `_FFMPEG_URL` と `_FFMPEG_EXE_IN_ZIP` の2箇所だけ修正する

**ライセンス表記**
- アプリの README または about ダイアログに以下を追記する:
  ```
  ffmpeg (LGPL build by BtbN) を使用しています。
  https://github.com/BtbN/FFmpeg-Builds
  LGPL v2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
  ```
