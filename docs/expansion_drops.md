# 拡張音源のタム（下降音ドラム）候補

2026-11-02 作成（nsf2mid v0.1.26）。**出力はしていない**。ユーザーが聴いて、タムとして分けるべきかを判定するための一覧。

- 対象: 拡張音源の NSF（各ゲーム 16 曲まで、各 40 秒）1729 曲
- 曲番号は morokoshi・nsf2mid の表示と同じ（1 始まり）。ch は MIDI ch = morokoshi のチャンネルボタン番号
- 曲名は zip 内の m3u から（ない場合は空欄）

## 1. 音程が下がり続ける短い音（2A03 と同じ判定: 12 フレーム以下・3 半音以上）

| ゲーム | 曲 | 曲名 | ch | 該当 / 音符数 | 例（時刻・下がり方） |
|:--|--:|:--|:--|--:|:--|
| Almana no Kiseki | 7 | Boss Theme I | Ch6 FDS | 6 / 22 | 0.1s(64->57) 0.2s(56->51) 0.4s(63->58) 0.5s(56->52) |
| Exciting Soccer - Konami Cup | 2 |  | Ch6 FDS | 1 / 153 | 30.4s(48->39) |
| Ginga Denshou - Galaxy Odyssey | 12 |  | Ch6 FDS | 1 / 1 | 0.0s(80->48) |

→ 2A03 のタム（バルーンファイト・レッキングクルーなど）のように、まとまって出る曲は見つからなかった。

## 2. FDS: モジュレーションがかかった短い音（12 フレーム以下）

FDS はモジュレーション（周波数を揺らすユニット）で音程を下げてタムを作れる。今のモデルは中心の周波数だけを見るので、
1. の判定には出てこない。モジュレーション付きの短い音が 4 つ以上ある曲を、短い音の割合が高い順に並べた。
ビブラートやベル系の音色でも該当するので、タムとは限らない。

| ゲーム | 曲 | 曲名 | 該当 / FDS の音符数 | 最初の例（時刻） |
|:--|--:|:--|--:|:--|
| Almana no Kiseki | 7 | Boss Theme I | 22 / 22 | 0.0s 0.1s 0.2s 0.3s |
| Bio Miracle Bokutte Upa | 5 |  | 395 / 395 | 0.5s 0.6s 0.7s 0.8s |
| Deep Dungeon II - Yuushi no Monshou | 2 |  | 175 / 175 | 0.0s 0.2s 0.4s 0.6s |
| Deep Dungeon II - Yuushi no Monshou | 8 |  | 291 / 291 | 0.2s 0.4s 0.6s 0.8s |
| Deep Dungeon II - Yuushi no Monshou | 9 |  | 150 / 150 | 0.0s 0.3s 0.5s 0.8s |
| Deep Dungeon II - Yuushi no Monshou | 10 |  | 140 / 140 | 0.0s 0.4s 0.8s 1.2s |
| Deep Dungeon II - Yuushi no Monshou | 11 |  | 368 / 368 | 3.2s 3.3s 3.4s 3.5s |
| Deep Dungeon II - Yuushi no Monshou | 12 |  | 12 / 12 | 0.0s 0.1s 0.2s 0.3s |
| Deep Dungeon II - Yuushi no Monshou | 14 |  | 20 / 20 | 0.0s 0.1s 0.2s 0.3s |
| Transformers - The Head Masters | 5 |  | 272 / 272 | 0.0s 0.2s 0.4s 0.6s |
| Vs. Excitebike | 14 |  | 394 / 394 | 0.0s 0.1s 0.2s 0.3s |
| Knight Move | 4 |  | 179 / 180 | 0.0s 0.1s 0.3s 0.4s |
| Vs. Excitebike | 13 |  | 292 / 294 | 0.0s 0.1s 0.3s 0.4s |
| Monty no Doki Doki Daisassou - Monty on the Run | 2 |  | 366 / 371 | 0.0s 0.1s 0.2s 0.3s |
| Kick and Run | 7 |  | 273 / 282 | 0.0s 0.1s 0.3s 0.4s |
| Vs. Excitebike | 10 |  | 282 / 292 | 0.6s 0.7s 0.9s 1.0s |
| Santa Claus no Takarabako | 8 |  | 240 / 249 | 1.6s 1.8s 1.9s 2.0s |
| Monty no Doki Doki Daisassou - Monty on the Run | 3 |  | 280 / 292 | 0.0s 0.1s 0.2s 0.3s |
| Vs. Excitebike | 15 |  | 243 / 257 | 0.0s 0.1s 0.3s 0.4s |
| Vs. Excitebike  - alt | 5 |  | 49 / 52 | 0.0s 0.2s 0.4s 0.6s |
| Vs. Excitebike | 6 |  | 49 / 52 | 0.0s 0.2s 0.4s 0.6s |
| Monty no Doki Doki Daisassou - Monty on the Run | 1 |  | 236 / 251 | 2.4s 2.5s 2.5s 2.5s |
| Deep Dungeon II - Yuushi no Monshou | 13 |  | 15 / 16 | 0.0s 0.2s 0.4s 0.5s |
| Santa Claus no Takarabako | 13 |  | 16 / 18 | 0.8s 1.0s 1.1s 1.2s |
| Bio Miracle Bokutte Upa | 6 |  | 202 / 228 | 3.7s 3.9s 4.0s 4.1s |
| Knight Move | 3 |  | 107 / 121 | 3.2s 3.3s 3.4s 3.5s |
| Kid Icarus | 4 |  | 7 / 8 | 1.6s 1.7s 1.9s 2.0s |
| Transformers - The Head Masters | 4 |  | 114 / 132 | 0.0s 0.2s 0.4s 0.6s |
| Kick and Run | 1 |  | 105 / 122 | 5.6s 5.7s 5.8s 5.9s |
| Vs. Excitebike  - alt | 4 |  | 17 / 20 | 0.0s 0.2s 0.3s 0.8s |
| Vs. Excitebike | 5 |  | 17 / 20 | 0.0s 0.2s 0.3s 0.8s |
| Transformers - The Head Masters | 2 |  | 116 / 142 | 6.0s 6.1s 6.4s 6.5s |
| Deep Dungeon II - Yuushi no Monshou | 5 |  | 134 / 167 | 0.0s 0.2s 0.4s 1.0s |
| Deep Dungeon II - Yuushi no Monshou | 7 |  | 32 / 40 | 13.0s 13.2s 13.4s 13.6s |
| Knight Move | 5 |  | 40 / 50 | 14.8s 15.2s 15.4s 16.4s |
| Transformers - The Head Masters | 6 |  | 98 / 123 | 1.2s 1.3s 1.5s 2.8s |
| Deep Dungeon II - Yuushi no Monshou | 3 |  | 92 / 117 | 3.9s 6.0s 6.2s 7.0s |
| Santa Claus no Takarabako | 14 |  | 17 / 22 | 0.0s 0.2s 0.4s 0.6s |
| Nankin no Adventure | 7 |  | 89 / 117 | 0.0s 0.3s 0.4s 0.5s |
| Monty no Doki Doki Daisassou - Monty on the Run | 5 |  | 154 / 209 | 1.1s 2.7s 2.9s 3.3s |
| Bio Miracle Bokutte Upa | 2 |  | 101 / 139 | 0.4s 0.6s 0.7s 0.9s |
| Transformers - The Head Masters | 3 |  | 29 / 40 | 6.0s 6.2s 9.2s 9.3s |
| Monty no Doki Doki Daisassou - Monty on the Run | 4 |  | 110 / 152 | 0.0s 0.6s 1.4s 1.6s |
| Kick and Run | 3 |  | 98 / 136 | 0.6s 1.8s 2.0s 2.2s |
| Kick and Run | 5 |  | 70 / 100 | 0.0s 0.1s 0.2s 0.6s |
| Nankin no Adventure | 12 |  | 54 / 79 | 2.0s 2.1s 2.2s 2.3s |
| Suishou no Ryuu | 1 |  | 54 / 79 | 10.7s 10.8s 11.0s 11.2s |
| Kiki Kaikai - Dotou-hen | 1 |  | 97 / 143 | 3.2s 3.3s 3.4s 3.5s |
| Kick and Run | 2 |  | 126 / 188 | 0.3s 0.4s 1.0s 1.1s |
| Family Composer Demo | 1 |  | 82 / 127 | 0.2s 0.3s 0.6s 0.8s |
| Kid Icarus | 1 |  | 44 / 70 | 12.8s 12.9s 13.1s 13.2s |
| Pulsar no Hikari | 1 |  | 8 / 13 | 28.4s 28.6s 31.6s 31.8s |
| Transformers - The Head Masters | 1 |  | 63 / 109 | 0.2s 0.4s 0.6s 0.8s |
| Santa Claus no Takarabako | 11 |  | 5 / 9 | 0.3s 1.5s 1.8s 3.0s |
| Vs. Excitebike  - alt | 7 |  | 25 / 45 | 0.8s 0.9s 1.1s 1.2s |
| Vs. Excitebike | 9 |  | 25 / 45 | 0.8s 0.9s 1.1s 1.2s |
| Deep Dungeon II - Yuushi no Monshou | 4 |  | 74 / 135 | 5.1s 5.2s 5.7s 5.8s |
| Bio Miracle Bokutte Upa | 10 |  | 13 / 30 | 0.1s 0.2s 0.3s 2.2s |
| Nazo no Magazine Disk - Nazoler Land Dai 3 Gou | 10 |  | 62 / 147 | 10.6s 10.8s 11.0s 12.5s |
| Kick and Run | 4 |  | 36 / 89 | 5.2s 5.4s 8.8s 9.0s |
| Bio Miracle Bokutte Upa | 3 |  | 47 / 144 | 0.0s 0.1s 0.2s 0.9s |
| Nazo no Murasame Jou | 9 |  | 15 / 52 | 0.3s 0.5s 0.6s 0.8s |
| Deep Dungeon II - Yuushi no Monshou | 1 |  | 14 / 50 | 16.4s 16.6s 21.2s 21.4s |
| Nazo no Murasame Jou | 10 |  | 41 / 152 | 2.4s 3.8s 3.9s 5.1s |
| Bio Miracle Bokutte Upa | 1 |  | 34 / 173 | 4.7s 5.1s 7.1s 7.2s |
| Bio Miracle Bokutte Upa | 7 |  | 72 / 384 | 9.6s 9.7s 9.8s 9.9s |
| Famicom Golf - Japan Course | 1 |  | 7 / 100 | 1.4s 4.6s 7.8s 8.8s |
| Nazo no Murasame Jou | 2 |  | 12 / 192 | 20.9s 21.0s 23.1s 23.2s |
| Falsion | 6 | Falsion - Sakamoto\ | 15 / 302 | 4.8s 4.8s 4.9s 5.0s |
| Legend of Zelda 2, The - The Adventure of Link | 1 |  | 5 / 192 | 26.1s 28.3s 30.4s 32.5s |

## 判定の結果（ユーザー記入欄）

- （タムだった曲・チャンネルを書いてもらう）
