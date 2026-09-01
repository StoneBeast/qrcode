# -*- coding: utf-8 -*-
"""生成应用图标 app.ico：QR 码风格的圆角方块 + 扫描线。"""
import os

from PIL import Image, ImageDraw

SIZE = 256
S = SIZE // 8  # 模块边长（8x8 网格）

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 白色圆角底
d.rounded_rectangle([4, 4, SIZE - 4, SIZE - 4], radius=44, fill=(255, 255, 255, 255),
                    outline=(210, 214, 220, 255), width=3)

GREEN = (10, 143, 91, 255)
DARK = (28, 30, 34, 255)


def finder(cx, cy):
    """左上/右上/左下三个定位角。"""
    x, y = cx * S, cy * S
    d.rounded_rectangle([x, y, x + 3 * S, y + 3 * S], radius=S // 2,
                        outline=DARK, width=S // 2)
    d.rounded_rectangle([x + S, y + S, x + 2 * S, y + 2 * S], radius=S // 4,
                        fill=DARK)


finder(1, 1)
finder(4, 1)
finder(1, 4)

# 右下角数据点
for (cx, cy) in [(5, 4), (6, 4), (5, 5), (6, 5), (4, 5), (5, 6), (6, 6)]:
    d.rectangle([cx * S + 1, cy * S + 1, (cx + 1) * S - 1, (cy + 1) * S - 1], fill=DARK)

# 扫描线
d.rounded_rectangle([S, 3 * S + 4, 7 * S, 3 * S + 14], radius=5, fill=GREEN)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("图标已生成:", out)
