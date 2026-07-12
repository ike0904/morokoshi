・C:\Users\ike09\.claude\claude.md 初回起動時と更新あり時は必ず読むこと。
・docsフォルダに拡張子mdの仕様書がある。初回起動時と更新あり時は必ず読むこと。
・docs\notes.md にアプリ固有の技術メモがある。初回起動時と更新あり時は必ず読むこと。
・mdファイルの内容を書き換える時、元のファイルを必ず「.md.bak」で残すこと。「.md.bak」の上書きは許可する。もちろん、このmdファイルも含む。


docs\morokoshi_manual.md　およびPDF（ファイル名は「{アプリ名}_manual.md(pdf)」で統一）
・マニュアルは日本語 → 英語の順で1ファイルにまとめる。
・PDF生成: python docs\gen_pdf.py（pandoc + Chrome headless）
・スタイル: docs\manual.css（ikePon と共通テンプレートで統一済み）
