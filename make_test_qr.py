# -*- coding: utf-8 -*-
"""生成测试二维码图片到 test_data/，用于验证解码功能。"""
import os
import sys

import zxingcpp
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
os.makedirs(OUT, exist_ok=True)

CASES = [
    ("url.png", "https://github.com/zxing-cpp/zxing-cpp"),
    ("text.png", "你好，世界！Hello QReader 123456"),
    ("wifi.png", "WIFI:T:WPA;S:MyHomeWiFi;P:pass1234;;"),
]


def to_pil(bm):
    """zxingcpp 生成的灰度位图（buffer 协议）转成 PIL Image。"""
    h, w = bm.shape[:2]
    return Image.frombuffer("L", (w, h), memoryview(bm), "raw", "L", 0, 1)


def main():
    bm = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, "probe")
    print("bitmap type:", type(bm), "attrs:", [a for a in dir(bm) if not a.startswith("_")])

    for name, text in CASES:
        bm = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, text,
                                    quiet_zone=6)
        img = to_pil(bm)
        # 放到白底画布上，模拟真实截图场景
        canvas = Image.new("RGB", (img.width + 80, img.height + 80), "white")
        canvas.paste(img, (40, 40))
        path = os.path.join(OUT, name)
        canvas.save(path)
        print("生成:", path, canvas.size)

    # 一张小尺寸二维码，测试放大重试逻辑
    bm = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, "tiny-qr-test", quiet_zone=4)
    img = to_pil(bm).resize((60, 60))
    path = os.path.join(OUT, "tiny.png")
    img.save(path)
    print("生成:", path, (60, 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
