# -*- coding: utf-8 -*-
"""Japanese UI texts. Key = the English text in morokoshi.py ({0}, {1}, ... = parts set at run time).

Parameter names shown on the main screen (Tempo, Key, Fine, Speed, Beat, Bar, A<->B, Rew/FF ...)
are kept in English, because the manual uses these names.
"""

STRINGS = {
    # ---------------------------------------------------------------- icons (main screen)
    "Help [H]\nR-Click [Alt+H]: Language": "ヘルプ [H]\n右クリック [Alt+H]: 言語 (Language)",
    "Save [S]": "保存 [S]",
    "Open[O]\nShift: Folder\nR-Click [Alt+O]: History": "開く [O]\nShift+クリック: フォルダを開く\n右クリック [Alt+O]: 履歴",
    "Play/Pause [Space]\nShift: Back to Start": "再生 / 一時停止 [Space]\nShift+クリック: 先頭に戻る",
    "ffmpeg: not found (will auto-download on first file open)":
        "ffmpeg: 見つかりません（最初にファイルを開いたときに自動でダウンロードします）",
    "ffmpeg (PATH): {0}": "ffmpeg（PATH 上）: {0}",
    "ffmpeg: {0}": "ffmpeg の場所: {0}",
    "Tempo detection [T]\nShift: Tap tempo": "テンポ検出 [T]\nShift+クリック: タップテンポ",
    "Reset[R]\nShift: Clear Cache": "リセット [R]\nShift+クリック: キャッシュクリア",
    "Ear mode [↑]": "Ear Mode（耳コピモード）[↑]",
    "Go to marker {0} [{1}]\nShift: Set marker": "マーカー {0} へ移動 [{1}]\nShift+クリック: マーカーを設定",
    "Rew[←]\nShift: Prev track (Game mode)": "巻き戻し [←]\nShift+クリック: 前の曲（ゲームモード）",
    "AB repeat [↓]": "AB リピート [↓]",
    "FF[→]\nShift: Next track (Game mode)": "早送り [→]\nShift+クリック: 次の曲（ゲームモード）",
    "Language": "言語",
    "Language: {0}": "言語: {0}",

    # ---------------------------------------------------------------- tooltips (main screen)
    "Rew/FF step\n1-Click: Copy A<->B duration → recalc Tempo\n2-Click: Edit(sec)\nDrag↑↓/Wheel: +/-0.1s\n"
    "Shift+Drag↑↓/Wheel: +/-1.0s\nR-Click: Reset Tempo/Beat/Bar\n→Tempo is recalculated":
        "Rew/FF の移動量\nクリック: A<->B の長さをコピー → Tempo を再計算\nダブルクリック: 編集（秒）\n"
        "ドラッグ↑↓/ホイール: ±0.1秒\nShift+ドラッグ↑↓/ホイール: ±1.0秒\n右クリック: Tempo/Beat/Bar をリセット\n→ Tempo が再計算されます",
    "A<->B duration\n2-Click: Edit(sec)\nDrag↑↓/Wheel: +/-0.1s\nShift+Drag↑↓/Wheel: +/-1.0s\nR-Click: Reset A & B":
        "A<->B の長さ\nダブルクリック: 編集（秒）\nドラッグ↑↓/ホイール: ±0.1秒\nShift+ドラッグ↑↓/ホイール: ±1.0秒\n"
        "右クリック: A と B をリセット",
    "{0}\n2-Click: Edit\nDrag↑↓/Wheel: +/-1\nR-Click: Reset":
        "{0}\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±1\n右クリック: リセット",
    "{0}\n1-Click: Tempo Detection\n2-Click: Edit\nDrag↑↓/Wheel: +/-0.1\nShift+Drag↑↓/Wheel: +/-1.0\nR-Click: Reset":
        "{0}\nクリック: テンポ検出\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±0.1\nShift+ドラッグ↑↓/ホイール: ±1.0\n右クリック: リセット",
    "{0}\n2-Click: Edit\nDrag↑↓/Wheel: +/-0.1\nShift+Drag↑↓/Wheel: +/-1.0\nR-Click: Reset":
        "{0}\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±0.1\nShift+ドラッグ↑↓/ホイール: ±1.0\n右クリック: リセット",
    "Key\n2-Click: Edit\nDrag↑↓/Wheel: +/-1\nShift+Drag↑↓/Wheel: +/-12\nR-Click: Reset":
        "Key（移調）\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±1\nShift+ドラッグ↑↓/ホイール: ±12\n右クリック: リセット",
    "Fine\n2-Click: Edit\nDrag↑↓/Wheel: +/-0.01\nShift+Drag↑↓/Wheel: +/-0.1\nR-Click: Reset":
        "Fine（キー微調整）\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±0.01\nShift+ドラッグ↑↓/ホイール: ±0.1\n右クリック: リセット",
    "Speed\n2-Click: Edit\nDrag↑↓/Wheel: step\nR-Click: Reset":
        "Speed（再生速度）\nダブルクリック: 編集\nドラッグ↑↓/ホイール: 段階的に変更\n右クリック: リセット",
    "Waveform\nClick: Seek\nDrag↑↓/Wheel: Zoom\nShift+Wheel: Scroll\nDrag←→: Set A-B range\n2-click: Set marker\n"
    "2-click on A/B: Reset\nR-Click: Reset A & B":
        "波形\nクリック: 再生位置を移動\nドラッグ↑↓/ホイール: 拡大・縮小\nShift+ホイール: スクロール\n"
        "ドラッグ←→: A-B 区間を設定\nダブルクリック: マーカーを設定\nA/B 上でダブルクリック: リセット\n右クリック: A と B をリセット",
    "Drag←→: Scroll\nDrag edge ←→: Zoom": "ドラッグ←→: スクロール\n端をドラッグ←→: 拡大・縮小",
    "Current time\n2-Click: Edit\nDrag↑↓/Wheel: +/-0.1s\nShift+Drag↑↓/Wheel: +/-1.0s\nR-Click: Back to Start":
        "現在の再生位置\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±0.1秒\nShift+ドラッグ↑↓/ホイール: ±1.0秒\n右クリック: 先頭に戻る",
    "Total time\n(NSF/GBS)\nDrag↑↓/Wheel: change duration\nR-Click: Back to initial time":
        "総再生時間\n（NSF/GBS）\nドラッグ↑↓/ホイール: 長さを変更\n右クリック: 最初の長さに戻す",
    "Volume\nDrag←→: change\nR-Click: 100%": "音量\nドラッグ←→: 変更\n右クリック: 100%",
    "Volume\n2-Click: Edit\nDrag↑↓/Wheel: +/-1\nShift+Drag↑↓/Wheel: +/-10\nR-Click: 100%":
        "音量\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±1\nShift+ドラッグ↑↓/ホイール: ±10\n右クリック: 100%",
    "Marker {0}\nClick: Set\n2-Click: Edit\nDrag↑↓/Wheel: +/-0.1s\nShift+Drag↑↓/Wheel: +/-1.0s\nR-Click: Clear":
        "マーカー {0}\nクリック: 現在位置を設定\nダブルクリック: 編集\nドラッグ↑↓/ホイール: ±0.1秒\n"
        "Shift+ドラッグ↑↓/ホイール: ±1.0秒\n右クリック: 消去",
    "Spectrum analyzer\nFilter (HPF/LPF, -24dB/Oct)\nDrag←→:Select pass band\nR-Click:Reset (no filter)":
        "スペクトラムアナライザー\nフィルター（HPF/LPF、-24dB/Oct）\nドラッグ←→: 通過帯域を選択\n右クリック: リセット（フィルターなし）",
    "Spectrum Analyzer\n{0}": "スペクトラムアナライザー\n{0}",
    "Filter reset (no filter)": "フィルターをリセット（フィルターなし）",

    # ---------------------------------------------------------------- game mode panels
    "Channel on/off [{0}]\nShift: Solo\nR-Click: Reset": "チャンネル ON/OFF [{0}]\nShift+クリック: ソロ\n右クリック: リセット",
    "Track number\nDrag↑↓/Wheel: change\nShift+Drag↑↓/Wheel: ×10\n2-Click: Edit":
        "曲番号\nドラッグ↑↓/ホイール: 変更\nShift+ドラッグ↑↓/ホイール: ×10\nダブルクリック: 編集",
    "Prev track [,]\nShift: ×10": "前の曲 [,]\nShift+クリック: 10曲前",
    "Next track [.]\nShift: ×10": "次の曲 [.]\nShift+クリック: 10曲先",
    "Total tracks": "総曲数",
    "Game title": "ゲームタイトル",
    "Previous track\nKey: [,] or Shift+[←]": "前の曲\nキー: [,] または Shift+[←]",
    "Next track\nKey: [.] or Shift+[→]": "次の曲\nキー: [.] または Shift+[→]",
    "SPC title": "SPC タイトル",

    # ---------------------------------------------------------------- dialogs
    "No history": "履歴なし",
    "Open Media File": "メディアファイルを開く",
    "Open Folder": "フォルダを開く",
    "Save Audio": "保存",
    "Clear cache": "キャッシュクリア",
    "This will discard the current track, delete the cache folder, and restart the app.\nAre you sure?":
        "現在の曲を閉じ、キャッシュフォルダを削除して、アプリを再起動します。\nよろしいですか？",
    "Drop a file or click Open to load": "ファイルをドロップするか、開くアイコンで読み込んでください",

    # ---------------------------------------------------------------- MIDI options
    "MIDI options": "MIDI オプション",
    "Loops": "ループ回数",
    "How many times to write the loop body\n0: no loop detection (convert the full max seconds)\nWheel: change":
        "ループ部分を何回書き出すか\n0: ループを探さず、最大秒数の長さをそのまま変換\nホイール: 変更",
    "Max seconds": "最大秒数",
    "Max length to emulate (seconds)\nStops automatically when a loop or the song end is found\nWheel: change":
        "エミュレートする最大の長さ（秒）\nループか曲の終わりが見つかると自動的に止まります\nホイール: 変更",
    "Tempo": "テンポ",
    "Auto: detected tempo\nHalf / Double: use when the tempo comes out doubled or halved":
        "自動: 検出したテンポ\n半分 / 2倍: テンポが倍・半分に検出されたときに指定",
    "Triplets": "3連符",
    "Write triplet-feel songs as 3 notes per beat\nAuto: detect / On: always / Off: never":
        "3 連ノリの曲を「1 拍 = 3 音」で出力するか\n自動: 検出 / オン: 常に / オフ: しない",
    "Pitch-drop drums": "下降音ドラム（半音）",
    "Short notes that keep falling by at least this many semitones\n(triangle kicks, pulse toms) go to their own drum tracks\n"
    "(MIDI ch stays 1-3)\n0: off\nWheel: change":
        "鳴り始めから、この半音数以上下がり続ける短い音\n（三角波のキック・矩形波のタム）をドラム用トラックに分けます（MIDI ch は 1〜3 のまま）\n"
        "0: 分けない\nホイール: 変更",
    "Keep reverb tails": "リバーブ余韻を残す",
    "Include reverb tails in the note length": "小さな音量で鳴らし続ける余韻も、音の長さに含めます",
    "Quantize": "クオンタイズする",
    "Snap notes to the detected beat grid\nOff: keep the exact timing (the tempo is still detected)":
        "音符を検出した拍のグリッドに合わせます\nオフ: 実際のタイミングのまま（テンポは検出します）",
    "Detect odd meters": "変拍子を検出する",
    "Find bars other than 4/4 (6/8, 9/8, 5/8 ...) in the loop\nfrom the repeating rhythm\nOff: no odd meters":
        "ループ内の 4/4 以外の小節（6/8・9/8・5/8 など）を\nリズムの繰り返しから求めます\nオフ: 変拍子を検出しない",
    "Defaults": "既定値に戻す",
    "OK": "OK",
    "Cancel": "キャンセル",
    "Auto": "自動",
    "Half": "半分",
    "Double": "2倍",
    "On": "オン",
    "Off": "オフ",

    # ---------------------------------------------------------------- status messages
    "Invalid number": "数値が正しくありません",
    "Invalid time": "時間が正しくありません",
    "Invalid value": "値が正しくありません",
    "Invalid Beat/Bar": "Beat/Bar が正しくありません",
    "Time out of range": "時間が範囲外です",
    "Markers updated": "マーカーを更新しました",
    "Marker {0} = {1}": "マーカー {0} = {1}",
    "Marker {0} reset": "マーカー {0} をリセットしました",
    "Marker {0} set": "マーカー {0} を設定しました",
    "Marker out of range": "マーカーが範囲外です",
    "A and B cannot be equal": "A と B を同じ位置にはできません",
    "Tempo/Beat/Bar Reset": "Tempo/Beat/Bar をリセットしました",
    "AB Repeat OFF": "AB リピート OFF",
    "AB Repeat ON": "AB リピート ON",
    "Ear Mode OFF": "Ear Mode OFF",
    "Ear Mode ON": "Ear Mode ON",
    "Duration must be positive": "長さは正の値にしてください",
    "Value must be positive": "値は正の値にしてください",
    "Set A marker first": "先に A マーカーを設定してください",
    "B must be after A": "B は A より後ろにしてください",
    "B out of range": "B が範囲外です",
    "Set A and B markers first": "先に A と B のマーカーを設定してください",
    "A and B markers are at the same position": "A と B のマーカーが同じ位置です",
    "Tempo out of range (30-300): {0}": "Tempo が範囲外です（30〜300）: {0}",
    "Load a file first": "先にファイルを読み込んでください",
    "Tap tempo: set Beat to 2 or more": "タップテンポ: Beat を 2 以上にしてください",
    "Tap tempo: {0} taps ({1} more...)": "タップテンポ: {0} 回（あと {1} 回…）",
    "Tap tempo: 1 tap ({0} more...)": "タップテンポ: 1 回（あと {0} 回…）",
    "Tap tempo: {0} BPM ({1} taps)": "タップテンポ: {0} BPM（{1} 回）",
    "Detecting tempo...": "テンポを検出中…",
    "Tempo detected: {0} BPM": "テンポを検出しました: {0} BPM",
    "Tempo detection failed": "テンポを検出できませんでした",
    "Reset to start [Shift+Space]": "先頭に戻りました [Shift+Space]",
    "Reset [R]": "リセットしました [R]",
    "morokoshi_manual.pdf not found": "morokoshi_manual.pdf が見つかりません",
    "Opening manual...": "マニュアルを開いています…",
    "Could not open manual": "マニュアルを開けませんでした",
    "No audio to save": "保存する音声がありません",
    "Saving in progress...": "保存中です…",
    "Saving...": "保存中…",
    "Saving... (converting)": "保存中…（変換中）",
    "Saved: {0}": "保存しました: {0}",
    "Save failed: {0}": "保存に失敗しました: {0}",
    "MIDI save cancelled": "MIDI の保存を中止しました",
    "Saving MIDI... {0}s (Esc: cancel)": "MIDI を保存中… {0}秒（Esc: 中止）",
    "Saved: {0} ({1}s)": "保存しました: {0}（{1}秒）",
    "MIDI save failed: {0}": "MIDI の保存に失敗しました: {0}",
    "Cancelling MIDI save...": "MIDI の保存を中止しています…",
    "Load failed: {0}": "読み込みに失敗しました: {0}",
    "Cannot shorten below current position": "現在の再生位置より短くはできません",
    "{0}: duration set to {1}": "{0}: 長さを {1} にしました",
    "{0} duration change failed: {1}": "{0} の長さの変更に失敗しました: {1}",
    "NSF: Loading track {0}...": "NSF: {0} 曲目を読み込み中…",
    "SPC: Loading track {0}...": "SPC: {0} 曲目を読み込み中…",
    "GBS: Loading track {0}...": "GBS: {0} 曲目を読み込み中…",
    "SPC: Track {0}": "SPC: {0} 曲目",
    "GBS: Track {0}": "GBS: {0} 曲目",
    "NSF track change failed: {0}": "NSF の曲の切り替えに失敗しました: {0}",
    "SPC track change failed: {0}": "SPC の曲の切り替えに失敗しました: {0}",
    "GBS track change failed: {0}": "GBS の曲の切り替えに失敗しました: {0}",
    "NSF ch render failed: {0}": "NSF のチャンネル切り替えに失敗しました: {0}",
    "SPC ch render failed: {0}": "SPC のチャンネル切り替えに失敗しました: {0}",
    "GBS ch render failed: {0}": "GBS のチャンネル切り替えに失敗しました: {0}",

    # ---------------------------------------------------------------- loading progress
    "Downloading ffmpeg... (~40MB, first time only)": "ffmpeg をダウンロード中…（約 40MB、初回のみ）",
    "Downloading ffmpeg... {0}%": "ffmpeg をダウンロード中… {0}%",
    "Extracting ffmpeg...": "ffmpeg を展開中…",
    "ffmpeg installed": "ffmpeg をインストールしました",
    "Converting...": "変換中…",
    "Loading...": "読み込み中…",
    "Done": "完了",
    "Loading NSF...": "NSF を読み込み中…",
    "Loading SPC...": "SPC を読み込み中…",
    "Loading GBS...": "GBS を読み込み中…",
    "Loading ZIP...": "ZIP を読み込み中…",
    "Loading GBS ZIP...": "GBS の ZIP を読み込み中…",
    "Loading folder...": "フォルダを読み込み中…",
    "Extracting NSF from ZIP...": "ZIP から NSF を取り出し中…",
    "SPC: reading metadata...": "SPC: 曲情報を読み込み中…",
    "SPC: rendering...": "SPC: 生成中…",
    "NSF: rendering track 1...": "NSF: 1 曲目を生成中…",
    "SPC: rendering track 1...": "SPC: 1 曲目を生成中…",
    "GBS: rendering track 1...": "GBS: 1 曲目を生成中…",
    "NSF: rendering track {0}...": "NSF: {0} 曲目を生成中…",
    "SPC: rendering track {0}...": "SPC: {0} 曲目を生成中…",
    "GBS: rendering track {0}...": "GBS: {0} 曲目を生成中…",
    "NSF: re-rendering with session channels...": "NSF: チャンネル設定を反映して再生成中…",
    "SPC: re-rendering with session channels...": "SPC: チャンネル設定を反映して再生成中…",
    "GBS: re-rendering with session channels...": "GBS: チャンネル設定を反映して再生成中…",
    "NSF: rendering {0}s→{1}s...": "NSF: {0}秒→{1}秒を生成中…",
    "SPC: rendering {0}s→{1}s...": "SPC: {0}秒→{1}秒を生成中…",
    "GBS: rendering {0}s→{1}s...": "GBS: {0}秒→{1}秒を生成中…",
    "NSF: detecting ch {0}/{1}...": "NSF: チャンネルを検出中 {0}/{1}…",
    "SPC: detecting ch {0}/{1}...": "SPC: チャンネルを検出中 {0}/{1}…",
    "GBS: detecting ch {0}/{1}...": "GBS: チャンネルを検出中 {0}/{1}…",
    "Convert error: {0}": "変換エラー: {0}",
    "Re-rendering{0}...": "再生成中{0}…",
}
