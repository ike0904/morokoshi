# NSF曲番号テキストボックスへの[<][>]ボタン追加 指示書

## 変更対象

`NsfPanel` クラスの `_build()` メソッド内、上段行（r1）のレイアウト。

## 変更後のレイアウトイメージ

```
変更前: [001] / [234]  [タイトルスクロール................................]
変更後: [<][001][>] / [234]  [タイトルスクロール.....................]
```

---

## 追加するウィジェット

`_track_edit`（曲番号テキストボックス）の左に `[<]` ボタン、右に `[>]` ボタンを追加する。
ウィジェット名は `self._track_prev_btn`（左）と `self._track_next_btn`（右）とする。

### ボタンの仕様

| 項目 | 値 |
|:---|:---|
| クラス | `QPushButton` |
| 表示テキスト | `<` / `>` |
| 幅 | `self.S(20)` |
| 高さ | `self.S(22)`（他のテキストボックスに合わせる） |
| スタイル | 下記参照 |
| クリック時の動作 | 曲番号を1だけデクリメント/インクリメントして `track_changed` シグナルを emit |

### ボタンのスタイル（既存のA/Bマーカーボタンと同じ形状）

```python
_btn_style = (
    f"QPushButton{{color:{FG};background:{BG3};border:1px solid {BORDER};"
    f"padding:0;font-size:{self.S(11)}px;}}"
    f"QPushButton:hover{{border:1px solid {FG2};}}"
    f"QPushButton:pressed{{background:{BG};}}"
)
```

---

## `_build()` の変更箇所

### 変更前（r1 上段の該当部分のみ抜粋）

```python
r1lo.addWidget(self._track_edit)
sep=QLabel("/"); sep.setFixedWidth(self.S(10)); ...
r1lo.addWidget(sep)
```

### 変更後

```python
# [<] ボタン
self._track_prev_btn = QPushButton("<")
self._track_prev_btn.setFixedWidth(self.S(20))
self._track_prev_btn.setFixedHeight(self.S(22))
self._track_prev_btn.setStyleSheet(_btn_style)
self._track_prev_btn.clicked.connect(self._on_prev_track)
r1lo.addWidget(self._track_prev_btn)

# 曲番号テキストボックス（既存。高さのみ S(20)→S(22) に変更）
self._track_edit.setFixedHeight(self.S(22))  # ← ここだけ変更
r1lo.addWidget(self._track_edit)

# [>] ボタン
self._track_next_btn = QPushButton(">")
self._track_next_btn.setFixedWidth(self.S(20))
self._track_next_btn.setFixedHeight(self.S(22))
self._track_next_btn.setStyleSheet(_btn_style)
self._track_next_btn.clicked.connect(self._on_next_track)
r1lo.addWidget(self._track_next_btn)

# 以降（"/", total_lbl, スペーサー, タイトル）は変更なし
sep=QLabel("/"); sep.setFixedWidth(self.S(10)); ...
```

---

## 追加するメソッド

`NsfPanel` クラスに以下の2メソッドを追加する。
既存の `_emit_track_changed` の直前あたりに置くのが自然。

```python
def _on_prev_track(self):
    """[<]ボタン: 前の曲へ"""
    v = max(0, self._cur - 1)
    if v != self._cur:
        self._cur = v
        self._track_edit.setText(f"{v+1:03d}")
        self.track_changed.emit(self._cur)

def _on_next_track(self):
    """[>]ボタン: 次の曲へ"""
    v = min(self._total - 1, self._cur + 1)
    if v != self._cur:
        self._cur = v
        self._track_edit.setText(f"{v+1:03d}")
        self.track_changed.emit(self._cur)
```

### 既存の `_track_wheel` / `_track_move` との違い

既存のホイール・ドラッグ操作は `_wheel_timer`（300ms ディレイ）を経由して emit している。
ボタンクリックは即時 emit で問題ない（ユーザーが明示的に押した操作なのでディレイ不要）。

---

## `set_info()` 内でのボタン有効/無効制御（推奨）

曲の先頭・末尾では対応ボタンをグレーアウトする。

```python
def set_info(self, total, cur_0, title):
    self._total = max(1, total)
    self._cur = cur_0
    self._total_lbl.setText(f"{self._total:03d}")
    self._track_edit.setText(f"{self._cur+1:03d}")
    self._title.setText(title)
    # ボタンの有効/無効を更新
    self._track_prev_btn.setEnabled(self._cur > 0)
    self._track_next_btn.setEnabled(self._cur < self._total - 1)
```

グレーアウト時のスタイルは Qt のデフォルト（`setEnabled(False)` で自動的にテキストが薄くなる）で十分。
必要であれば `QPushButton:disabled` セレクタをスタイルに追加してもよい。

---

## 合わせて変更する箇所：`_track_edit` の高さ統一

本機能追加のタイミングで、`_track_edit` の高さを他のテキストボックスに統一する。

```python
# 変更前
self._track_edit.setFixedHeight(self.S(20))

# 変更後
self._track_edit.setFixedHeight(self.S(22))
```

`r1` の高さは `self.S(24)` のままで問題ない（22px のウィジェットは余裕で収まる）。

---

## 変更不要な箇所

- `_track_press` / `_track_move` / `_track_release` / `_track_leave` / `_track_wheel`：変更なし
- `_emit_track_changed`：変更なし
- チャンネルボタン行（下段 r2）：変更なし
- `track_changed` シグナルの受け取り側（メインウィンドウ）：変更なし
