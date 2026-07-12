<div style="page-break-after: always; text-align: center; padding-top: 55mm;">
<p style="font-size: 26pt; font-weight: bold; color: #1a1a2e; margin: 0 0 6px;">もろこしタイム</p>
<p style="font-size: 14pt; color: #555; margin: 0 0 24px;">Morokoshi Time</p>
<p style="font-size: 13pt; color: #333; margin: 0 0 16px;">ユーザーマニュアル / User Manual</p>
<p style="font-size: 11pt; color: #888; margin: 0 0 50px;">v1.6.0</p>
<hr style="width: 50%; border: none; border-top: 1px solid #ccc; margin: 0 auto 24px;">
<p style="font-size: 9.5pt; color: #666; margin: 0 0 6px;">日本語マニュアルは次のページから始まります。</p>
<p style="font-size: 9.5pt; color: #666; margin: 0;">English manual starts on the second half of this document.</p>
</div>

# 耳コピ特化型メディアプレイヤー「もろこしタイム」 ユーザーマニュアル

(対象バージョン: v1.6.0)

---

## 改版履歴

| バージョン | 日付 | 内容 |
| :-------------------- | :-------------------- | :--------------------------------------------------------------- |
| **v1.0** | 2026/6/16 | 初回リリース |
| **v1.3** | 2026/6/18 | スペクトラムアナライザー・フィルター機能を追加。<br>画面表示を2倍に拡大できるZoom機能を追加。<br>A・Bマーカーの移動ボタンをEar Modeアイコンの左右に配置（テンキー操作との整合性向上）。<br>波形エリアで現在位置線・マーカー線を直接ドラッグして移動できるように改善。<br>その他、細かな表示・操作性の修正。 |
| **v1.4** | 2026/6/19 | **A&lt;-&gt;B** と **Rew/FF** の値を直接編集可能に（ドラッグ・ホイール・直接入力）。Rew/FFを変更するとTempoが自動逆算されます。<br>Tempoの範囲を30〜300に拡大。ABリピートON時にマーカー未設定でも自動補完する挙動をマニュアルに明記。<br>ライブラリ最適化によりexeファイルサイズを大幅削減（約136MB→約49MB）。 |
| **v1.5.0** | 2026/6/23 | **NSF（NESゲーム音楽）ファイル対応**。チャンネル個別ON/OFF、複数曲切り替え、総再生時間拡張など。<br>**ffmpegの自動ダウンロード機能**を追加（ffmpegが無くても自動で入手）。<br>NSFを含む全ファイルの状態保存を強化（NSF内の全曲分の再生位置・マーカー等を個別に記憶）。 |
| **v1.6.0** | 2026/6/28 | **SPC（SNES/スーパーファミコンのゲーム音楽）対応**。チャンネル個別ON/OFF、ZIPファイルをそのまま複数曲として開く機能など。<br>**GBS（Game Boyのゲーム音楽）対応**。チャンネル個別ON/OFF、複数曲切り替えなど。<br>**NSF/SPC/GBSをZIPファイルのまま直接開ける**ようになりました（解凍不要）。<br>**フォルダのドラッグ＆ドロップ**でフォルダ内のゲーム音楽ファイルを一括認識して開けます。<br>全数値ボックスのホイール操作対応（編集モードに入らなくてもホイールで値を変えられます）。<br>波形エリアの上下ドラッグでもズームができるようになりました。<br>A-B区間外の波形を左右ドラッグしてスクロールできます。<br>Speed（再生速度）を7段階固定に変更（×0.2、×0.25、×0.33、×0.5、×1.0、×1.5、×2.0）。<br>ゲーム音楽（NSF/SPC/GBS）の曲頭ノイズを修正（改良版libgme.dll適用）。 |

---

<div style="page-break-before: always;"></div>

## 1. 特徴

「もろこしタイム」は、耳コピ作業に特化したメディアプレイヤーです。次のような特徴があります。

* **読み込み時に内部でWAV変換**します。映像部分を取り除いて音声だけを扱い、動画ファイル特有の「キーフレーム単位でしか移動できない」制限を排除するため、どんな位置でもなめらかにシーク（頭出し）できます。
* **テンポ自動検出機能**を搭載。再生位置の前後およそ10秒を解析して、曲のテンポ（BPM）を自動で割り出します。
* 検出したテンポをもとに、**小節単位での早送り・早戻し**ができます。「2小節だけ戻る」といった操作が一発です。
* **ABリピートの間隔を保ったまま、区間ごと前後にスライド移動**できます。「この2小節をもう少し後ろにずらしたい」が直感的に行えます。
* **再生速度と音程（キー）を、それぞれ独立して変更**できます。さらに音程は半音単位の**Key**だけでなく、-1.00～+1.00単位で微調整できる**Fine（ファインチューン）**も用意しており、原曲と手持ちの楽器・環境とのわずかなピッチのズレも補正できます。
* **15バンドのスペクトラムアナライザー**で、再生中の音の周波数バランスをリアルタイムに確認できます（通常の音声・動画ファイルのみ）。
* **フィルター（ハイパス・ローパス）**を搭載。聴きたい楽器の帯域だけを浮き上がらせたり、邪魔な低音・高音を削ったりできます（通常の音声・動画ファイルのみ）。
* アプリを閉じても、**前回作業時の各種情報（再生位置・マーカー・速度・キー・Fine・フィルターなど）を曲ごとに記憶**します。次に同じファイルを開くと、続きからすぐ作業できます。
* **NSF（NES/ファミコン）・SPC（SNES/スーパーファミコン）・GBS（Game Boy）のゲーム音楽ファイルに対応**。チャンネル個別ON/OFF・複数曲の切り替えなど、耳コピに役立つ機能が揃っています（詳細は「6. ゲームモードの使い方」参照）。
* **ZIPファイルをそのまま開ける**ので、解凍の手間なくゲーム音楽を楽しめます。
* **省スペースでシンプル**、かつ直感的で使いやすいデザイン。映像ウィンドウに画面を圧迫されることもありません。

---

<div style="page-break-before: always;"></div>

## 2. 動作環境・インストール・起動方法

### 必須環境

* **OS**: Windows 10 / 11（64bit）
* **ffmpeg**: メディアファイルを内部的にWAVへ変換するために使用します。NSF/SPC/GBSファイルを使う場合は不要です。

### ffmpegについて

「もろこしタイム」は、通常の音声・動画ファイルを開く際に **ffmpeg** を内部的に使用します。

* **ffmpegが見つからない場合、初回ファイル読み込み時に自動でダウンロードします**（インターネット接続が必要です）。ダウンロードは一度だけ行われ、次回以降はそのまま使用できます。
* 手動で用意したい場合は、`ffmpeg.exe` を **`morokoshi.exe` と同じフォルダに置く**か、Windowsの「環境変数PATH」が通った場所に置いてください。
* ステータスバー（画面最下部）にマウスを乗せると（ファイルが開かれていない状態のとき）、現在使用されているffmpegのパスが表示されます。

### 対応ファイル形式

音声・動画の主要な形式に対応しています。

`.mp3` `.mp4` `.wav` `.flac` `.aac` `.ogg` `.m4a` `.wma` `.opus` `.webm` `.avi` `.mkv` `.mov` など

**ゲーム音楽ファイル**: 以下の形式にも対応しています。再生にffmpegは不要です。

| 形式 | 説明 |
| :--- | :--- |
| `.nsf` `.nsfe` | NES/ファミコンのゲーム音楽（NSF） |
| `.spc` | SNES/スーパーファミコンのゲーム音楽（SPC） |
| `.gbs` | Game Boyのゲーム音楽（GBS） |

> 💡 上記ゲーム音楽ファイルを含む **ZIPファイルをそのまま開ける**ほか、**フォルダをドラッグ＆ドロップ**してフォルダ内のファイルを一括認識することもできます。

### インストール・起動方法

インストール作業は不要です。

1. 配布された **`morokoshi.exe`** と、同梱の **DLLファイル**（`libgme.dll` など）を、同じフォルダに置きます。
2. **ダブルクリックで起動**します。

それだけで使えます。アンインストールしたい場合は、これらのファイルをまとめて削除するだけです。

> 💡 DLLファイルは **NSF・SPC・GBSファイルの再生**に必要なものです。通常の音声・動画ファイルのみを使う場合でも、同じフォルダに置いておいてください。

### 同梱ライブラリのライセンス

本アプリは以下のオープンソースライブラリを使用しています。

| ライブラリ | ファイル | ライセンス・ソース |
| :---------------------- | :------------------------------- | :----------------------------------------------------- |
| Game_Music_Emu (libgme) | `libgme.dll` | LGPL 2.1<br>https://github.com/ike0904/game-music-emu-morokoshi |
| GCC Runtime | `libgcc_s_seh-1.dll` | GPL + Runtime Library Exception |
| libstdc++ | `libstdc++-6.dll` | GPL + Runtime Library Exception |
| winpthreads | `libwinpthread-1.dll` | MIT / BSD |
| zlib | `zlib1.dll` | zlib License |

> `libgme.dll` は LGPL v2.1 に基づき独立したファイルとして同梱されており、ご自身でビルドした DLL と入れ替えて使用することができます。各ライセンスの全文は、同梱の `license.txt` をご参照ください。

### 設定やキャッシュの保存場所

作業情報（再生位置・マーカーなど）や、変換済みのWAVファイルは、お使いのユーザーフォルダ内の隠しフォルダに保存されます。

```
C:\Users\(あなたのユーザー名)\.morokoshi_cache\
```

* 一度開いたファイルは、ここにWAVとして保存されるため、**2回目以降は変換をスキップして高速に開けます**。
* このフォルダ内のファイルは、**30日間使われないと自動的に削除**されます。
* 容量が気になる場合は、このフォルダの中身を削除しても問題ありません（次回開くときに作り直されます）。

### キャッシュクリア（アプリからの操作）

アプリ内から、キャッシュフォルダをまとめて削除することができます。

* **Shiftを押しながら「すべてリセット」アイコンをクリック**すると、確認ダイアログが表示されます。
* **「Yes」を選択**すると、`.morokoshi_cache` フォルダ全体が削除され、アプリが自動的に再起動します。

> ⚠️ キャッシュクリアを行うと、変換済みのWAVファイルだけでなく、すべての曲の作業情報（再生位置・マーカーなど）も消去されます。ご注意ください。


---

<div style="page-break-before: always;"></div>

## 3. 画面の説明

起動すると、次のような画面が表示されます。

![メイン画面](icons/Main_Capture.png)

画面は大きく分けて、**左側の情報エリア**、**右側のアイコンボタン**、**中央のスペクトラムアナライザー（フィルター操作）**、**中央下の波形エリア**、**最下部の再生・音量エリア**で構成されています。

> 💡 NSF/SPC/GBSファイルを開くと、スペクトラムアナライザーのエリアが **ゲームパネル**（楽曲選択・チャンネルON/OFF）に切り替わります。詳しくは「6. ゲームモードの使い方」を参照してください。

### 左側の情報エリア（数値の表示・入力）

このエリアは**左列**と**中央列**の2つの縦並びに分かれており、それぞれ上から関連する項目が並んでいます。

| 項目 | 説明 |
| :---------------------- | :-------------------------------------------------------- |
| **A&lt;-&gt;B** | AマーカーとBマーカーの間隔（区間の長さ）。ドラッグ・ホイール・直接入力で変更可能。変更するとAは固定のままBマーカーが移動します。A・Bどちらかが未設定の場合は自動補完されます（後述）。 |
| **A** | Aマーカー（リピート開始位置）の時間。 |
| **B** | Bマーカー（リピート終了位置）の時間。 |
| **Key** | 音程（キー）。-24～+24半音（1半音刻み）。 |
| **Fine** | 音程の微調整（ファインチューン）。-1.00～+1.00（1.00で半音1つ分）。Keyとは独立した値で、原曲とのわずかなピッチのズレを補正したい時に使います。 |
| **Rew/FF** | 早戻し・早送りの幅（秒）。Tempo・Beat・Barから自動計算されます。ドラッグ・ホイール・直接入力で直接変更することもでき、その場合はTempoが逆算されて自動更新されます。 |
| **Tempo** | 曲のテンポ（BPM）。30～300。 |
| **Beat** | 拍子（1小節あたりの拍数）。1～16。 |
| **Bar** | 早送り・早戻しの小節数。0.1～100。 |
| **Speed** | 再生速度。×0.2 / ×0.25 / ×0.33 / ×0.5 / ×1.0 / ×1.5 / ×2.0 の7段階。 |

これらの数値ボックスは、共通して次の操作ができます（詳しくは「4. 基本的な使い方」で解説します）。

* **上下にドラッグ**して値を増減、Shiftキーを押しながらドラッグで大きく増減（一部を除く）
* **マウスホイール**でも値を増減できます（Shiftキーを押しながらで大きく増減、一部を除く）
* **ダブルクリック**して直接キーボード入力（編集中はマウスホイールでも増減できます）
* **右クリック**で初期値に戻す

### 右側のアイコンボタン

アイコンは4行に並んでいます。アイコンの並び位置は、テンキーでの操作（「8. ショートカット」参照）に対応できるようになっています。例えば、3段目の **A（移動）・Ear Mode・B（移動）** がテンキーの **4・5・6** に対応しています。

| 項目 | 説明 |
| :---------------------- | :-------------------------------------------------------- |
| <img src="icons/help.png" width="20"> **Help** | 取扱説明書（PDF版）を、お使いのパソコンの既定のアプリで開きます。`morokoshi.exe` と同じフォルダに `morokoshi_manual.pdf` がある場合に開けます。 |
| <img src="icons/zoom.png" width="20"> **Zoom** | 画面全体の表示倍率を2倍 ⇔ 1倍で切り替えます。文字やボタンが小さくて見づらいときに使います。 |
| <img src="icons/open.png" width="20"> **ファイルを開く** | メディアファイルを選択して読み込みます。 |
| <img src="icons/tempo_search.png" width="20"> **テンポ検出** | 現在の再生位置の前後約10秒からテンポ（BPM）を自動検出します。 |
| <img src="icons/reset.png" width="20"> **すべてリセット** | マーカー・速度・キー・Fine・テンポ・フィルターなどを初期状態に戻します。 |
| **A** ボタン | **Aマーカーへ移動**します。再生中はそのまま再生を続けながら、停止中は停止したまま、再生位置だけがAマーカーの位置にジャンプします。 |
| <img src="icons/ear.png" width="20"> **Ear Mode（耳マーク）** | 耳コピ用の特別なリピートモード（詳細は後述）。ONのときアイコンが**黄色**になります。 |
| **B** ボタン | **Bマーカーへ移動**します（動作はAボタンと同様）。 |
| <img src="icons/rew.png" width="20"> **早戻し** | 設定した小節数（Rew/FF）だけ前に移動します。 |
| <img src="icons/ab_repeat.png" width="20"> **ABリピート** | A～B区間を繰り返し再生します。ONのときアイコンが**黄色**になります。 |
| <img src="icons/ff.png" width="20"> **早送り** | 設定した小節数（Rew/FF）だけ後ろに移動します。 |

> 💡 **A**・**B** ボタンは、左側情報エリアのA・Bの時間表示（マーカーを**セット**する場所）とは別の、マーカーへ**移動（ジャンプ）する**専用ボタンです。

### 中央: スペクトラムアナライザー（フィルター操作エリア）

左側エリアと波形エリアの間にある帯状の部分です（通常の音声・動画ファイルのみ）。

* 再生中の音を**15バンドのスペクトラムアナライザー**としてリアルタイムに表示します。下に並んだ周波数（25Hz～16KHz）が、各バンドの目印になります。
* この帯にマウスを乗せている間だけ、**フィルター（ハイパス・ローパス）**を操作できるようになります。詳しい使い方は「4. 基本的な使い方 ステップ7」で解説します。

> 💡 NSF/SPC/GBSファイルを開くと、このエリアが **ゲームパネル**（楽曲番号・タイトル・チャンネルボタン）に切り替わります。スペクトラムアナライザーおよびフィルターは、ゲームモード中は使用できません。

### 中央下の波形エリア

* 曲全体の波形が表示されます。再生済みの部分は明るい色になります。
* AマーカーとBマーカーの両方が設定されていると、その間が**黄色い帯**で表示されます。
* **マウスホイール**または**上下ドラッグ**で**拡大・縮小**できます。
* 波形の**A-B区間外を左右ドラッグ**、または下部のバーをドラッグ、または**Shift+ホイール**で**左右スクロール**できます。
* 現在位置の**白い線**、A・Bマーカーの**黄色い線**は、いずれも直接ドラッグして動かせます（詳しくは「4. 基本的な使い方 ステップ5」）。

### 最下部の再生・音量エリア

| 項目 | 説明 |
| :---------------------- | :-------------------------------------------------------- |
| **現在時間**（左下） | 現在の再生位置。ドラッグ・ホイールで変更可能。右クリックで先頭に戻ります。 |
| <img src="icons/play_pause.png" width="20"> **ボタン**（中央） | 再生・一時停止。Shiftを押しながら押すと先頭に戻ります。 |
| **総時間**（右下） | 曲全体の長さ。NSF/GBSのループ曲では**赤く点滅**し、ドラッグ・ホイールで延長できます（後述）。 |
| **メッセージ**（最下部の左） | 操作の結果などが表示されます。 |
| **音量スライダー・%**（最下部の右） | 音量調整（0～200%）。 |  

---

<div style="page-break-before: always;"></div>

## 4. 基本的な使い方

### ステップ1: ファイルを開く

1. <img src="icons/open.png" width="20"> **ファイルを開く**アイコンをクリックします。
2. 耳コピしたい音声・動画ファイルを選びます。
3. 読み込みが終わると波形が表示され、再生できる状態になります。

> 💡 ウィンドウ内へのファイルのドラッグ＆ドロップにも対応しています。
> 💡 初めて開くファイルは内部でWAV変換が行われるため、少し時間がかかることがあります。2回目以降は高速に開きます。  
> 💡 前回そのファイルで作業していた場合、**再生位置・マーカー・速度・キー・Fineなどが自動的に復元**されます。  
> 💡 NSF/SPC/GBSファイルを開く場合は「6. ゲームモードの使い方」を参照してください。  

### ステップ2: 再生・一時停止と速度・キー・Fineの調整

1. 中央の <img src="icons/play_pause.png" width="20"> **ボタン**（またはスペースキー）で再生／一時停止します。
2. **Speed** を調整すると、音の高さを変えずに**再生速度だけ**を変えられます。×0.2 / ×0.25 / ×0.33 / ×0.5 / ×1.0 / ×1.5 / ×2.0 の7段階から選べます。
3. **Key** を調整すると、速度を変えずに**音程だけ**を上下できます（-24～+24半音）。
4. 原曲と手持ちの楽器・環境とでピッチが微妙に合わない時は、**Fine** で-1.00～+1.00の範囲で微調整できます（Keyとは別の独立した値です）。

> **数値の変え方（共通）**
>
> * **上下ドラッグ、マウスホイール**: 少しずつ変化（例: Fineは0.01ずつ）。
> * **Shift+上下ドラッグ、マウスホイール**: 大きく変化（例: Keyは12ずつ、Fineは0.1ずつ）。Beat・Speed・総時間はShiftに対応していません。
> * **ダブルクリック**: 直接キーボードで入力。編集中も上下ドラッグ、マウスホイールで増減できます。
> * **右クリック**: 初期値に戻す。

### ステップ3: テンポを検出して、小節単位で移動する

1. テンポを知りたいあたりまで再生位置を移動します。
2. <img src="icons/tempo_search.png" width="20"> **テンポ検出**アイコンをクリックします。再生位置の前後約10秒を解析し、**Tempo** 欄に検出結果（BPM）が入ります。
3. **Beat**（拍子）と **Bar**（移動したい小節数）を必要に応じて設定すると、Tempo,Beat,Barから算出した時間が**Rew/FF**欄に表示されます。
4. <img src="icons/rew.png" width="20"> **早戻し** / <img src="icons/ff.png" width="20"> **早送り**を押すと、Rew/FFの表示秒数ぶんだけ移動します。

> **Rew/FF（早送り・早戻しの幅）の計算式**  
> `Rew/FF（秒） = 60 ÷ Tempo × Beat × Bar`  
> 例えば Tempo=120、Beat=4、Bar=2 なら、`60 ÷ 120 × 4 × 2 = 4.0秒`（＝2小節分）になります。  
> 💡 逆に **Rew/FFを直接変更**した場合は、`Tempo = 60 × Beat × Bar ÷ Rew/FF` でTempoが逆算されます。「ちょうど3秒戻りたい」といった秒数指定にも対応できます。Beat・Barの値は変わりません。Tempoが30〜300の範囲外になる場合はエラーになり、変更前の値に戻ります。  
> 💡 テンポ検出は再生を一度止めてから行われます。検出中はテンポ関連の入力欄が一時的にグレーになります。  
> 💡 テンポ検出は完全ではなく、誤った値を出力する場合があることをご了承ください。

### ステップ4: A・Bマーカーを設定してリピートする

「この区間を繰り返し聴きたい」というときに使います。

1. リピートを始めたい位置で、左側の **A** の時間ボックスを**1回クリック**します（現在位置がAマーカーにセットされ、一瞬黄色く光ります）。
2. リピートを終わりたい位置で、**B** の時間ボックスを**1回クリック**します。
3. <img src="icons/ab_repeat.png" width="20"> **ABリピート**アイコンをクリックすると、A～B区間が繰り返し再生されます。もう一度押すと解除されます。

> 💡 AよりBを前に設定してしまっても、自動的に入れ替わって「A &lt; B」になります。  
> 💡 マーカーの時間ボックスは、ドラッグで微調整したり、ダブルクリックで直接入力したりもできます。**右クリックでクリア**できます。

**■ ABリピートON時にマーカーが未設定の場合の自動補完**

<img src="icons/ab_repeat.png" width="20"> ABリピートアイコンを押したとき、A・Bのどちらかまたは両方が未設定の場合、**Rew/FFの秒数を使って自動的にマーカーが補完**されます。

| 状態 | 補完のしかた |
| :---------------------- | :-------------------------------------------------------- |
| **A・B両方が未設定** | 現在の再生位置をAにセットし、AにRew/FF秒を足した位置をBにセット |
| **Aのみ設定済み** | AにRew/FF秒を足した位置をBにセット |
| **Bのみ設定済み** | BからRew/FF秒を引いた位置をAにセット |

> 💡 この自動補完は、**A&lt;-&gt;Bボックスの操作**（後述）でも同様に適用されます。

**■ A&lt;-&gt;B（区間の長さ）を直接変更する**

左列の **A&lt;-&gt;B** ボックスは、AマーカーとBマーカーの間隔（秒）を直接編集できます。

* **ドラッグ / Shift+ドラッグ / ホイール / Shift+ホイール**: 0.1秒 / 1.0秒単位で変更します。
* **ダブルクリック**: 秒数を直接キーボード入力できます。
* **変更の効果**: **Aは固定のままBだけが移動**します。Bが総再生時間を超える場合や、A以前になる場合はエラーになります。
* **A・Bどちらかが未設定の場合**: 上記の自動補完が先に実行されてから、区間の長さが変更されます。

**■ Aマーカー・Bマーカーへ移動する**
右側アイコンボタンの **A** / **B** ボタン（Ear Modeアイコンの左右）をクリックすると、再生位置がそのマーカーへジャンプします。再生中なら再生を続けながら、停止中なら停止したまま移動するだけで、**再生状態は変わりません**。

---

### ステップ5: 波形エリアをくわしく使う

波形エリアは、目で見ながら直感的に操作できる便利なエリアです。

**■ 再生位置を移動する（シーク）**
波形を**クリック**すると、その位置へ再生位置がジャンプします。

**■ 拡大・縮小する（ズーム）**
波形の上で**マウスホイールを回す**か、**上下にドラッグ**すると、カーソル位置を中心に拡大・縮小します。細かい部分を聴き取りたいときに、波形を拡大すると見やすくなります。

**■ 左右にスクロールする**
拡大しているときは、次の方法で表示位置を左右に動かせます。

* **A-B区間外**（黄色い帯の外側）の波形を**左右にドラッグ**する。
* 波形の下にある**スクロールバーをドラッグ**する。
* **Shift+マウスホイール**を回す。

**■ ダブルクリックでマーカーをセットする**
波形を**ダブルクリック**すると、その位置にマーカーがセットされます。状況に応じて、セットされるマーカーが自動で選ばれます。

* A・Bどちらも未設定 → **Aがセット**されます。
* どちらか一方だけ未設定 → **未設定の方**にセットされます。
* 両方とも設定済み → **クリック位置に近い方**のマーカーが置き換わります。

**■ ダブルクリックで既存のマーカーをリセットする**
既に置かれている**AマーカーやBマーカーの真上**（数px程度の許容範囲内）をダブルクリックすると、新しいマーカーを置くのではなく、**そのマーカー自体がリセット（解除）**されます。

* マーカーが1個しかない状態でその真上をダブルクリックした場合も、新しいマーカーを置くより**既存マーカーのリセットが優先**されます。
* A・B両方がダブルクリック許容範囲内にある場合は、**より近い方だけ**がリセットされます（1回の操作で両方リセットされることはありません）。

> 💡 波形のシングルクリックは「クリックした位置へ再生位置を移動（シーク）」する操作ですが、**ダブルクリックはマーカー操作専用**で、再生位置そのものは動きません。ダブルクリックの1回目のクリックで一瞬シークしたように見えても、ダブルクリックが確定した時点で元の再生位置に戻ります。

**■ 黄色い帯（A～B区間）をドラッグして区間ごと移動する**
A・B両方が設定されているとき、波形の**黄色い帯を左右にドラッグ**すると、**区間の長さ（間隔）を保ったまま、AとBが一緒に移動**します。
「この2小節を、もう少し後ろにずらして確認したい」というときに最適です。

**■ 現在位置線・マーカー線を直接ドラッグして移動する**
波形に表示されている**現在位置の白い線**や、**A・Bマーカーの黄色い線**は、その線の上を直接つかんでドラッグすることで個別に移動できます（黄色い帯の内側をつかむ「区間ごと移動」とは異なる操作です）。

* **現在位置の線をドラッグ** → ドラッグ中は時間表示が連動して動き、マウスを離した時点の位置へ実際にシークします。
* **A・Bどちらかの線をドラッグ** → 通常時はそのマーカーだけが動きます（もう片方のマーカーを追い越すことはできません）。
* **Ear Mode中にA・Bどちらかの線をドラッグ** → 区間の長さを保ったまま、A・Bが連動して動きます（黄色い帯のドラッグと同じ動き方になります）。

> 💡 ABリピート再生中やEar Mode再生中は、A・Bマーカーのどちらの移動方法（黄色い帯のドラッグ／マーカー線の個別ドラッグ／左側情報エリアでのドラッグ）でも、現在再生している位置を追い越さないように移動が制限されます。停止中は自由に動かせます。  
> 💡 再生中に波形を拡大しておくと、再生位置が画面の右80%あたりに来たところで、波形が自動でスクロールして追従します。

---

### ステップ6: Ear Mode（耳コピモード）を使う

**Ear Mode** は、ABリピートをさらに耳コピ向けに進化させたモードです。「同じ長さの区間を保ったまま、少しずつ位置をずらして反復再生させる」のに向いています。

ABリピートとの一番の違いは、**区間の長さ（A～Bの間隔）を固定したまま操作できる**点です。

**■ Ear Modeをオンにする**

1. A・B両方のマーカーを設定しておきます。
2. <img src="icons/ear.png" width="20"> **Ear Mode**アイコンをクリックします。アイコンが**黄色**になり、A・Bの時間表示や Rew・FFアイコンなどが青く点滅し始めます。これがONの合図です。

![Ear ModeがオンのときのEar Mode_Capture](icons/Ear_Mode_Capture.png)

3. A～B区間が繰り返し再生されます。

**■ Ear Mode中の特別な動き（区間の長さを保つ）**
Ear Mode中は、A・Bが常に「セットで」動きます。

* **片方のマーカー時間をドラッグ**（左側情報エリアの時間表示、または波形上のマーカー線のいずれでも）すると、もう片方も**同じ間隔を保ったまま連動**して動きます。
* **片方の時間を直接入力**しても、間隔を保ってもう片方が変化します。
* <img src="icons/rew.png" width="20"> **早戻し** / <img src="icons/ff.png" width="20"> **早送り**を押すと、A・Bの区間ごと、Rew/FFの表示秒数ぶん移動します。

> 💡 これにより、「2小節ぶんの区間」を保ったまま、曲の頭から少しずつ後ろへずらして反復再生させる、といった使い方ができます。  
> 💡 移動の結果が曲の範囲外になる場合は、操作を受け付けず、元の状態が保たれます。  
> 💡 ABリピートとEar Modeは同時にはオンにできません（一方をオンにすると、もう一方は自動でオフになります）。

**■ Ear Modeをオフにする**
もう一度 <img src="icons/ear.png" width="20"> アイコンをクリックすると解除され、点滅も止まります。

---

### ステップ7: スペクトラムアナライザー・フィルターを使う

左側の情報エリアと波形エリアの間にある帯状のエリアでは、**音の周波数バランスの確認**と**フィルター（ハイパス・ローパス）による音質調整**ができます（ゲームモードは非対応）。

**■ スペクトラムアナライザーを見る**
再生中、この帯に**15本のバー**がリアルタイムに表示され、今聴いている音にどの周波数（低音～高音）がどれだけ含まれているかが一目でわかります。下に並んだ **25・40・63・100・160・250・400・630・1K・1.6K・2.5K・4K・6.3K・10K・16K** の数字が、各バーの周波数（Hz）の目印です。

**■ フィルターをかける（マウスを乗せている間だけ操作可能）**

1. スペクトラムアナライザーの帯に**マウスを乗せる**と、フィルター操作モードになります。
2. **聴かせたい帯域の上を左右にドラッグ**します。例えば「63」のあたりから「1K」のあたりまでドラッグすると、その範囲だけを通す**バンドパスフィルター**になります。
3. ドラッグを離すと、その範囲が**通過域（パスバンド）**として確定します。

![フィルター操作中のFilter_Capture](icons/Filter_Capture.png)

> 💡 ドラッグした範囲の**外側は、1オクターブごとに-24dBずつ減衰**していきます（緩やかにフェードアウトするイメージで、ピタッと無音になるわけではありません）。  
> 💡 範囲の**左端が一番低い「25」を含む**ときは、低い方を削る必要が無いので、自動的に**ローパスフィルターのみ**（高い方だけ削る）になります。  
> 💡 同様に、範囲の**右端が一番高い「16K」を含む**ときは、自動的に**ハイパスフィルターのみ**（低い方だけ削る）になります。  
> 💡 フィルターをかけている間は、マウスオーバー中に実際の効果（おおむねの音量カーブ）が**黄色い線**でスペクトラムアナライザーの上に重ねて表示されます。

**■ フィルターを解除する**
スペクトラムアナライザーの帯の中で**右クリック**すると、フィルターが解除され、元の音（全帯域）に戻ります。<img src="icons/reset.png" width="20"> **すべてリセット**（または **R** キー）でも解除されます。

> 💡 フィルターの設定も、マーカーや速度などと同様に**曲ごとに記憶**されます。次にそのファイルを開いたときも、同じフィルターがかかった状態で再開できます。

---

<div style="page-break-before: always;"></div>

## 6. ゲームモードの使い方（NSF・SPC・GBS）

「もろこしタイム」は、NSF（NES/ファミコン）・SPC（SNES/スーパーファミコン）・GBS（Game Boy）の3種類のゲーム音楽フォーマットに対応しています。これらのファイルを開くと、スペクトラムアナライザーのエリアが**ゲームパネル**に切り替わります。

![ゲームモードのメイン画面](icons/GameMode_Capture.png)

### ゲームパネルの構成

ゲームパネルは上下2段に分かれています。

**上段: 楽曲ナビゲーション**

| 項目 | 説明 |
| :---------------------- | :-------------------------------------------------------- |
| **&lt;** ボタン | 前の曲へ |
| **曲番号** | 現在再生中の曲番号。ドラッグ・ホイール・ダブルクリックで変更できます。<br>Shiftを押しながらドラッグ・ホイールで10曲単位で移動します。 |
| **&gt;** ボタン | 次の曲へ |
| **/XXX** | ファイル内の総曲数（複数曲がある場合）。 |
| **タイトル表示** | ゲームタイトルや現在の曲タイトルを表示します（NSFeやm3u付きSPC/GBSのみ）。 |

**下段: チャンネルON/OFFボタン**

音源チャンネルが並んで表示されます。数はフォーマットによって異なります。

| フォーマット | チャンネル数 |
| :--- | :--- |
| NSF（NES/ファミコン） | 最大13ch（基本5ch＋拡張音源） |
| SPC（SNES/スーパーファミコン） | 8ch（固定） |
| GBS（Game Boy） | 4ch（固定） |

* **グレーアウトしているボタン**: その曲で使われていないチャンネルです。
* **ON（黄色い枠）**: 再生に含まれています。
* **OFF（暗い表示）**: ミュートされています。

**チャンネルの操作方法:**

| 操作 | 結果 |
| :---------------------- | :-------------------------------------------------------- |
| **クリック** | そのチャンネルのみON、他は全てOFF（ソロ） |
| **Shift+クリック** | そのチャンネルのON/OFFを切り替え |
| **右クリック** | 全チャンネルをリセット（使用チャンネル全部ON） |

### ファイルの開き方

**単体ファイル**: 通常の **<img src="icons/open.png" width="20"> ファイルを開く** から選択できます。  
**ZIPファイル**: ZIPをそのまま選択するだけで、中身のゲーム音楽ファイルを自動的に認識して開きます。複数のSPCファイルが入ったZIPは、それぞれの曲を切り替えながら再生できます。  
**フォルダのドラッグ＆ドロップ**: フォルダをウィンドウにドロップすると、フォルダ内のゲーム音楽ファイル（NSF/SPC/GBS）を一括認識します。**Shift+ <img src="icons/open.png" width="20"> ファイルを開く**で、フォルダを開くダイアログウィンドウを出すことも出来ます。

### 総再生時間の拡張（ループ曲）

ゲーム音楽の多くはループ（繰り返し）するため、「曲の終わり」が自動検出できません。

* **自然終了した曲**: 総時間が自動で確定し、通常のファイルと同様に再生されます。
* **ループ曲（自然終了しない曲）**: 右下の**総時間表示が赤く点滅**します。デフォルトの時間はNSF/GBSが1分、SPCが2分です（SPC内にループ情報が含まれる場合は自動確定します）。

ループ曲の再生時間を伸ばすには:

1. 右下の**赤く点滅している総時間表示**を上下にドラッグするか、マウスホイールを回します。
2. 追加分がリアルタイムにデコードされ、波形が延長されます。
3. 延長後に自然終了が確認されると、点滅が止まり時間が確定します。

> 💡 再生時間の設定も、他の情報と同様に曲ごとに記憶されます。

### セッションの保存（全曲対応）

NSF/SPC/GBSファイルを閉じると、**そのファイル内のすべての曲**（一度でも再生・閲覧した曲）の状態が個別に保存されます。

次回同じファイルを開くと:

* 最後に開いていた曲が自動的に選択されます。
* 各曲の**再生位置・ABマーカー・チャンネルON/OFF**がそれぞれ復元されます。

### NSFの拡張音源

NSFファイルのみ、以下の拡張音源チャンネルに対応しています。

| 拡張音源 | 説明 |
| :---------------------- | :-------------------------------------------------------- |
| **VRC6** | Konami製。追加パルス波×2、鋸歯状波×1（計3ch） |
| **VRC7** | Konami製FM音源。6ch |
| **FDS** | ファミコンディスクシステム音源。1ch |
| **MMC5** | 追加パルス波×2、PCM×1（計3ch） |
| **Namco163 (N163)** | ナムコ製波形メモリ音源。最大8ch |
| **Sunsoft 5B** | サンソフト製FM音源（YM2149ベース）。3ch |

---

<div style="page-break-before: always;"></div>

## 7. 既知のバグ・制限事項

| 内容 | 詳細 |
| :---------------------- | :--------------------------------------------------------------- |
| **チャンネル認識の誤検出** | 特定のゲーム音楽ファイルで、一部のチャンネルが「使用している」と誤って認識され、正しくグレーアウトされない場合があります。この場合、手動でOFFにすることができます。 |
| **ゲームモードのスペクトラムアナライザー非対応** | NSF/SPC/GBSモード中はスペクトラムアナライザーおよびフィルターは使用できません。 |
| **テンポ検出の精度** | テンポ検出は自己相関法を用いた推定です。複雑なリズムの曲や一定でないテンポの曲では、誤った値が検出される場合があります。 |

---

<div style="page-break-before: always;"></div>

## 8. ショートカット

「もろこしタイム」は、通常のショートカットとは別に、**テンキーだけでほとんどの操作が完結**するよう隠しショートカット（裏ボタン）を用意しています。テンキーの数字の並びが、ほぼそのまま画面右側のアイコンの配置に対応しているので、慣れると手元を見ずに片手で操作できます。

| メインキー | テンキー | 機能 |
| :-------------------- | :-------------------- | :--------------------------------------------------------------- |
| **Space** | **0** | 再生 / 一時停止 |
| **←** | **1** | 早戻し |
| **Shift+←** | **Enter+1** | 前の曲（ゲームモード時のみ） |
| **↓** | **2** | ABリピート 切り替え |
| **→** | **3** | 早送り |
| **Shift+→** | **Enter+3** | 次の曲（ゲームモード時のみ） |
| **A** | **4** | Aマーカーへ移動 |
| **Shift+A** | **Enter+4** | Aマーカーをセット |
| **↑** | **5** | Ear Mode 切り替え |
| **B** | **6** | Bマーカーへ移動 |
| **Shift+B** | **Enter+6** | Bマーカーをセット |
| **O** | **7** | ファイルを開く |
| **T** | **8** | テンポ検出 |
| **R** | **9** | すべてリセット |
| **Shift+R** | **Enter+9** | キャッシュクリア |
| **H** | **／**（スラッシュ） | Help（取扱説明書を開く） |
| **Z** | **＊**（アスタリスク） | Zoom（画面表示倍率を切り替え） |
| **1** ～ **¥**（最上段） | （対応無し） | ゲームモード: チャンネルをソロ（そのchのみON、他は全てOFF） |
| **Shift+1 ～ ¥** | （対応無し） | ゲームモード: チャンネルのON/OFFを切り替え |
| **,** | （対応無し） | 前の曲（ゲームモード時のみ） |
| **Shift+,** | （対応無し） | 10曲前へ（ゲームモード時のみ） |
| **.** | （対応無し） | 次の曲（ゲームモード時のみ） |
| **Shift+.** | （対応無し） | 10曲次へ（ゲームモード時のみ） |

> 💡 テンキーのEnterを使用する操作をする場合、テンキーEnterを押した直後（1.5秒以内）に次のキーを押してください。  
> 💡 時間やテンポなどを**直接入力している最中は、ショートカットは無効**になります（入力の邪魔をしません）。  
> 💡 **キーボードの種類による差異**: JISキーボードでは最上段12・13番目のキーは `^` と `¥` です。USキーボードでは対応するキーは `=` と `\` になります。アプリが自動判別します。

---

<div style="page-break-before: always;"></div>

## 9. あとがき

数あるメディアプレイヤーの中から**「もろこしタイム」**を見つけていただき、ありがとうございます！

開発者である私は、これまで公私問わず、膨大な数の楽曲を「耳コピ」してきました。
しかし、既存の有名なメディアプレイヤーをどれだけ試しても、耳コピ作業中にある**「強烈なストレス」**と付き合い続ける必要があったのです。

* **「早送り・早戻しの単位は、秒数じゃなくて『小節数』で指定したい！」**
* **「ABリピートの幅（2小節分など）を保ったまま、位置を前後にスライド移動させたい！」**
* **「前回起動時の再生位置を覚えていて欲しい！」**
* **「動画ファイルを再生すると、キーフレーム単位でしか大雑把にスキップできないのがもどかしい！」**
* **「そもそも音だけ聴きたいのに、映像ウィンドウが画面を圧迫して邪魔！」**
* **「耳コピ中、原曲と手持ちの環境のピッチが微妙に合っていなくて気持ち悪い！」**

「もっと耳コピに特化した、プレイヤーとしての理想の形があるはずだ――」
そんな**耳コピストとしての魂の叫び**をすべて解決し、徹底的に作業を効率化するために自作した究極のツール、それがこの「もろこしタイム」です。



### 🌽 余談：なぜ「もろこしタイム」なのか？

一見、音楽とは何の関係もないように思えるこの名前には、ちょっとした思い出があります。

以前、あるレトロゲームの楽曲を耳コピしてピアノで演奏し、YouTubeに動画を投稿したときのことでした。
それを見た北海道在住の方から「ぜひ楽譜が欲しい」と連絡があり、無償でお送りしたところ、後日お礼として**大量の立派なトウモロコシ**が届いたのです。

採れたてのトウモロコシは本当に美味しく、それ以来、私の脳内には**「耳コピを頑張ると、美味しいトウモロコシがもらえる」**という幸せな因果関係が深く焼き付いてしまいました。

いつしか私にとって、集中して耳コピに没頭する時間のことは、親しみを込めて**「もろこしタイム」**と呼ばれるようになりました。

このアプリは、そんな私の「耳コピへの情熱と遊び心」から生まれています。
あなたの耳コピライフ、そして音楽制作の時間が、より快適で豊か（実り多いもの）になりますように！

---

**Morokoshi Time v1.6.0**  
*Created by Ike-san*

---

<div style="page-break-before: always;"></div>

<!-- EN_START -->
# Morokoshi Time – Music Transcription Media Player User Manual

(Target version: v1.6.0)

---

## Revision History

| Version | Date | Changes |
| :-------------------- | :-------------------- | :--------------------------------------------------------------- |
| **v1.0** | 2026/6/16 | Initial release |
| **v1.3** | 2026/6/18 | Added spectrum analyzer and filter features.<br>Added Zoom feature to double the display size.<br>Added A/B marker navigation buttons on both sides of the Ear Mode icon (better numpad alignment).<br>Waveform area: current-position and marker lines can now be dragged directly.<br>Various display and usability fixes. |
| **v1.4** | 2026/6/19 | **A&lt;-&gt;B** and **Rew/FF** values are now directly editable (drag, wheel, or keyboard input). Changing Rew/FF back-calculates Tempo automatically.<br>Expanded Tempo range to 30–300. Documented auto-fill behavior when AB Repeat is ON but markers are not set.<br>Library optimization reduces .exe file size significantly (approx. 136 MB → approx. 49 MB). |
| **v1.5.0** | 2026/6/23 | **NSF (NES/Famicom game music) support**. Per-channel ON/OFF, multi-track switching, extended total playback time, and more.<br>**Automatic ffmpeg download** — ffmpeg is fetched automatically if not already present.<br>Enhanced state saving for all files including NSF (playback position, markers, etc. stored per track). |
| **v1.6.0** | 2026/6/28 | **SPC (SNES/Super Famicom game music) support**. Per-channel ON/OFF, open ZIP files directly as multi-track collections, etc.<br>**GBS (Game Boy game music) support**. Per-channel ON/OFF, multi-track switching, etc.<br>**NSF/SPC/GBS can now be opened directly from a ZIP archive** (no extraction needed).<br>**Drag & drop a folder** to batch-recognize all game music files inside.<br>All numeric input boxes now support mouse wheel (change values without entering edit mode).<br>Waveform area can now be zoomed by dragging up/down.<br>Drag outside the A-B region of the waveform to scroll left/right.<br>Speed changed to 7 fixed steps (×0.2, ×0.25, ×0.33, ×0.5, ×1.0, ×1.5, ×2.0).<br>Fixed startup noise in game music (NSF/SPC/GBS) by applying improved libgme.dll. |

---

<div style="page-break-before: always;"></div>

## 1. Features

"Morokoshi Time" is a media player built specifically for music transcription (ear training). Key features include:

* **Converts audio to WAV internally on load.** By stripping video and working with audio only, the "keyframe-only seeking" limitation of video files is eliminated — you can seek smoothly to any position.
* **Automatic tempo detection.** The app analyzes approximately 10 seconds of audio around the current playback position and calculates the song's BPM automatically.
* **Navigate by measure.** Using the detected tempo, you can jump forward or backward by whole-measure increments — "go back exactly 2 measures" in a single keystroke.
* **Slide the A-B repeat region while preserving its length.** You can shift the entire repeat region forward or backward without changing the interval — perfect for "nudge this 2-bar loop a bit later."
* **Change playback speed and pitch independently.** Pitch can be adjusted in semitones (**Key**) and also fine-tuned from −1.00 to +1.00 (**Fine**) to correct any slight pitch drift between the original and your instrument or environment.
* **15-band spectrum analyzer** displays the frequency balance of the audio in real time during playback (standard audio/video files only).
* **Highpass/lowpass filter** lets you isolate the frequency range you want to hear, or cut unwanted bass or treble (standard audio/video files only).
* **Per-file state persistence.** Playback position, markers, speed, key, Fine, filters, and more are remembered for each file. The next time you open the same file, you pick up exactly where you left off.
* **NSF (NES/Famicom), SPC (SNES/Super Famicom), and GBS (Game Boy) game music support.** Features include per-channel ON/OFF muting and multi-track switching — everything you need for game music transcription. (See "6. Game Mode" for details.)
* **Open ZIP files directly** — no need to extract game music files first.
* **Compact and simple design** that stays out of your way, with no video window crowding your screen.

---

<div style="page-break-before: always;"></div>

## 2. System Requirements, Installation & Launching

### System Requirements

* **OS**: Windows 10 / 11 (64-bit)
* **ffmpeg**: Required to convert media files to WAV internally. Not required for NSF/SPC/GBS files.

### About ffmpeg

"Morokoshi Time" uses **ffmpeg** internally to open standard audio and video files.

* **If ffmpeg is not found, it is downloaded automatically the first time you open a file** (requires an internet connection). The download happens once; subsequent launches use the cached copy.
* To provide ffmpeg manually, place `ffmpeg.exe` in the **same folder as `morokoshi.exe`**, or in a location on Windows' PATH.
* When no file is open, hovering over the status bar (bottom of the window) shows the path of the ffmpeg currently in use.

### Supported File Formats

Most major audio and video formats are supported:

`.mp3` `.mp4` `.wav` `.flac` `.aac` `.ogg` `.m4a` `.wma` `.opus` `.webm` `.avi` `.mkv` `.mov` and more

**Game music files**: The following formats are also supported. ffmpeg is not required for these.

| Format | Description |
| :--- | :--- |
| `.nsf` `.nsfe` | NES/Famicom game music (NSF) |
| `.spc` | SNES/Super Famicom game music (SPC) |
| `.gbs` | Game Boy game music (GBS) |

> 💡 You can open a **ZIP file containing the above game music files directly**, or **drag & drop a folder** to batch-recognize all game music files inside.

### Installation and Launch

No installation is required.

1. Place **`morokoshi.exe`** and the bundled **DLL files** (e.g., `libgme.dll`) in the same folder.
2. **Double-click to launch.**

That's it. To uninstall, simply delete these files.

> 💡 The DLL files are required for **NSF, SPC, and GBS playback**. Even if you only plan to use standard audio/video files, keep them in the same folder.

### Bundled Library Licenses

This application uses the following open-source libraries:

| Library | File | License / Source |
| :---------------------- | :------------------------------- | :----------------------------------------------------- |
| Game_Music_Emu (libgme) | `libgme.dll` | LGPL 2.1<br>https://github.com/ike0904/game-music-emu-morokoshi |
| GCC Runtime | `libgcc_s_seh-1.dll` | GPL + Runtime Library Exception |
| libstdc++ | `libstdc++-6.dll` | GPL + Runtime Library Exception |
| winpthreads | `libwinpthread-1.dll` | MIT / BSD |
| zlib | `zlib1.dll` | zlib License |

> `libgme.dll` is bundled as a separate file under LGPL v2.1, and you may replace it with a version you build yourself. Full license texts are included in the bundled `license.txt`.

### Where Settings and Cache Are Stored

Work data (playback position, markers, etc.) and converted WAV files are stored in a hidden folder in your user profile:

```
C:\Users\(your username)\.morokoshi_cache\
```

* Once a file is opened, its WAV is cached here, so **subsequent opens are much faster** (no re-conversion).
* Files in this folder are **automatically deleted after 30 days of inactivity**.
* If disk space is a concern, you can safely delete the contents of this folder (they will be recreated next time you open a file).

### Clearing the Cache (from within the app)

You can clear the entire cache folder from within the app:

* **Hold Shift and click the "Reset All" icon** — a confirmation dialog will appear.
* **Select "Yes"** to delete the `.morokoshi_cache` folder and automatically restart the app.

> ⚠️ Clearing the cache removes not only the converted WAV files but also all saved work data (playback positions, markers, etc.) for every file. Use with caution.

---

<div style="page-break-before: always;"></div>

## 3. Screen Overview

When launched, the following window appears:

![Main Screen](icons/Main_Capture.png)

The window is divided into the **Info Area (left)**, **Icon Buttons (right)**, **Spectrum Analyzer / Filter Area (center)**, **Waveform Area (center-bottom)**, and **Playback & Volume Area (bottom)**.

> 💡 When an NSF/SPC/GBS file is open, the spectrum analyzer area switches to the **Game Panel** (track selection and channel ON/OFF). See "6. Game Mode" for details.

### Info Area (Left) — Numeric Display and Input

This area is arranged in **two vertical columns** (left column and center column), each listing related items from top to bottom.

| Field | Description |
| :---------------------- | :-------------------------------------------------------- |
| **A&lt;-&gt;B** | The interval (length) between the A and B markers. Editable by drag, wheel, or direct input. Changing it moves B while A stays fixed. Auto-fill applies if either marker is not set (see below). |
| **A** | A marker (repeat start) position in time. |
| **B** | B marker (repeat end) position in time. |
| **Key** | Pitch in semitones. Range: −24 to +24 (1 semitone per step). |
| **Fine** | Fine-tune pitch. Range: −1.00 to +1.00 (1.00 = one semitone). Independent of Key; use this to correct slight pitch drift between the original and your environment. |
| **Rew/FF** | Rewind/fast-forward distance in seconds. Auto-calculated from Tempo, Beat, and Bar. Can also be set directly; doing so back-calculates Tempo. |
| **Tempo** | Song tempo (BPM). Range: 30–300. |
| **Beat** | Time signature (beats per measure). Range: 1–16. |
| **Bar** | Number of measures per Rew/FF jump. Range: 0.1–100. |
| **Speed** | Playback speed. 7 fixed steps: ×0.2, ×0.25, ×0.33, ×0.5, ×1.0, ×1.5, ×2.0. |

All numeric input boxes share the same interaction methods (details in "4. Basic Usage"):

* **Drag up/down** to increase/decrease; **Shift+drag** for larger steps (most fields)
* **Mouse wheel** to increase/decrease; **Shift+wheel** for larger steps (most fields)
* **Double-click** to type a value directly; wheel also works while in edit mode
* **Right-click** to reset to default

### Icon Buttons (Right)

Icons are arranged in 4 rows corresponding to the numpad layout (see "8. Shortcuts"). For example, the 3rd row — **A (Go), Ear Mode, B (Go)** — maps to numpad **4, 5, 6**.

| Item | Description |
| :---------------------- | :-------------------------------------------------------- |
| <img src="icons/help.png" width="20"> **Help** | Opens the user manual PDF in your default PDF viewer. Requires `morokoshi_manual.pdf` in the same folder as `morokoshi.exe`. |
| <img src="icons/zoom.png" width="20"> **Zoom** | Toggles display scaling between 2× and 1×. Use when text and buttons are too small to read comfortably. |
| <img src="icons/open.png" width="20"> **Open File** | Opens a file selection dialog to load a media file. |
| <img src="icons/tempo_search.png" width="20"> **Detect Tempo** | Analyzes approximately 10 seconds around the current position to auto-detect BPM. |
| <img src="icons/reset.png" width="20"> **Reset All** | Resets markers, speed, key, Fine, tempo, filters, and more to their defaults. |
| **A** button | **Go to A marker.** Jumps playback position to the A marker. Playback state does not change. |
| <img src="icons/ear.png" width="20"> **Ear Mode (ear icon)** | Activates Ear Mode — a special transcription-focused repeat mode (details below). Icon turns **yellow** when ON. |
| **B** button | **Go to B marker.** Jumps to the B marker (same behavior as A button). |
| <img src="icons/rew.png" width="20"> **Rewind** | Moves back by the Rew/FF distance. |
| <img src="icons/ab_repeat.png" width="20"> **AB Repeat** | Loops the A–B region. Icon turns **yellow** when ON. |
| <img src="icons/ff.png" width="20"> **Fast-Forward** | Moves forward by the Rew/FF distance. |

> 💡 The **A** and **B** buttons (on either side of the Ear Mode icon) are for **jumping to** markers. They are separate from the A/B time fields in the Info Area, which are for **setting** markers.

### Center: Spectrum Analyzer / Filter Area

The horizontal band between the Info Area and the Waveform Area (standard audio/video files only).

* Displays **15 frequency bands** in real time during playback. The labels **25, 40, 63, 100, 160, 250, 400, 630, 1K, 1.6K, 2.5K, 4K, 6.3K, 10K, 16K** (Hz) mark each band.
* While the mouse hovers over this area, **filter (highpass/lowpass) controls** become available. See "Step 7" in Basic Usage for details.

> 💡 When an NSF/SPC/GBS file is open, this area switches to the **Game Panel**. The spectrum analyzer and filter are not available in Game Mode.

### Waveform Area (Center-Bottom)

* Displays the entire waveform of the loaded file. The already-played portion appears in a brighter color.
* When both A and B markers are set, the region between them is highlighted in **yellow**.
* **Mouse wheel** or **drag up/down** to **zoom in/out** (centered on the cursor).
* **Drag left/right outside the A-B region**, drag the scroll bar at the bottom, or use **Shift+wheel** to **scroll left/right**.
* The **white current-position line** and the **yellow A/B marker lines** can all be dragged directly (see "Step 5" for details).

### Playback & Volume Area (Bottom)

| Item | Description |
| :---------------------- | :-------------------------------------------------------- |
| **Current Time** (bottom-left) | Current playback position. Editable by drag or wheel. Right-click to return to the beginning. |
| <img src="icons/play_pause.png" width="20"> **Button** (center) | Play / Pause. Hold Shift while clicking to return to the beginning. |
| **Total Time** (bottom-right) | Total length of the file. For looping NSF/GBS tracks, **blinks red** — drag or scroll to extend (see Game Mode). |
| **Message** (far-left bottom) | Displays operation results and status messages. |
| **Volume slider / %** (far-right bottom) | Volume control (0–200%). |

---

<div style="page-break-before: always;"></div>

## 4. Basic Usage

### Step 1: Opening a File

1. Click the <img src="icons/open.png" width="20"> **Open File** icon.
2. Select the audio or video file you want to transcribe.
3. When loading is complete, the waveform appears and playback is ready.

> 💡 You can also drag and drop a file directly onto the window.
> 💡 The first time a file is opened it is converted to WAV internally — this may take a moment. Subsequent opens are much faster.
> 💡 If you previously worked with this file, **playback position, markers, speed, key, Fine, and other settings are automatically restored.**
> 💡 For NSF/SPC/GBS files, see "6. Game Mode."

### Step 2: Play/Pause, Speed, Key, and Fine

1. Click the <img src="icons/play_pause.png" width="20"> **button** (or press Space) to play/pause.
2. Adjust **Speed** to change the **playback rate without affecting pitch**. Choose from 7 steps: ×0.2, ×0.25, ×0.33, ×0.5, ×1.0, ×1.5, ×2.0.
3. Adjust **Key** to shift **pitch without affecting speed** (−24 to +24 semitones).
4. If the pitch is slightly off between the original and your instrument, use **Fine** (−1.00 to +1.00, independent of Key) to correct it.

> **Changing values (all numeric fields)**
>
> * **Drag up/down or mouse wheel**: small steps (e.g., Fine changes by 0.01).
> * **Shift+drag or Shift+wheel**: large steps (e.g., Key jumps by 12, Fine by 0.1). Beat, Speed, and Total Time do not support Shift.
> * **Double-click**: type a value directly; drag and wheel also work while in edit mode.
> * **Right-click**: reset to default.

### Step 3: Detecting Tempo and Navigating by Measure

1. Move the playback position near the tempo you want to detect.
2. Click the <img src="icons/tempo_search.png" width="20"> **Detect Tempo** icon. The app analyzes about 10 seconds around the current position and fills in the **Tempo** field.
3. Set **Beat** (time signature) and **Bar** (number of measures) as needed. The calculated time appears in the **Rew/FF** field.
4. Use <img src="icons/rew.png" width="20"> **Rewind** / <img src="icons/ff.png" width="20"> **Fast-Forward** to jump by the Rew/FF distance.

> **Rew/FF calculation**
> `Rew/FF (seconds) = 60 ÷ Tempo × Beat × Bar`
> Example: Tempo=120, Beat=4, Bar=2 → `60 ÷ 120 × 4 × 2 = 4.0 sec` (= 2 measures).
> 💡 You can also **set Rew/FF directly** to specify an exact number of seconds; Tempo is back-calculated as `Tempo = 60 × Beat × Bar ÷ Rew/FF`. Beat and Bar are unchanged. If the resulting Tempo would be outside 30–300, the change is rejected.
> 💡 Tempo detection briefly pauses playback. Tempo-related fields turn grey during detection.
> 💡 Tempo detection is an estimate and may return incorrect values for complex or variable-tempo songs.

### Step 4: Setting A/B Markers and Repeating

Use this to loop a specific section of a song.

1. At the position where you want the repeat to start, **single-click** the **A** time field in the Info Area (the current position is set as the A marker, and the field briefly flashes yellow).
2. At the position where you want the repeat to end, **single-click** the **B** time field.
3. Click the <img src="icons/ab_repeat.png" width="20"> **AB Repeat** icon to loop the A–B region. Click again to turn it off.

> 💡 If you accidentally set B before A, the markers are swapped automatically so that A < B.
> 💡 The A and B time fields can be fine-tuned by dragging or edited directly by double-clicking. **Right-click to clear** a marker.

**■ Auto-fill when AB Repeat is ON but markers are not set**

When you click <img src="icons/ab_repeat.png" width="20"> AB Repeat and one or both markers are missing, markers are **automatically filled in using the Rew/FF distance**:

| State | Auto-fill behavior |
| :---------------------- | :-------------------------------------------------------- |
| **Neither A nor B set** | A = current position; B = A + Rew/FF |
| **A set only** | B = A + Rew/FF |
| **B set only** | A = B − Rew/FF |

> 💡 The same auto-fill logic applies when you edit the **A&lt;-&gt;B** field (see below).

**■ Editing A&lt;-&gt;B (interval length) directly**

The **A&lt;-&gt;B** field shows the distance between A and B in seconds and can be edited directly.

* **Drag / Shift+drag / wheel / Shift+wheel**: changes in 0.1-second / 1.0-second steps.
* **Double-click**: type the number of seconds directly.
* **Effect**: **A stays fixed; only B moves**. If B would exceed the total length or land before A, the change is rejected.
* **If either marker is missing**: auto-fill is performed first, then the interval is updated.

**■ Jumping to A and B markers**

Click the **A** or **B** button (on either side of the Ear Mode icon) to jump the playback position to that marker. Playback continues if playing; stops stay stopped — **playback state is not changed**.

---

### Step 5: Using the Waveform Area in Detail

The waveform area lets you navigate and set markers visually and intuitively.

**■ Seeking (moving the playback position)**
**Click** anywhere in the waveform to jump the playback position to that point.

**■ Zooming in/out**
**Scroll the mouse wheel** or **drag up/down** over the waveform to zoom in or out, centered on the cursor. Zooming in makes fine sections easier to see and hear.

**■ Scrolling left/right**
When zoomed in, you can scroll using any of these methods:

* **Drag left/right outside the A-B region** (outside the yellow band).
* **Drag the scroll bar** at the bottom of the waveform.
* **Shift+mouse wheel**.

**■ Double-clicking to set markers**
**Double-click** in the waveform to set a marker at that position. Which marker is set is determined automatically:

* Neither A nor B set → **A is set**.
* One marker missing → the **missing one** is set.
* Both markers set → the **marker closer to the click** is replaced.

**■ Double-clicking to clear a marker**
Double-clicking **directly on an existing A or B marker line** (within a few pixels) clears that marker instead of placing a new one.

* Even if only one marker exists, clicking on it clears it rather than placing a new marker.
* If both markers are within the double-click tolerance, only the **closer one** is cleared.

> 💡 A single click always seeks to the clicked position. A double-click is exclusively a **marker operation** and does not move the playback position — even if the position appears to move briefly on the first click, it snaps back when the double-click is confirmed.

**■ Dragging the yellow band to slide the A-B region**
When both markers are set, **dragging the yellow A-B band left or right** moves **both A and B together, preserving the interval** — ideal for sliding a 2-bar loop slightly forward or backward.

**■ Dragging position/marker lines directly**
The **white current-position line** and the **yellow A/B marker lines** can be grabbed and dragged individually (distinct from dragging the yellow band):

* **Drag the current-position line** → the time display updates as you drag; playback seeks to the release point.
* **Drag an A or B line** → normally moves only that marker (cannot cross the other marker).
* **Drag an A or B line while in Ear Mode** → moves both A and B together (same as dragging the yellow band).

> 💡 While AB Repeat or Ear Mode is active, any marker movement is constrained so it cannot cross the current playback position. While stopped, markers can be moved freely.
> 💡 While playing with the waveform zoomed in, the waveform auto-scrolls to follow playback when the position reaches about 80% from the left edge.

---

### Step 6: Ear Mode

**Ear Mode** enhances AB Repeat for transcription. It is designed for **looping a fixed-length region while gradually sliding it forward through the song**.

The key difference from AB Repeat is that the **interval length (A–B distance) stays fixed** as you make adjustments.

**■ Turning Ear Mode ON**

1. Set both A and B markers.
2. Click the <img src="icons/ear.png" width="20"> **Ear Mode** icon. The icon turns **yellow**, and the A/B time displays and Rew/FF icons start **blinking blue** — Ear Mode is active.

![Ear Mode active](icons/Ear_Mode_Capture.png)

3. The A–B region plays on repeat.

**■ Special behavior in Ear Mode (preserving interval length)**
In Ear Mode, A and B always move as a pair:

* **Drag either marker time** (Info Area or waveform line) → both markers move together, **keeping the same interval**.
* **Type a time directly** → the other marker shifts to preserve the interval.
* Press <img src="icons/rew.png" width="20"> **Rewind** / <img src="icons/ff.png" width="20"> **Fast-Forward** → the entire A-B region shifts by the Rew/FF distance.

> 💡 This lets you keep a fixed "2-measure window" and slide it forward through the song step by step.
> 💡 If a move would take the region outside the file, it is rejected and the original position is preserved.
> 💡 AB Repeat and Ear Mode cannot both be ON at the same time. Turning one ON automatically turns the other OFF.

**■ Turning Ear Mode OFF**
Click the <img src="icons/ear.png" width="20"> icon again to deactivate Ear Mode. The blinking stops.

---

### Step 7: Spectrum Analyzer and Filter

The horizontal band between the Info Area and the Waveform Area provides **frequency visualization** and **filter control** (not available in Game Mode).

**■ Reading the spectrum analyzer**
During playback, **15 bars** appear in real time showing how much of each frequency range is present. The labels **25, 40, 63, 100, 160, 250, 400, 630, 1K, 1.6K, 2.5K, 4K, 6.3K, 10K, 16K** (Hz) mark each band.

**■ Applying a filter (only while hovering)**

1. **Hover over the spectrum analyzer band** to enter filter-control mode.
2. **Drag left/right over the band** to define the passband. For example, dragging from "63" to "1K" creates a bandpass filter that passes only that range.
3. Release to confirm the **passband**.

![Filter in use](icons/Filter_Capture.png)

> 💡 Outside the passband, attenuation is **−24 dB per octave** (a gradual rolloff, not a hard cutoff).
> 💡 If the **left edge of the range includes the lowest band ("25")**, it becomes **lowpass only** (no low-end attenuation).
> 💡 If the **right edge includes the highest band ("16K")**, it becomes **highpass only**.
> 💡 While a filter is active, hovering shows a **yellow line** over the spectrum indicating the approximate gain curve.

**■ Removing the filter**
**Right-click** anywhere in the spectrum analyzer band to remove the filter and restore full-range audio. The <img src="icons/reset.png" width="20"> **Reset All** button (or the **R** key) also removes the filter.

> 💡 Filter settings are **saved per file**, just like markers and speed. The same filter is restored next time you open that file.

---

<div style="page-break-before: always;"></div>

## 6. Game Mode (NSF, SPC, GBS)

"Morokoshi Time" supports three game music formats: NSF (NES/Famicom), SPC (SNES/Super Famicom), and GBS (Game Boy). When one of these files is open, the spectrum analyzer area switches to the **Game Panel**.

![Game Mode main screen](icons/GameMode_Capture.png)

### Game Panel Layout

The Game Panel has two rows.

**Top row: Track Navigation**

| Item | Description |
| :---------------------- | :-------------------------------------------------------- |
| **&lt;** button | Previous track |
| **Track number** | Current track number. Editable by drag, wheel, or double-click.<br>Hold Shift while dragging/scrolling to move in 10-track steps. |
| **&gt;** button | Next track |
| **/XXX** | Total number of tracks in the file (when more than one). |
| **Title display** | Shows game title and/or current track title (NSFe and m3u-tagged SPC/GBS only). |

**Bottom row: Channel ON/OFF Buttons**

Each audio channel is shown as a button. The number of channels depends on the format:

| Format | Channels |
| :--- | :--- |
| NSF (NES/Famicom) | Up to 13 (5 base + expansion audio) |
| SPC (SNES/Super Famicom) | 8 (fixed) |
| GBS (Game Boy) | 4 (fixed) |

* **Greyed-out buttons**: channels not used by the current track.
* **ON (yellow border)**: channel is included in playback.
* **OFF (dim display)**: channel is muted.

**Channel controls:**

| Action | Result |
| :---------------------- | :-------------------------------------------------------- |
| **Click** | Solo that channel (this channel ON, all others OFF) |
| **Shift+click** | Toggle that channel ON/OFF |
| **Right-click** | Reset all channels (all active channels set to ON) |

### Opening Files

**Single file**: Use the standard <img src="icons/open.png" width="20"> **Open File** button.
**ZIP file**: Select a ZIP directly; the app automatically recognizes game music files inside. A ZIP with multiple SPC files lets you switch between tracks.
**Folder drag & drop**: Drop a folder onto the window to batch-recognize all game music files (NSF/SPC/GBS) inside. You can also **hold Shift and click** <img src="icons/open.png" width="20"> **Open File** to open a folder-selection dialog.

### Extending Total Playback Time (Looping Tracks)

Most game music loops indefinitely, so the end cannot be detected automatically.

* **Tracks with a natural end**: Total time is confirmed automatically, like a normal file.
* **Looping tracks (no natural end)**: The **Total Time display blinks red**. The default time is 1 minute for NSF/GBS and 2 minutes for SPC (SPC files with embedded loop data are set automatically).

To extend the playback time of a looping track:

1. **Drag up/down on the blinking red Total Time display**, or scroll the mouse wheel.
2. Additional audio is decoded in real time, extending the waveform.
3. If a natural end is detected after extension, the blinking stops and the time is confirmed.

> 💡 Total time settings are saved per track, just like all other session data.

### Session Saving (All Tracks)

When an NSF/SPC/GBS file is closed, the state of **all tracks opened during the session** is saved individually.

The next time you open the same file:

* The last active track is automatically selected.
* Each track's **playback position, A/B markers, and channel ON/OFF settings** are individually restored.

### NSF Expansion Audio

NSF files support the following expansion audio chips:

| Chip | Description |
| :---------------------- | :-------------------------------------------------------- |
| **VRC6** | Konami. Two additional pulse waves + one sawtooth wave (3 ch total). |
| **VRC7** | Konami FM synthesis. 6 channels. |
| **FDS** | Famicom Disk System audio. 1 channel. |
| **MMC5** | Two additional pulse waves + PCM (3 ch total). |
| **Namco163 (N163)** | Namco wavetable synthesis. Up to 8 channels. |
| **Sunsoft 5B** | Sunsoft FM synthesis (YM2149-based). 3 channels. |

---

<div style="page-break-before: always;"></div>

## 7. Known Issues and Limitations

| Issue | Details |
| :---------------------- | :--------------------------------------------------------------- |
| **False channel detection** | For certain game music files, some channels may be incorrectly identified as "in use" and not greyed out properly. These can be manually turned OFF. |
| **No spectrum analyzer in Game Mode** | The spectrum analyzer and filter are unavailable while an NSF/SPC/GBS file is open. |
| **Tempo detection accuracy** | Tempo detection uses autocorrelation and is an estimate. It may return incorrect values for songs with complex rhythms or non-constant tempos. |

---

<div style="page-break-before: always;"></div>

## 8. Shortcuts

In addition to standard shortcuts, "Morokoshi Time" provides **hidden numpad shortcuts** that let you control almost everything with one hand. The numpad layout directly mirrors the icon arrangement on the right side of the screen — for example, the 3rd row (**A (Go), Ear Mode, B (Go)**) maps to numpad **4, 5, 6**.

| Main Key | Numpad | Function |
| :-------------------- | :-------------------- | :--------------------------------------------------------------- |
| **Space** | **0** | Play / Pause |
| **←** | **1** | Rewind |
| **Shift+←** | **Enter+1** | Previous track (Game Mode only) |
| **↓** | **2** | Toggle AB Repeat |
| **→** | **3** | Fast-forward |
| **Shift+→** | **Enter+3** | Next track (Game Mode only) |
| **A** | **4** | Go to A marker |
| **Shift+A** | **Enter+4** | Set A marker |
| **↑** | **5** | Toggle Ear Mode |
| **B** | **6** | Go to B marker |
| **Shift+B** | **Enter+6** | Set B marker |
| **O** | **7** | Open file |
| **T** | **8** | Detect tempo |
| **R** | **9** | Reset all |
| **Shift+R** | **Enter+9** | Clear cache |
| **H** | **/** (slash) | Help (open user manual) |
| **Z** | **\*** (asterisk) | Zoom (toggle display scaling) |
| **1** – **\\** (top row) | (none) | Game Mode: solo that channel (this ch ON, all others OFF) |
| **Shift+1 – \\** | (none) | Game Mode: toggle that channel ON/OFF |
| **,** | (none) | Previous track (Game Mode only) |
| **Shift+,** | (none) | Go back 10 tracks (Game Mode only) |
| **.** | (none) | Next track (Game Mode only) |
| **Shift+.** | (none) | Go forward 10 tracks (Game Mode only) |

> 💡 For numpad Enter combinations: press numpad Enter first, then press the second key within 1.5 seconds.  
> 💡 **Shortcuts are disabled while typing in a text field** — entering a value will not accidentally trigger shortcuts.  
> 💡 **Key layout note**: On a US keyboard, the top-row keys are `1`–`\` (`=` and `\` for channels 12–13). On a JIS keyboard, those keys are `^` and `¥`. The app handles both layouts automatically.

---

<div style="page-break-before: always;"></div>

## 9. Afterword

Thank you for finding **"Morokoshi Time"** among so many media players!

As a developer, I have spent years transcribing a huge number of songs — both professionally and as a hobby. But no matter how many popular media players I tried, there was always that **intense frustration** that came with transcription work:

* **"I want to jump by measures, not seconds!"**
* **"I want to slide the A-B loop window forward and backward while keeping the same length!"**
* **"Why can't it remember my playback position between sessions?"**
* **"Video files only seek to keyframes — I want to seek anywhere, smoothly!"**
* **"I just want to hear the audio, but the video window is always in the way!"**
* **"The original pitch and my instrument are slightly off — I need a fine-tune control!"**

"There has to be a better way — a player truly built for transcription" —
I built this app from scratch to answer every one of those frustrations.
That is **Morokoshi Time**.

### 🌽 Aside: why "Morokoshi Time"?

The name may seem unrelated to music, but there's a little story behind it.

A while ago, I transcribed a retro game piece on piano and posted the video on YouTube. Someone from Hokkaido (Japan's northernmost island, famous for its sweet corn) reached out asking for the sheet music, and I sent it free of charge. A few days later, a large box of **beautiful, fresh corn on the cob** arrived as a thank-you.

It was genuinely delicious — and from that moment, my brain forged a happy association: **"transcribing hard music = getting delicious corn."**

Before long, those focused, immersive transcription sessions became what I affectionately call **"Morokoshi Time"** — "corn time."

This app grew out of that passion — and a dash of playfulness.

I hope "Morokoshi Time" makes your transcription sessions — and your music creation — more comfortable and more rewarding. 🌽

---

**Morokoshi Time v1.6.0**
*Created by Ike-san*
