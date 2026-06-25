from PIL import Image

# 2つのPNG画像を読み込む
img_128 = Image.open('もろこしアイコン.png')
img_32 = Image.open('もろこしアイコンs.png')

# 正しい書き方：
# ベースとなるimg_128のsaveメソッドを使い、
# append_imagesに「一緒にまとめる別サイズの画像リスト」を渡します。
img_128.save(
    'morokoshi.ico', 
    format='ICO', 
    append_images=[img_32],  # ←ここでimg_32を確実に追加します
    sizes=[(128, 128), (32, 32)]
)

