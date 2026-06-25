# libgme.dll ビルド＋FDS対応確認 指示書

## 目的

現在使用中の libgme.dll は FDS バンク切り替えレジスタ ($5FF6/$5FF7) が未実装で、
Exciting Soccer (FDS)(1988)(Konami).nsf などが無音になる問題がある。

公式の最新版 libgme 0.6.6（kode54 氏による NSF チップ改善を含む）に差し替えることで
この問題が解消される可能性が高い。

---

## ビルド環境

- MinGW-w64（64bit）
- CMake 3.3 以上
- ターゲット: Windows 64bit DLL（libgme.dll）

---

## 手順

### Step 1: ソースを取得

```bash
git clone https://github.com/libgme/game-music-emu.git
cd game-music-emu
git checkout tags/0.6.6   # 最新リリースタグ。なければ main でも可
```

### Step 2: ビルド

```bash
mkdir build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DCMAKE_SYSTEM_NAME=Windows \
  -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc \
  -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++
make -j4
```

生成される `libgme.dll`（または `gme.dll`）を確認する。

### Step 3: FDS対応の確認（ビルド前に必ず行う）

ビルド前に、ソースに `$5FF6`/`$5FF7` の実装が含まれているか確認する。

```bash
grep -r "5FF6\|5FF7\|0x5FF6\|0x5FF7" gme/
```

**結果A: 見つかった** → そのままビルドして差し替えればOK。

**結果B: 見つからなかった** → 以下の「FDS対応パッチ」を適用してからビルドする。

---

## FDS対応パッチ（Step 3 で見つからなかった場合のみ）

`gme/Nsf_Emu.cpp` を開き、NSF バンク切り替えの書き込みハンドラを探す。
`$5FF8`〜`$5FFF` を処理している箇所があるはず（下記のような形）。

```cpp
// 既存コード（イメージ。実際のコードに合わせて読むこと）
case 0x5FF8: case 0x5FF9: ... case 0x5FFF:
    set_bank( addr - 0x5FF8, data );
    break;
```

その直前（または同じ switch/if ブロック内）に以下を追加する：

```cpp
// FDS: $5FF6/$5FF7 = $6000-6FFF / $7000-7FFF のバンク切り替え（RAM領域へのmemcopy）
// header[0x76]/[0x77] で初期設定された後、INIT中に動的に書き換えられる
case 0x5FF6:
    if ( fds_enabled ) {
        int bank = data & 0x0F;   // 有効バンク番号（ファイルに存在するbankに丸める）
        bank = bank % bank_count; // bank_countはNSFデータの総ページ数
        memcpy( ram + 0x6000, rom + bank * bank_size, bank_size ); // 0x6000-6FFF にコピー
    }
    break;
case 0x5FF7:
    if ( fds_enabled ) {
        int bank = data & 0x0F;
        bank = bank % bank_count;
        memcpy( ram + 0x7000, rom + bank * bank_size, bank_size ); // 0x7000-7FFF にコピー
    }
    break;
```

**注意**: 上記は概念コードです。実際の変数名（`ram`, `rom`, `bank_count`, `bank_size`,
`fds_enabled` 等）は Nsf_Emu.cpp の実際のコードを読んで合わせること。
FDS有効判定は `header_.chip_flags & 0x04` 相当の条件で行う。

---

## Step 4: 動作確認

1. ビルドした `libgme.dll` を morokoshi の実行フォルダに配置（上書き）
2. `Exciting Soccer - Konami Cup (FDS)(1988)(Konami).nsf` を読み込む
3. ログで以下を確認：
   ```
   NSF ch0: used=True
   NSF ch1: used=True
   ...
   NSF render: mask=0b...... (0以外)
   ```
4. 音楽が再生されることを確認

---

## Step 5: 配布用の対応（改造した場合のみ）

libgme を改造してビルドした場合、LGPL の義務を果たすために：

1. `license.txt`（libgme に同梱の LGPL ライセンス文）を morokoshi の配布パッケージに含める
2. README または about ダイアログに以下を記載：
   ```
   本ソフトウェアは libgme (Game_Music_Emu) を使用しています。
   libgme は GNU Lesser General Public License (LGPL) の下で配布されています。
   https://github.com/libgme/game-music-emu
   ```
3. 改変したソースコードを GitHub 等に公開する（または要求時に提供できる状態にする）

改造していない（0.6.6 をそのまま使う）場合は、1と2のみで十分。

---

## 補足：改造しなかった場合でも Soccer が動かない場合

0.6.6 でも動かなければ、FDS $5FF6/$5FF7 はやはり未実装。
その場合は上記パッチを適用してビルドし直す。

Soccer の INIT コードは以下のことをしている：
- $F000 に INIT スタブがある（バンク16 = NSF末尾の不完全バンクに存在）
- このスタブが $5FF6/$5FF7 に書き込み、$6000-7FFF に楽曲 INIT コードのあるバンクをマップ
- $5FF6/$5FF7 が動作しないと $6000-7FFF が未設定のままで楽曲 INIT に到達できない

パッチの memcpy 方式（書き込みで RAM にコピー）は、NEZPlug 等でも採用されている
実績ある実装パターンであり、FDS バンク切り替えの正しい処理方法。
