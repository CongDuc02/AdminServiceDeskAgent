# PyJWT 2.15.0 và RFC 7518 — độ dài tối thiểu của khoá HMAC cho `HS256`

- **Ngày lấy:** 2026-10-05. **Cách lấy:** `curl -sS -L` — không công cụ tóm tắt web (`CLAUDE.md`, mục Luật thao tác). Excerpt dưới đây chép bằng script từ file đã tải, không gõ lại; số dòng là dòng của văn bản đã bỏ thẻ HTML.
- **Dùng cho:** A-088 — độ dài tối thiểu của `BO19_SESSION_SECRET` (bước kiểm khởi động #12); ADR-028 (thư viện `PyJWT`, thuật toán ký HMAC).
- **Phiên bản khớp lock:** `PyJWT==2.15.0` (`backend/requirements-linux.lock`). Trang `.../en/2.15.0/...` là trang của đúng bản này.
- **Vì sao có cả RFC:** trang của PyJWT dẫn "RFC 7518 Section 3.2" làm căn cứ cho con số — PO yêu cầu lấy cả RFC (2026-10-05).

## 0. Nguồn đã tải

| # | URL | Kích thước (byte) | sha256 |
|---|---|---|---|
| N1 | `https://pyjwt.readthedocs.io/en/2.15.0/algorithms.html` | 13429 | `7c40715df2332176962a1b09603b619a334ac9c7ccd4045c74c643d15a4fa69d` |
| N2 | `https://pyjwt.readthedocs.io/en/2.15.0/usage.html` | 86514 | `483d7a2b33bc22d8662a3272d1e7dde6cad48d7b6c8872c4536420b9bfa7a29d` |
| N3 | `https://pyjwt.readthedocs.io/en/2.15.0/changelog.html` | 113375 | `a12c1e99eea6b8db8efe5dcbcfbf0374b97e433e16f96ed4926e375c2350a09a` |
| N4 | `https://www.rfc-editor.org/rfc/rfc7518.txt` | 155905 | `9a9ae524b09ea700ad3f189bac115df95ba69af84b26ffdbe3cdfb8d2152b1fc` |

Không commit nguyên file (trang HTML lớn, RFC 150 KB) — chỉ sha256 và các đoạn chép nguyên văn dưới đây.

## 1. N1 — bảng độ dài tối thiểu theo thuật toán, `algorithms.html`, dòng 111–145

```text
Minimum Key Length Requirements
PyJWT enforces minimum key lengths per industry standards. Keys below these
minimums will trigger an InsecureKeyLengthWarning by default, or raise
InvalidKeyError if enforce_minimum_key_length is enabled.


Algorithm
Minimum Key Length
Standard



HS256
32 bytes (256 bits)
RFC 7518 Section 3.2

HS384
48 bytes (384 bits)
RFC 7518 Section 3.2

HS512
64 bytes (512 bits)
RFC 7518 Section 3.2

RS256/384/512
2048 bits
NIST SP 800-131A

PS256/384/512
2048 bits
NIST SP 800-131A



See Key Length Validation for configuration details.
```

## 2. N2 — Key Length Validation, `usage.html`, dòng 468–496

```text
Key Length Validation
PyJWT validates that cryptographic keys meet minimum recommended lengths.
By default, a warning (InsecureKeyLengthWarning) is emitted when a key
is too short. You can configure PyJWT to raise an InvalidKeyError instead.
The minimum key lengths are:

HMAC (HS256, HS384, HS512): Key must be at least as long as the hash
output (32, 48, or 64 bytes respectively), per RFC 7518 Section 3.2.
RSA (RS256, RS384, RS512, PS256, PS384, PS512): Key must be at least
2048 bits, per NIST SP 800-131A.

By default, short keys produce an InsecureKeyLengthWarning:
>>> import jwt
>>> encoded = jwt.encode({"some": "payload"}, "short", algorithm="HS256")


To enforce minimum key lengths (raise InvalidKeyError on short keys),
pass enforce_minimum_key_length=True in the options when creating a
PyJWT or PyJWS instance:
>>> strict_jwt = jwt.PyJWT(options={"enforce_minimum_key_length": True})
>>> try:
...     strict_jwt.encode({"some": "payload"}, "short", algorithm="HS256")
... except jwt.InvalidKeyError:
...     print("key too short")
...
key too short


To suppress the warning without enforcing, use Python’s standard
```

## 3. N3 — `changelog.html`: hai dòng liên quan tới khoá HMAC, dòng 523–527 và 440–446

```text
Add minimum key length validation for HMAC and RSA keys (CWE-326).
Warns by default via InsecureKeyLengthWarning when keys are below
minimum recommended lengths per RFC 7518 Section 3.2 (HMAC) and
NIST SP 800-131A (RSA). Pass enforce_minimum_key_length=True in
options to PyJWT or PyJWS to raise InvalidKeyError instead.
...

Fixed

Reject empty HMAC keys outright in HMACAlgorithm.prepare_key with
InvalidKeyError instead of accepting them with only a warning.
Thanks to @SnailSploit and @spartan8806 for independently flagging the
footgun.
```

## 4. N4 — RFC 7518, mục 3.2, dòng 343–357 của bản `.txt`

```text
3.2.  HMAC with SHA-2 Functions

   Hash-based Message Authentication Codes (HMACs) enable one to use a
   secret plus a cryptographic hash function to generate a MAC.  This
   can be used to demonstrate that whoever generated the MAC was in
   possession of the MAC key.  The algorithm for implementing and
   validating HMACs is provided in RFC 2104 [RFC2104].

   A key of the same size as the hash output (for instance, 256 bits for
   "HS256") or larger MUST be used with this algorithm.  (This
   requirement is based on Section 5.3.4 (Security Effect of the HMAC
   Key) of NIST SP 800-117 [NIST.800-107], which states that the
   effective security strength is the minimum of the security strength
   of the key and two times the size of the internal hash value.)

```

## 5. Điều rút ra — và điều **không** rút ra

- Với `HS256`, khoá HMAC **không được ngắn hơn 32 byte (256 bit)**: N1 (bảng) và N4 (câu "A key of the same size as the hash output (for instance, 256 bits for "HS256") or larger MUST be used"). `HS384` là 48 byte, `HS512` là 64 byte (N1).
- **Đơn vị là byte**, không phải ký tự: một secret có ký tự ngoài ASCII dài hơn số ký tự của nó khi mã hoá UTF-8. N1 ghi "32 bytes (256 bits)".
- Mặc định PyJWT **chỉ cảnh báo** (`InsecureKeyLengthWarning`) khi khoá ngắn; muốn từ chối thì đặt `enforce_minimum_key_length=True` trong `options` của `PyJWT` (N2). Changelog (N3) ghi thêm: khoá HMAC rỗng bị từ chối hẳn ở `prepare_key`.
- **Không rút ra được từ các nguồn này:** độ ngẫu nhiên (entropy) của secret. Độ dài byte là điều kiện cần — một chuỗi 32 ký tự lặp vẫn qua kiểm độ dài. Các nguồn không nêu ngưỡng entropy; thiết kế **không** đặt ngưỡng nào ngoài độ dài.
- **Không rút ra được:** thuật toán ký nào là "đúng" cho dự án. Đó là quyết định ở ADR-028 (ghi tên thuật toán ở B3).
