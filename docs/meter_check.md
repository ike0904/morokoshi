# 変拍子・テンポの判定 確認リスト（v0.1.43、2026-11-04 更新）

## まず確認してほしいこと（v0.1.43）

1. **Relics - Ankoku Yousai 3 曲目**: 6/8 になったが、小節頭が 8 分 1 個早い（P1 の C#5 を小節頭にしている）。
   P1 と P2 が 8 分ずれの輪唱で、長い音・ベース・ループ開始のどれも「P2 の C#5 が小節頭」にならない。今の形で許容できるか
2. **Contra JP 2 曲目**: 全体 3/4 → 全体 6/8 に変わった（小節の長さは同じ。長い音がすべて 8 分 3 個の区切りに来る）。3/4 の方が良いか
3. **Minna no Taabou 2 曲目**: まだ 40〜64 拍目が 6/8（正解は 4/4）。変更なし
4. **480 曲の比較で変わった 31 曲**（下の表、MIDI は `morokoshi\tmp\meter_check\v043\`）。特に
   M.C. Kids 2 曲目・Downtown Nekketsu 2 曲目はテンポが変わって変拍子が出た（悪化の可能性）
5. **Kkachi-Wa Norae Chingu 1 曲目**のループが短すぎる件（ユーザー指摘）は未対応（ループ検出の問題）
6. **Tom & Jerry & Tuffy・Balda**（ループのない曲）は v0.1.41 のテンポに戻した（90 / 90.15 BPM の方がデータに合うが、ループのない曲は判定を変えない方針にした）

MIDI: 確認リストの曲は `morokoshi\tmp\meter_check\`、回帰テストの曲は `regress\`、480 曲で変わった曲は `v043\`（変換ログ `*.log` も同じフォルダ）。

## ユーザー提示の曲

| 曲 | 判定 | メモ |
|:---|:---|:---|
| Ys 8 曲目 | 4/4 ×10、6/8 ×8、4/4 ×1、9/8 ×8、3/4 ×8（最後の 1 小節は無音）、→ 冒頭に戻る | ユーザーの構成（6/8 ×9、最後に 2/4 ×2 の無音）とは 2 か所違う。データでは 6/8 の 9 小節目に当たる所は無音と上行の 4 音（D E F G）で 4/4 の 1 小節分、最後の無音は 8 分音符 6 個分（3/4 の 1 小節） |

## 割り切れるループで変拍子と判定された曲（ユーザー確認済み 2026-11-04）

| # | 曲 | v0.1.41 の判定 | ユーザー確認 | v0.1.43 |
|:--|:---|:---|:---|:---|
| 1 | Contra JP 2 曲目 | 全体 3/4 | 正しい | **全体 6/8**（小節の長さは同じ。要確認） |
| 2 | NFL 1 曲目 | 全体 3/4（2 拍目から） | OK。どちらかというと 6/8（ノイズの位置） | 120 BPM 3 連系 4/4（= 12/8） |
| 3 | Rampart 3 曲目 | 全体 6/8 | OK | 変化なし |
| 4 | Laser Invasion 1 曲目 | 全体 9/8 | 6/8 | 162 BPM 3 連系 4/4（= 12/8、6/8 の 2 小節分） |
| 5 | Ikinari Musician 2 曲目 | 全体 5/8 | 4/4 | **90 BPM 4/4** |
| 6 | Super Team Games 1 曲目 | 全体 5/8 | 4/4（3 連符ノリ） | **150 BPM 4/4** |
| 7 | Minna no Taabou 1 曲目 | 19 拍目から 5/8 | 4/4（3 連符ノリ）、1 拍 + 1/3 のアウフタクト | **180 BPM 3 連系 4/4、2/4 の前打ち小節（2/3 拍の休符 + 1 拍 1/3）** |
| 8 | Minna no Taabou 2 曲目 | 4/4、40 拍目から 6/8、64 拍目から 4/4 | 4/4 | 変化なし（未解決） |
| 9 | Starship Hector 3 曲目 | 4/4、63 拍目から 6/8、87 拍目から 4/4 | 正しい | 変化なし |
| 10 | Hot Slots 2 曲目 | 4/4、14 拍目から 3/4 | 4/4（3 連符ノリ） | **150 BPM 3 連系 4/4** |
| 11 | Indora no Hikari 1 曲目 | 4/4、80 拍目から 3/4 … | ずっと 6/8（8 分 3 個の繰り返し） | **全体 6/8** |
| 12 | Elnark no Zaihou 3 曲目 | 9/8、6/8、9/8 | ずっと 4/4（17 拍目からベースが紛らわしい） | **150 BPM 4/4** |
| 13 | Ma Bu Mi Zhen & Qu Wei Cheng 3 曲目 | 9/8、45 拍目から 3/4 | ずっと 6/8、頭に 8 分 1 個のアウフタクト | **3/8 の前打ち小節（8 分休符 2 個 + アウフタクト）→ 6/8** |
| 14 | Relics - Ankoku Yousai 3 曲目 | 3/8、3/4、9/8 | ずっと 6/8、頭に 8 分 1 個のアウフタクト | 6/8（小節頭が 8 分 1 個早い。要確認） |
| 15 | Ganbare Pennant Race! 1 曲目 | 9/8、4/4、7/8、6/8 | ずっと 4/4（3 連符ノリ） | **150 BPM 3 連系 4/4** |
| 16 | Super Spike V'Ball 2 曲目 | 6/8、9/8 | ずっと 4/4（3 連符ノリ）、1 拍 + 1/3 のアウフタクト | **181.7 BPM 3 連系 4/4、2/4 の前打ち小節** |

ユーザーの補足: 3 連符ノリの曲を 4/4 と 6/8（12/8）のどちらにするかはどちらでも良い。ただし急に 6/8 が 4/4 になる曲もあるので注意。
アウフタクトは最初は人間にも分からないことが多く、後ろを聴いて拍の頭を認識してから「あれはアウフタクトだった」と分かる。
アウフタクトが 1 拍で割り切れないときは、頭に休符を入れて割り切れるようにする。

## v0.1.42 で回帰テストのテンポが変わった曲（ユーザー確認 2026-11-04）

| 曲 | v0.1.41 | v0.1.43 | ユーザー確認 |
|:---|:---|:---|:---|
| Adventures of Lolo 2 2 曲目 | 112.5 BPM | 150 BPM 3 連系 | 3 連ノリで正しい |
| Kkachi-Wa Norae Chingu 1 曲目 | 150 BPM | 112.7 BPM | テンポは正しい。ループはもっと長い（未対応） |
| Tom & Jerry & Tuffy 1 曲目 | 134.9 BPM | 134.9 BPM（v0.1.42 は 90） | 15 秒で終わる短い曲。曲番号が合っているか（回帰テストは zip 内の最初の NSF の開始曲） |
| Ai Sensei no Oshiete 1 曲目 | 97.6 BPM | 130.1 BPM、1/4 の前打ち小節 | 3 連ノリで正しい、1 拍のアウフタクト |
| Balda (BBG) 1 曲目 | 112.7 BPM | 112.7 BPM（作業中に一時 90） | 未確認（三角波が 20 フレームごとなので 90 BPM の方が合いそう） |

## v0.1.43 で 480 曲の比較で変わった曲（確認待ち、確認リストの曲を除く）

ランダム 160 タイトル（seed 7）× 1〜3 曲目。MIDI は `morokoshi\tmp\meter_check\v043\`。

| 曲 | 曲番号 | ループ | v0.1.41 | v0.1.43 |
|:---|:---|:---|:---|:---|
| Indora no Hikari | 2 | あり | 100 BPM 4/4 | 150.01 BPM 6/8 |
| Nichibutsu Mahjong III - Mahjong G Men | 1 | あり | 149.9 BPM 6/8 | 199.87 BPM 4/4 |
| Bee 52 | 3 | なし | 128.14 BPM 4/4 | 128.14 BPM 6/8 |
| Educational Computer 2000 | 1 | なし | 150.01 BPM 4/4 / 138.47 BPM 4/4 / 150.01 BPM 6/8 … | 150.01 BPM 4/4 / 138.47 BPM 6/8 / 150.01 BPM 6/8 … |
| Muppet Adventure - Chaos at the Carnival | 1 | あり | 112.5 BPM 4/4、変拍子 4/4 at beat 0, 9/8 at beat 4, 6/8 at beat 8.5, 4/4 at beat 41.5, 6/8 at beat 53.5, 4/4 at beat 83.5, 6/8 at beat 95.5, 9/8 at beat 119.5, 2/4 at beat 124 | 150.01 BPM 4/4 |
| Pooyan | 3 | あり | 112.47 BPM 4/4 | 168.7 BPM 4/4 |
| Navy Blue | 1 | あり | 96.42 BPM 4/4 | 128.56 BPM 4/4 |
| Ninja Crusaders | 3 | あり | 200.01 BPM 4/4 | 150.01 BPM 4/4 |
| China Rabbit Baby | 3 | あり | 100 BPM 4/4、変拍子 4/4 at beat 0, 9/8 at beat 124, 4/4 at beat 146.5, 2/4 at beat 154.5, 4/4 at beat 156.5 | 133.39 BPM 4/4 |
| Rockman 2 Exile | 1 | あり | 120 BPM 4/4 | 90 BPM 4/4 |
| Pasofami Demo | 1 | あり | 75 BPM 4/4 | 112.5 BPM 4/4 |
| MDSYM | 3 | あり | 167.78 BPM 4/4 | 125.87 BPM 4/4 |
| Ganbare Pennant Race! | 2 | あり | 112.5 BPM 6/8 | 150.01 BPM 4/4 |
| Daiva Story VI - Imperial of Nirsartia | 2 | あり | 75 BPM 4/4 | 112.5 BPM 4/4 |
| Elnark no Zaihou | 2 | あり | 75 BPM 4/4、変拍子 6/8 at beat 0, 4/4 at beat 9, 6/8 at beat 13, 4/4 at beat 22 | 75 BPM 6/8 |
| Shin Satomi Hakkenden - Hikari to Yami no Tatakai | 2 | あり | 150.01 BPM 4/4、変拍子 4/4 at beat 0, 6/8 at beat 60, 9/8 at beat 66, 4/4 at beat 75 | 200.01 BPM 4/4 |
| Just Breed | 1 | あり | 28.17 BPM 4/4、変拍子 4/4 at beat 3, 2/4 at beat 11, 4/4 at beat 13 | 112.73 BPM 4/4 |
| Batman | 3 | あり | 112.5 BPM 4/4、変拍子 4/4 at beat 0, 9/8 at beat 12, 4/4 at beat 21 | 150.01 BPM 4/4 |
| Star Soldier | 2 | なし | 150.01 BPM 4/4 | 150.01 BPM 6/8 |
| Happy Pairs | 3 | あり | 74.95 BPM 4/4 | 112.42 BPM 4/4 |
| Ne Zha Chuan Qi | 2 | なし | 112.5 BPM 4/4 / 87.88 BPM 4/4 / 112.5 BPM 4/4 … | 112.5 BPM 4/4 / 87.88 BPM 4/4 / 112.5 BPM 6/8 … |
| Bikkuriman World - Gekitou Sei Senshi | 2 | あり | 150.01 BPM 4/4 | 150.01 BPM 6/8 |
| Legends of the Diamond - The Baseball Championship Game | 2 | あり | 100 BPM 4/4、変拍子 6/8 at beat 0, 4/4 at beat 9, 6/8 at beat 13, 3/4 at beat 22, 6/8 at beat 25, 4/4 at beat 34 | 133.34 BPM 4/4 |
| SD Gundam Gaiden - Knight Gundam Monogatari | 3 | あり | 150.01 BPM 4/4 | 112.5 BPM 4/4 |
| Radical Bomber!! Jirai-kun | 2 | あり | 138.47 BPM 4/4 | 150.01 BPM 4/4 |
| Shockwave | 3 | あり | 171.44 BPM 4/4 | 128.58 BPM 4/4 |
| Seiken Psycho Calibur - Maju no Mori Densetsu | 2 | あり | 128.58 BPM 4/4、変拍子 4/4 at beat 24, 3/4 at beat 36, 4/4 at beat 42, 2/4 at beat 46, 4/4 at beat 48, 3/4 at beat 76, 4/4 at beat 79 | 128.58 BPM 6/8 |
| Adventures of Dino-Riki | 2 | あり | 200.01 BPM 4/4 | 150.01 BPM 4/4 |
| Business Wars | 3 | あり | 25 BPM 4/4、変拍子 3/4 at beat 0 | 100 BPM 4/4 |
| M.C. Kids | 2 | あり | 150.11 BPM 4/4 | 85.78 BPM 4/4、変拍子 4/4 at beat 0, 3/4 at beat 12, 2/4 at beat 15, 4/4 at beat 17 |
| Downtown Nekketsu Koushinkyoku - Soreyuke Daiundoukai | 2 | あり | 117.78 BPM 4/4 | 157.04 BPM 4/4、変拍子 4/4 at beat 14, 2/4 at beat 30, 5/8 at beat 32, 4/4 at beat 34.5, 3/4 at beat 42.5, 2/4 at beat 45.5, 4/4 at beat 47.5, 5/8 at beat 51.5, 4/4 at beat 54, 7/8 at beat 58, 4/4 at beat 61.5, 3/4 at beat 77.5, 4/4 at beat 80.5, 2/4 at beat 104.5, 4/4 at beat 106.5, 7/8 at beat 114.5, 4/4 at beat 118, 5/8 at beat 130 |
