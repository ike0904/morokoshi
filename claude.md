・C:\Users\ike09\.claude\claude.md 初回起動時と更新あり時は必ず読むこと。
・docsフォルダに拡張子mdの仕様書がある。初回起動時と更新あり時は必ず読むこと。
・このmdファイルに書いてある要望に対して、どんな作業をしたかを書き足して。作業していない場合も、そのむね書いて。
・このmdファイルに書いてない作業を行った場合（プロンプト直接指示など）も、作業内容をここに書いて。
・mdファイルの内容を書き換える時、元のファイルを必ず「.md.bak」で残すこと。「.md.bak」の上書きは許可する。もちろん、このmdファイルも含む。

上記内容は全プロジェクト共通。メモっておいて。


・SPCファイルはループ情報がファイル内に入ってしまっているので、間違えようがなかった。
申し訳ないけど、やっぱり総時間変更はできないように元に戻して。ツールチップも。
→【対応済み】SPC の _nsf_set_dur_editable を常に False に変更。
  ツールチップから "(NSF/SPC/GBS)" → "(NSF/GBS)" に修正。
  _dur_lbl_press / _dur_lbl_release / _dur_lbl_wheel の SPC ブランチを削除。

・アプリ立ち上げ後、タスクバーのアイコンが「とうもろこしマーク」になっていない。
E:\Users\takashi\Desktop\ClaudeCode\morokoshi\docs\icons　にある「もろこしアイコン.png（大きいアイコン）」と「もろこしアイコンs.png（小さいアイコン）」を使って、アイコンを作り直して。
→【対応済み】PIL で 256/128/64/48/32/16px の多サイズ ICO を再作成（icon/morokoshi.ico）。
  main() に SetCurrentProcessExplicitAppUserModelID('morokoshi.time') を追加し、
  win.setWindowIcon() も追加してタスクバーに確実に反映されるよう修正。

・マニュアルの改変履歴「更新履歴」に名称変更。表示個所も一番後ろにする。（E:\Users\takashi\Desktop\ClaudeCode\ikePon\docs　のマニュアルに合わせる）この仕様は全マニュアル共通。メモしておくこと。
今回はまだマニュアル更新対象ではないので、次回指示時に更新して。
→【未対応】次回マニュアル更新時に対応予定。


