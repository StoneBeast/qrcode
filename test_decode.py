# -*- coding: utf-8 -*-
"""解码自测：对 test_data/ 里的图片跑 decode_image，校验结果。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qr_reader import decode_image  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")

EXPECT = {
    "url.png": "https://github.com/zxing-cpp/zxing-cpp",
    "text.png": "你好，世界！Hello QReader 123456",
    "wifi.png": "WIFI:T:WPA;S:MyHomeWiFi;P:pass1234;;",
    "tiny.png": "tiny-qr-test",
}


def main():
    ok = True
    for name, expected in EXPECT.items():
        path = os.path.join(BASE, name)
        results = decode_image(__import__("PIL.Image", fromlist=["Image"]).open(path))
        got = results[0]["text"] if results else None
        status = "OK " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"[{status}] {name}: {got!r} (format={results[0]['format'] if results else '-'})")
    print("全部通过" if ok else "存在失败用例")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
