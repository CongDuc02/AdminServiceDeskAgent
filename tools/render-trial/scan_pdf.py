"""Quét một PDF trước khi commit: host, khoá, định danh. In TÊN mẫu/biến khớp và số lần — không in giá trị khớp của biến môi trường.

Dùng: python scan_pdf.py <pdf>   (chạy trong container với --env-file .env để so với giá trị biến môi trường — chỉ in tên biến)
"""
import os
import re
import subprocess
import sys
import zlib

path = sys.argv[1]
raw = open(path, "rb").read()

# 1) mọi luồng nén (Flate) giải ra; 2) text trích bằng pdftotext; 3) XMP/Info bằng pdfinfo -meta
blobs = {"raw": raw}
for i, m in enumerate(re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL)):
    try:
        blobs[f"stream{i}"] = zlib.decompress(m.group(1))
    except Exception:  # noqa: BLE001 — luồng không nén hay là font/ảnh
        blobs[f"stream{i}"] = m.group(1)
blobs["pdftotext"] = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True).stdout
blobs["pdfinfo_meta"] = subprocess.run(["pdfinfo", "-meta", "-enc", "UTF-8", path], capture_output=True).stdout + subprocess.run(["pdfinfo", "-enc", "UTF-8", path], capture_output=True).stdout

PATTERNS = {
    "url": rb"https?://[^\s\"'<>)]+",
    "host_tld": rb"\b[a-z0-9][a-z0-9-]{1,40}\.(?:com|net|org|io|vn|dev|app|ai|cloud|local|test|internal)\b",
    "ipv4": rb"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "email": rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "uuid": rb"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    "groq_key": rb"gsk_[A-Za-z0-9]{10,}",
    "generic_key": rb"\b(?:sk|pk|AKIA|ghp|xox[bap])[-_A-Za-z0-9]{16,}",
    "dsn": rb"postgres(?:ql)?://",
    "long_hex": rb"\b[0-9a-f]{32,}\b",
    "provider_words": rb"(?i)groq|openai|onrender|render\.com|seaweed|bo19-trial|amazonaws|localhost|127\.0\.0\.1",
    "path_win": rb"[A-Za-z]:\\\\[^\s]{3,}|/home/[a-z0-9_]+|/Users/[A-Za-z0-9_]+|C:/Users",
}
hits = {}
for label, blob in blobs.items():
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, blob):
            hits.setdefault(name, []).append((label, m.group(0)[:60]))

print("Luồng đã quét:", len(blobs))
for name in PATTERNS:
    found = hits.get(name, [])
    kinds = sorted({h[0] if h[0] in ("raw", "pdftotext", "pdfinfo_meta") else "stream" for h in found})
    print(f"  {name:15s} {len(found):3d} khớp {kinds}")

# giá trị biến môi trường (>= 6 ký tự) có trong PDF không — chỉ in TÊN biến
leaks = []
for name, value in os.environ.items():
    if len(value) >= 6 and name not in ("PATH", "HOME", "PWD", "LANG", "HOSTNAME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING"):
        needle = value.encode("utf-8")
        if any(needle in b for b in blobs.values()):
            leaks.append(name)
print("Biến môi trường có giá trị nằm trong PDF:", leaks or "không")

# in giá trị khớp của các mẫu KHÔNG phải khoá/định danh bí mật để người đọc tự xét (host_tld, url, email, uuid, ipv4)
for name in ("url", "host_tld", "email", "uuid", "ipv4", "long_hex", "provider_words", "path_win"):
    uniq = sorted({h[1].decode("utf-8", "replace") for h in hits.get(name, [])})
    if uniq:
        print(f"  [{name}] giá trị khớp:", uniq[:10])
