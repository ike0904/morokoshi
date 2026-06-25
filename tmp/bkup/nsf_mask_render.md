# NSF チャンネル設計変更：マスク合算レンダリング方式

## 背景・経緯

チャンネルごとに個別wavを作成して合算する現在の方式では、
gme_start_track() のINIT期間中にミュートが間に合わず、
全chに同じ全体ミックス音が混入する。
これをN ch分合算するとN倍増幅になり、先頭ノイズとして聴こえる。
この問題はlibgmeの内部構造上、公開APIの範囲では根本解決不可能と判断。

## 新方式の考え方

「チャンネルごとに分けて後で合算」をやめ、
「現在ONになっているチャンネルを最初からまとめてミュートし、1本のwavとして生成」する。

```
変更前：
  ch0のwav（ch1-4ミュート）
  ch1のwav（ch0,2-4ミュート）  → 合算 → 5倍増幅ノイズ
  ...

変更後：
  [ON中の全ch]を1本のwavに（それ以外をミュート）→ これが直接出力される
```

Winampのチャンネルミュートが同じ方式のため、同等の品質になる見込み。

## ノイズについて

出だしに一瞬だけ全ch音が鳴ることは残る可能性がある。
しかし「N倍増幅された全ch音」ではなく「1倍の全ch音」になるため、
音量的には大幅に改善される。現時点での最適解とする。

---

## アーキテクチャ変更

### 削除するもの

- `ch_data: list[float32 array]` ― chごとの個別wav配列（N本）
- `ch_emus: list[c_void_p]` ― chごとの個別emuインスタンス（N個）
- `_nsf_decode_track()` 内のchループ（N回レンダリング）
- 先頭ノイズ対策コード（ゼロ化・1/N割り算など、全て不要になる）
- ミキサー（ch_on フラグを見てch_dataを合算する処理）

### 追加・変更するもの

**`_nsf_render(gme_lib, nsf_raw, track_idx, ch_mask, ch_count, dur_sec)` 関数（新規）**

`ch_mask`（int）: ビットマスク。ビットiが1ならchiをON、0ならミュート。
指定マスクで1本のwavを生成して返す。

```python
def _nsf_render(gme_lib, nsf_raw, track_idx, ch_mask, ch_count, dur_sec=None):
    """
    指定チャンネルマスクでNSFを1パスレンダリングして返す。
    戻り値: (float32 mono array, natural_end: bool, actual_dur_sec: float)
    """
    if dur_sec is None:
        dur_sec = NSF_DEFAULT_DUR_SEC

    _buf = _ct.create_string_buffer(nsf_raw, len(nsf_raw))
    emu = _ct.c_void_p()
    err = gme_lib.gme_open_data(_buf, len(nsf_raw), _ct.byref(emu), NSF_SR)
    if err is not None:
        return np.zeros(int(dur_sec * NSF_SR), dtype=np.float32), True, dur_sec

    # マスクに従ってミュートを設定（ONのchだけ残す）
    for i in range(ch_count):
        muted = 0 if (ch_mask >> i) & 1 else 1
        gme_lib.gme_mute_voice(emu, i, muted)

    err2 = gme_lib.gme_start_track(emu, track_idx)
    if err2 is not None:
        gme_lib.gme_delete(emu)
        return np.zeros(int(dur_sec * NSF_SR), dtype=np.float32), True, dur_sec

    CHUNK = NSF_FRAME_SAMPLES
    target_s = int(dur_sec * NSF_SR)
    min_s = int(NSF_MIN_DURATION * NSF_SR)
    buf16 = (_ct.c_int16 * (CHUNK * 2))()
    samples = []; rendered = 0

    while rendered < target_s:
        if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None:
            break
        mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
        need = target_s - rendered
        if len(mono) > need:
            mono = mono[:need]
        samples.append(mono)
        rendered += len(mono)

    gme_lib.gme_delete(emu)

    target_len = max(rendered, min_s)
    if rendered < target_len:
        samples.append(np.zeros(target_len - rendered, dtype=np.int16))
    arr = np.concatenate(samples)[:target_len] if samples else \
          np.zeros(target_len, dtype=np.int16)
    arr_f = arr.astype(np.float32) / 32768.0

    # 自然終了検出（末尾NSF_SILENCE_SEC秒が無音かどうか）
    natural_end = _nsf_detect_natural_end(arr_f)

    return arr_f, natural_end, rendered / NSF_SR
```

**`NsfState` の変更**

```python
# 変更前
ch_data: list[float32 array]   # chごとの個別wav（N本）
ch_used: list[bool]
ch_emus: list[c_void_p]
ch_on:   list[bool]

# 変更後
wav:         float32 array     # 現在のch_maskで生成された1本のwav
ch_used:     list[bool]        # chが使用されているか（グレーアウト判定用）
ch_on:       list[bool]        # 各chのON/OFF状態
ch_mask:     int               # 現在のチャンネルマスク（ch_onのビット表現）
emu_ref:     c_void_p or None  # 延長用インスタンス（1個のみ）
```

**`ch_used` の判定方法**

chごとの個別wavがなくなるため、使用判定は別途行う。
初回ロード時に**全ch ON**で1回追加レンダリングし、
フレームごとのピーク値でch使用判定を行う（ch_on変化のたびの再レンダリングとは別）。
または既存の「mute voice して1chずつ計測」方式のまま維持してもよい（設計判断に委ねる）。

---

## チャンネルON/OFF操作の流れ

```
ユーザーがチャンネルボタンを押す
↓
ch_on[ch] を反転（またはSHIFT+クリックでsolo化）
↓
新しい ch_mask を計算
↓
バックグラウンドスレッドで _nsf_render(ch_mask) を実行
↓
レンダリング完了したら Engine.data を差し替え、現在位置を維持して再生継続
```

**再生位置の維持：**

再レンダリング中は現在の `wav` で再生を継続する。
新しい `wav` が完成したら、現在の再生位置（サンプル位置）を保持したまま差し替える。
差し替え時のクリック防止のため、数ms（256サンプル程度）のフェードを挟む。

---

## 延長機能との整合

「延長」は「`dur_sec` を増やして再レンダリング」するだけ。

```python
def _nsf_extend(nsf_state, add_sec):
    new_dur = nsf_state.actual_dur_sec + add_sec
    wav, natural_end, actual = _nsf_render(
        gme_lib, nsf_state.nsf_raw, nsf_state.cur_track,
        nsf_state.ch_mask, nsf_state.ch_count, dur_sec=new_dur
    )
    # 差分を取り出して既存wavに連結する場合:
    new_part = wav[len(nsf_state.wav):]
    nsf_state.wav = np.concatenate([nsf_state.wav, new_part])
    nsf_state.actual_dur_sec = actual
    nsf_state.natural_end = natural_end
```

延長時も差分のみ連結するため、継ぎ目は発生しない（同じ関数の続きなので）。

ただし **延長時のemuインスタンス保持（旧方式）は不要になる**。
`_nsf_render` は毎回 `gme_open_data` から作り直す方式でよい。
（延長時のみ速度が気になる場合は、インスタンスを1個保持して続きから生成する最適化を後で追加する）

---

## 初回ロード時のフロー

```
1. ch_used の判定
   全ch ON でレンダリング（または簡易な個別ch計測）し、
   使用中のchを特定してグレーアウト判定に使う。

2. 初回 wav の生成
   使用中chが全て ON の ch_mask で _nsf_render() を実行。
   これが再生用 wav の初期状態。

3. 自然終了チェック
   natural_end が False なら総再生時間ボックスを赤点滅・編集可能にする。
```

---

## 変更による影響範囲

| 変更内容 | 影響 |
|:---|:---|
| chごとのwav・emu管理が1本に集約 | NsfState がシンプルになる |
| 初回ロードが1パスに（ch_used判定で+1パス） | 初回ロードが大幅に速くなる |
| ch切り替え時に1パスのレンダリングが走る | 小さな待ち時間が発生（許容範囲） |
| 先頭ノイズ対策コード全削除 | コードがシンプルになる |
| ミキサー（ch_data合算）が不要 | コードがシンプルになる |
| 延長時のemu保持が不要 | 管理がシンプルになる |

---

## 残る既知の問題

出だしに一瞬だけ全ch音が鳴る可能性がある（ミュートが効くまでの数フレーム）。
ただし「1倍の全ch音」であり、従来の「N倍増幅」ではないため大幅に改善される。
これは現時点での最適解とし、将来的に気になる場合は別途検討する。
