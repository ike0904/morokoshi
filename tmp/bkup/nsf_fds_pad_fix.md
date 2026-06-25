# FDS NSF ロード失敗修正指示書（bank不完全パディング）

## 原因

Exciting Soccer (FDS) がロードできない原因は libgme の問題ではなく、
NSFデータの末尾が4KBの境界に揃っていないことを libgme が処理できないため。

```
バンク切替: [2, 3, 4, 5, 0, 0, 0, 16]
INITアドレス: 0xF000  ← スロット7 (0xF000-0xFFFF) = bank16 が必要

ファイル内のbank16データ:
  必要サイズ: 4096 bytes
  実際のサイズ: 1088 bytes  ← 不完全！
  非ゼロバイト: 1076/1088  ← 有効なINITコードが含まれている

先頭バイト: 0x48(PHA) 0xA9 0xC0(LDA #$C0) 0x8D 0x17 0x40(STA $4017)...
→ APUの初期化コード。有効な6502コードである。
```

libgmeはbank16を完全な4KBページとして読もうとするが、
ファイルが短いためマップに失敗 → 0xF000-0xFFFFが未マップ → INIT実行不可 → 無音。

## 修正内容

`gme_open_data()` に渡す前に、Python側でNSFデータをゼロパッドして
全bankが完全な4KBになるよう補完する関数を追加する。

### 追加する関数

```python
def _nsf_pad_banks(nsf_raw: bytes) -> bytes:
    """
    NSFデータの末尾バンクが不完全な場合、4KB境界までゼロパッドして補完する。
    FDS NSFでbank値がファイルサイズを超える場合に有効。
    libgme に渡す前に呼ぶ。nsf_raw が正常なら変更なしでそのまま返す。
    """
    if len(nsf_raw) < 0x80:
        return nsf_raw

    banks = [nsf_raw[0x70 + i] for i in range(8)]
    max_bank = max(banks)

    # 最大bankを収容するために必要な最小ファイルサイズ
    min_required = 0x80 + (max_bank + 1) * 4096

    if len(nsf_raw) >= min_required:
        return nsf_raw  # 既に十分なサイズ

    # ゼロパッドで補完
    pad_size = min_required - len(nsf_raw)
    _log(f"NSF bank pad: max_bank={max_bank} file={len(nsf_raw)} "
         f"need={min_required} pad={pad_size}bytes")
    return nsf_raw + bytes(pad_size)
```

### 呼び出し箇所

`_nsf_decode_track`、`_nsf_detect_ch_used`、`_nsf_render` の
`gme_open_data()` を呼ぶ直前に `nsf_raw = _nsf_pad_banks(nsf_raw)` を挿入する。

または `_nsf_fmt()` 等でNSFを最初に読み込む箇所で一度だけ変換して
`NsfState.nsf_raw` に保存しておく方が、全関数に追記せずに済む。

```python
# _load_th 内、nsf_raw を取得した直後
nsf_raw = _nsf_pad_banks(nsf_raw)
nsf.nsf_raw = nsf_raw  # パッド済みデータを保持
```

### 計算の内訳（Exciting Soccer の場合）

```
max_bank = 16
min_required = 0x80 + 17 * 4096 = 128 + 69632 = 69760 bytes
現在のファイルサイズ = 66752 bytes
pad_size = 69760 - 66752 = 3008 bytes のゼロを末尾に追加
```

bank16 は 0xF000-0xFFFF にマップされ、
有効なINITコード(1088バイト) + ゼロ埋め(3008バイト) の構成になる。

---

## 検証方法

修正後のログに以下が出ること：

```
NSF bank pad: max_bank=16 file=66752 need=69760 pad=3008bytes
NSF ch0: used=True
NSF ch1: used=True
...
NSF ch5: used=True   ← FDSチャンネル
NSF render: mask=0b111111 ...
```

Exciting Soccer が音楽付きでロードされること。
他のNSFファイル（Excitebike等）では `pad=0` で変化なしなこと。

---

## 補足：この問題が起きるケース

bank値がファイルに含まれるbank数を超えているFDS NSFファイルで発生する。
これはNSFリッパーの実装によるもので、libgmeやもろこしタイムのバグではない。
FDS以外の通常NSFでは bank値は常にファイル内に収まるため、この問題は起きない。
