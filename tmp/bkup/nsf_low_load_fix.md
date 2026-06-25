# NSF LOAD < 0x8000 対応指示書（トランポリン方式）

## 問題

`Deep Dungeon - Madou Senki` など、LOADアドレスが 0x8000 未満の NSF ファイルが
libgme に拒否されて無音になる。

```
Deep Dungeon: LOAD=0x6230 INIT=0x627B PLAY=0x62DE
→ libgme は 0x8000 未満への LOAD を受け付けないため gme_open_data がエラー
→ 全チャンネル used=False → mask=0 → 無音
```

FDS ゲームでは、コードが「ディスクから RAM (0x6000-0x7FFF) にロードされる」
形式のものがある。NSF リッパーがそのアドレスをそのまま LOAD に設定した結果。

---

## 解決策：Python で NSF を前処理（libgme 改造不要）

コードを RAM 部分と ROM 部分に分け、
ROM 部分は直接 0x8000 に配置し、
RAM 部分は 6502 コピールーチン（トランポリン）で実行時にコピーする。

### 変換後のメモリレイアウト（Deep Dungeon の例）

```
変換前 (libgme 非対応):
  LOAD=0x6230: 全8642バイトを 0x6230-0x83F1 に配置しようとする
  → 0x6230-0x7FFF はRAM領域 → libgme が 0x6230 への LOAD を拒否

変換後 (libgme 対応):
  LOAD=0x8000
  0x8000-0x83F1: ROM部分 (1010バイト、直接配置)
  0x8400-0x843F: トランポリン (64バイト、INIT として呼ばれる)
  0x8440-0xA20F: RAM部分データ (7632バイト、ROM に仮置き)

実行時:
  INIT (0x8400) = トランポリンが実行される
  → 0x8440-0xA20F (ROM上) から 0x6230-0x7FFF (RAM) へ 7632バイトをコピー
  → JMP 0x627B (元の INIT コードへ。これはRAMにコピー済み)
  PLAY (0x62DE) は変更なし (RAM上のコードへ)
```

---

## 実装：`_nsf_pad_banks` の直後に `_nsf_fix_low_load` を追加

```python
def _nsf_fix_low_load(nsf_raw: bytes) -> bytes:
    """
    LOADアドレスが 0x8000 未満の NSF を libgme 対応形式に変換する。
    コードを RAM部分 (LOAD-0x7FFF) と ROM部分 (0x8000-) に分割し、
    6502トランポリンで RAM部分を実行時にコピーする。
    libgme 改造不要。
    """
    if len(nsf_raw) < 0x80:
        return nsf_raw

    load = nsf_raw[8] | (nsf_raw[9] << 8)
    init = nsf_raw[10] | (nsf_raw[11] << 8)

    if load >= 0x8000:
        return nsf_raw  # 通常のNSF、変換不要

    code = nsf_raw[0x80:]
    code_len = len(code)

    # RAM部分: LOAD〜0x7FFF  (実行時にコピーが必要)
    # ROM部分: 0x8000〜      (直接 0x8000 に配置)
    ram_size = 0x8000 - load
    ram_part = code[:ram_size]
    rom_part = code[ram_size:]

    # トランポリンをROM部分の直後、64バイト境界に配置
    trampoline_offset = (len(rom_part) + 63) & ~63   # ROM部分サイズを64B境界に切り上げ
    TRAMPOLINE_ADDR = 0x8000 + trampoline_offset      # = 0x8400 (Deep Dungeonの場合)
    RAM_PART_ADDR   = TRAMPOLINE_ADDR + 64            # = 0x8440

    src_lo  = RAM_PART_ADDR & 0xFF
    src_hi  = (RAM_PART_ADDR >> 8) & 0xFF
    dst_lo  = load & 0xFF
    dst_hi  = (load >> 8) & 0xFF
    n_pages = (ram_size + 255) // 256  # コピーページ数（切り上げ）

    # 6502 コピールーチン（37バイト、64バイトにパッド）
    # ゼロページ $00-$03 をソース・デスティネーションポインタとして使用
    # ページ単位のフォワードコピー（ソース > デスティネーションなので安全）
    trampoline_code = bytes([
        0xA9, src_lo, 0x85, 0x00,   # LDA #src_lo / STA $00
        0xA9, src_hi, 0x85, 0x01,   # LDA #src_hi / STA $01
        0xA9, dst_lo, 0x85, 0x02,   # LDA #dst_lo / STA $02
        0xA9, dst_hi, 0x85, 0x03,   # LDA #dst_hi / STA $03
        0xA2, n_pages,               # LDX #n_pages
        # loop: offset 18
        0xA0, 0x00,                  # LDY #0        ; offset 18
        # inner: offset 20
        0xB1, 0x00,                  # LDA ($00),Y   ; offset 20
        0x91, 0x02,                  # STA ($02),Y   ; offset 22
        0xC8,                        # INY           ; offset 24
        0xD0, 0xF9,                  # BNE inner     ; offset 25 (→20: 20-27=-7=0xF9)
        0xE6, 0x01,                  # INC $01       ; offset 27
        0xE6, 0x03,                  # INC $03       ; offset 29
        0xCA,                        # DEX           ; offset 31
        0xD0, 0xF0,                  # BNE loop      ; offset 32 (→18: 18-34=-16=0xF0)
        0x4C, init & 0xFF, (init >> 8) & 0xFF,  # JMP original_init ; offset 34
    ])
    # 37バイト → 64バイトにゼロパッド
    trampoline = trampoline_code + bytes(64 - len(trampoline_code))

    # 新ヘッダー（LOAD=0x8000、INIT=トランポリンアドレスに変更、PLAYは変更なし）
    header = bytearray(nsf_raw[:0x80])
    header[8]  = 0x00;                           header[9]  = 0x80
    header[10] = TRAMPOLINE_ADDR & 0xFF;         header[11] = (TRAMPOLINE_ADDR >> 8) & 0xFF

    # 新データ: ROM部分 → ゼロパッド → トランポリン → RAM部分データ
    pad = bytes(trampoline_offset - len(rom_part))
    new_data = rom_part + pad + trampoline + ram_part

    _log(f"NSF low-load fix: LOAD=0x{load:04X} INIT=0x{init:04X} "
         f"ram={ram_size}B rom={len(rom_part)}B trampoline=0x{TRAMPOLINE_ADDR:04X}")
    return bytes(header) + new_data
```

---

## 呼び出し箇所

`_nsf_pad_banks` の直後に呼ぶ（既存の `_nsf_pad_banks` 呼び出しと同じ場所）。

```python
# 既存
_nsf_raw = _nsf_pad_banks(_nsf_raw)
# 追加（直後）
_nsf_raw = _nsf_fix_low_load(_nsf_raw)
```

---

## 検証方法

Deep Dungeon ロード後のログで以下を確認する：

```
NSF low-load fix: LOAD=0x6230 INIT=0x627B ram=7632B rom=1010B trampoline=0x8400
NSF ch0: used=True
...
NSF render: mask=0b...... (0以外)
```

音楽が再生されることを確認する。
他のNSFファイルで `load >= 0x8000` の場合は変換をスキップするため影響なし。

---

## 補足：この問題が起きるケース

LOADアドレスが 0x8000 未満の NSF は、FDS ゲームの NSF に稀に存在する。
NSFリッパーが FDS の「ディスクから 0x6000-0x7FFF へロード」という
ハードウェア動作をそのまま NSF の LOAD アドレスとして記録した結果。
通常の NSF（カートリッジゲーム）では発生しない。
