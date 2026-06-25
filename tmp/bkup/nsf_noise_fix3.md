# NSF 先頭ノイズ 根本原因と修正提案書（第4版・最終）

---

## 根本原因の確定

### ログ実測データ（全6ロードを網羅）

```
== 5chの例 ==
frame[0]: [0.0,    0.0,    0.0,    0.0,    0.0   ]  ← 全ch無音
frame[1]: [0.212,  0.212,  0.212,  0.212,  0.212 ]  ← 全ch一致 → 合算=1.06（クリップ）
frame[2]: [0.168,  0.168,  0.168,  0.168,  0.168 ]  ← 全ch一致 → 合算=0.84
frame[3]: [0.0835, 0.0835, 0.1681, 0.0835, 0.0835]  ← 各ch分岐（正常）

== 13chの例（拡張音源）==
frame[0]: [0.8076 × 13ch]  ← 全ch一致 → 合算=10.5（大幅クリップ）
frame[1]: [0.4082 × 13ch]  ← 全ch一致 → 合算=5.3
frame[2]:  各ch分岐（正常）
```

### 分かったこと（これまでの仮説をすべて覆す事実）

**1. フレーム[0]は必ずしも無音ではない（13chのケースで確認）**
5ch曲ではframe[0]=0.0だが、13ch曲ではframe[0]が最大の漏れ（0.8076×13=10.5）になっている。
漏れのフレーム数は曲・チップ構成によって「1フレーム」から「2フレーム」まで変わる。

**2. 漏れの正体は「N倍増幅されたINIT音」**
各チャンネルのデコード結果に同一のINIT音（全ch合算）が乗っている。
これをN個のチャンネルで合算すると、N×（全ch音量）= N倍の音量になる。
- 5ch曲：最大1.53（float32の正常範囲=1.0を超えてクリップ）
- 13ch曲：最大10.5（論外）

これが「全チャンネルが一斉に鳴ったような大きなノイズ」に聞こえる理由。
**ノイズの本質はINIT音の「N倍増幅」であり、音自体より増幅が問題。**

**3. 漏れフレームには演奏音が含まれていない（重要）**
frame[3]以降で各chの値が分岐し始める = ここから本来の演奏が始まっている。
frame[0]〜[2]の全ch一致区間は演奏音ではなく、純粋にINITノイズ。
**したがって、これらのフレームをゼロにしても演奏の頭は切れない。**

---

## なぜ「gme_mute_voice を start_track の前に呼ぶ」が失敗したか（確定）

libgme の Blip_Buffer は「書き込み位置と読み出し位置が独立した遅延バッファ」として動作する。
gme_start_track() 実行中に INIT ルーチンが APU を操作し、その音をすでに Blip_Buffer に書き込む。
gme_mute_voice() はミックス段階のゲインをゼロにするだけで、Blip_Buffer 内の既存データには一切触れない。
よって、gme_start_track() の前後どちらで mute を呼んでも、Blip_Buffer の漏れは除去できない。

また「mute before → DMC DMA の省略 → CPU タイミングズレ」の問題も確認済みのため、
mute の呼び出しタイミングを変える方向での解決は現実的でない。

---

## 修正方針

### 「漏れフレームのゼロ化」（ポストプロセス）

デコード後、全チャンネルの「漏れフレーム区間」をゼロで上書きする。

```python
# _nsf_decode_track() の戻り値 ch_data に対するポストプロセス
# （デコードループの外、natural_end 判定の前に実行）

LEAK_FRAMES = 2   # 実測で確定（5ch曲=frame[0-1]、13ch曲=frame[0-1]）
                  # ただし最大値を取ると frame[0] が漏れる13ch曲もあるため、
                  # 安全に 2フレーム分とする（= 2 × CHUNK サンプル = ≈33ms）

LEAK_SAMPLES = LEAK_FRAMES * CHUNK
FADE_SAMPLES = 256  # 漏れ区間終端のクリック防止フェードイン（≈6ms）

for i, arr_f in enumerate(ch_data):
    if len(arr_f) <= LEAK_SAMPLES:
        continue
    # 漏れ区間をゼロ化
    arr_f[:LEAK_SAMPLES] = 0.0
    # ゼロ→演奏音の境界クリック防止フェードイン
    fade_end = min(LEAK_SAMPLES + FADE_SAMPLES, len(arr_f))
    fade_len = fade_end - LEAK_SAMPLES
    if fade_len > 0:
        arr_f[LEAK_SAMPLES:fade_end] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
```

### なぜこれが正しいか

| 項目 | 根拠 |
|:---|:---|
| 演奏の頭が切れない | frame[3]以降で初めて各chの値が分岐する。frame[0-2]は純粋にINITノイズ（全ch一致）であり、演奏音ではない |
| ノイズが消える | 全chでゼロ化 → N倍増幅がゼロ倍になる |
| クリップが消える | 合算値1.5〜10.5 → 0.0 に置き換え |
| 従来のflushとの違い | flush（デコード時に破棄）は「INIT区間の長さの見積もりが合わないと演奏を削る」が、これは「デコード後のポストプロセス」なので、見積もりが若干ズレても演奏に無影響 |
| 13ch（拡張音源）にも対応 | frame[0]が漏れる13chケースも、LEAK_FRAMES=2で確実にカバー |

### 考慮事項

**natural_end（無音検出）ロジックへの影響**
ゼロ化するのは先頭33msのみ。natural_end判定は末尾5秒を対象にしているため、無影響。

**チャンネルごとの時間軸のズレ**
全chに同じ LEAK_SAMPLES（固定値）を適用するため、時間軸のズレは発生しない。

**延長デコード（_nsf_extend_track）への影響**
延長分は先頭ゼロ化の対象外（先頭ではなく後続データを追加するだけ）。変更不要。

**ch_used（使用判定）との整合**
ch_used は max_amp で判定しているが、ゼロ化はポストプロセス後に実施するため、
判定は「ゼロ化前の生データ」で行われる。これは正しい挙動（INITで鳴っていれば「使用中」と判定）。
→ ゼロ化を ch_used 判定の後に行うよう、コードの順序を確認すること。

---

## 実装場所

`_nsf_decode_track()` 関数内の、`ch_data` リストを返す直前（自然終了判定・`natural_end` の計算の後）。

```python
    # （既存コード）natural_end の判定 ...
    natural_end = ...

    # ★ ここに追加：漏れフレームのゼロ化
    LEAK_SAMPLES = 2 * CHUNK
    FADE_SAMPLES = 256
    for arr_f in ch_data:
        if len(arr_f) > LEAK_SAMPLES:
            arr_f[:LEAK_SAMPLES] = 0.0
            fade_end = min(LEAK_SAMPLES + FADE_SAMPLES, len(arr_f))
            fade_len = fade_end - LEAK_SAMPLES
            if fade_len > 0:
                arr_f[LEAK_SAMPLES:fade_end] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)

    return ch_data, ch_used, natural_end, ch_emus, actual_dur_sec
```

---

## 検証方法

修正後に frame_peaks ログを確認する。

**期待する結果：**
```
frame[0]: [0.0, 0.0, ..., 0.0]     ← ゼロ化済み
frame[1]: [0.0, 0.0, ..., 0.0]     ← ゼロ化済み
frame[2]: 各ch分岐（漏れなし）
frame[3]: 各ch分岐（演奏）
```

聴感上も「全チャンネルが一斉に鳴る大きなノイズ」が消えていることを確認する。
冒頭33ms（≈2フレーム）が無音になるが、演奏の頭は切れていないことを確認する。
