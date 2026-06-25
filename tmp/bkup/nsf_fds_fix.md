# NSF ロード失敗（FDS音源ファイル）修正指示書

## 症状

`Exciting Soccer - Konami Cup (FDS)(1988)(Konami).nsf` がロードできない。
再生しても無音になる。

## ログの証拠

```
NSF ch0: used=False
NSF ch1: used=False
NSF ch2: used=False
NSF ch3: used=False
NSF ch4: used=False
NSF ch5: used=False
NSF render: mask=0b0 ch_count=6 dur=10.0s natural_end=True
```

全チャンネルが `used=False` → `ch_mask=0` → 全ミュートでrender → 無音

## 根本原因

### 原因1：`_nsf_detect_ch_used` のmute-before方式

`_nsf_detect_ch_used` は各chを1つずつ有効にし、他をミュートしてから
`gme_start_track()` を呼ぶ方式（mute-before）を使っている。

以前の調査で判明している問題：
mute-beforeでDMCチャンネル（ch4）をミュートすると、
libgmeがDMC DMAを省略してCPUタイミングが変化する。
この変化にFDSゲームの音楽ドライバが敏感で、全チャンネルが無音になる。

### 原因2：mask=0 のフォールバックがない

`ch_used` が全て `False` になった場合でも `ch_mask=0` のまま render を呼ぶため、
全チャンネルミュートの無音wavが生成される。

---

## 修正内容

### 修正1：mask=0 フォールバック（即効・最優先）

`_load_th` および `_nsf_switch_track` の中で、
`ch_used` 判定後に `ch_mask == 0` であれば全ch ONで再チェックするフォールバックを追加する。

```python
# ch_used判定後、ch_maskが0（全て無音判定）の場合のフォールバック
if ch_mask == 0:
    _log("NSF ch_mask=0: fallback to all-ch render to verify")
    # 全ch ON で短くrenderして音があるか確認
    _all_mask = (1 << ch_count) - 1
    _test_wav, _, _ = _nsf_render(gme_lib, nsf_raw, track_idx,
                                   _all_mask, ch_count, dur_sec=3.0)
    if float(np.max(np.abs(_test_wav))) > NSF_SILENCE_THRESH:
        # 音が出た → 全ch usedとして扱う
        ch_used = [True] * ch_count
        ch_mask = _all_mask
        _log(f"NSF fallback: ch_mask={bin(ch_mask)} (all used)")
    else:
        _log("NSF fallback: truly silent, ch_mask remains 0")
```

この修正を追加する箇所：
- `_load_th` 内の `ch_used = _nsf_detect_ch_used(...)` の直後（2箇所ある場合は両方）
- `_nsf_switch_track` 内の同様の箇所

---

### 修正2：`_nsf_detect_ch_used` をmute-after方式に変更（長期）

mute-beforeをやめ、`gme_start_track()` の後にミュートを設定する。
最初のNフレームはINITノイズが乗るが、ch_used判定には十分な情報が得られる。

```python
def _nsf_detect_ch_used(gme_lib, nsf_raw, track_idx, ch_count,
                         detect_sec=3.0, scb=None):
    """各chが音を出すかどうかを判定する（mute-after方式）。"""
    ch_used = []
    CHUNK = NSF_FRAME_SAMPLES
    SKIP_FRAMES = 3      # INITノイズをスキップ（先頭3フレーム分を判定対象外）
    target_s = int(detect_sec * NSF_SR)

    for ch in range(ch_count):
        if scb: scb(f"NSF: ch {ch+1}/{ch_count} 判定中...")
        _buf = _ct.create_string_buffer(nsf_raw, len(nsf_raw))
        emu = _ct.c_void_p()
        err = gme_lib.gme_open_data(_buf, len(nsf_raw), _ct.byref(emu), NSF_SR)
        if err is not None:
            ch_used.append(False); continue

        # ★ start_track を先に呼ぶ（mute-after方式）
        err2 = gme_lib.gme_start_track(emu, track_idx)
        if err2 is not None:
            gme_lib.gme_delete(emu); ch_used.append(False); continue

        # ★ start_track の後にミュートを設定
        for i in range(ch_count):
            gme_lib.gme_mute_voice(emu, i, 0 if i == ch else 1)

        buf16 = (_ct.c_int16 * (CHUNK * 2))()
        samples = []; rendered = 0

        # 先頭 SKIP_FRAMES フレームはINITノイズのため読み飛ばす（判定には使わない）
        for _ in range(SKIP_FRAMES):
            if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None:
                break

        # 残りを判定用データとして収集
        while rendered < target_s:
            if gme_lib.gme_play(emu, CHUNK * 2, buf16) is not None: break
            mono = np.frombuffer(bytes(buf16), dtype=np.int16)[::2].copy()
            need = target_s - rendered
            if len(mono) > need: mono = mono[:need]
            samples.append(mono); rendered += len(mono)

        gme_lib.gme_delete(emu)

        if samples:
            arr_f = np.concatenate(samples).astype(np.float32) / 32768.0
            used = float(np.max(np.abs(arr_f))) > NSF_SILENCE_THRESH
        else:
            used = False
        _log(f"NSF ch{ch}: used={used}")
        ch_used.append(used)

    return ch_used
```

**変更点のまとめ：**
- `gme_start_track()` を `gme_mute_voice()` より先に呼ぶ
- 先頭 `SKIP_FRAMES`（3フレーム）は判定対象から除外
  （INITノイズが全ch一致で乗るため、used判定が誤って全ch Trueになるのを防ぐ）

---

## 検証方法

Exciting Soccer でロードしたとき：

```
# 修正1のフォールバックが動いた場合
NSF ch_mask=0: fallback to all-ch render to verify
NSF fallback: ch_mask=0b111111 (all used)
NSF render: mask=0b111111 ch_count=6 dur=60.0s ...

# 修正2のmute-after方式が正しく動いた場合
NSF ch0: used=True
NSF ch1: used=True
...
NSF ch5: used=True   ← FDSチャンネル
```

音楽が再生されることを確認する。
他のNSFファイル（Excitebike等）で退行がないことも確認する。
