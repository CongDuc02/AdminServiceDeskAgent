# Giấy phép font Tinos — bản gốc (cổng 1.6, A-058)

- **Lấy bằng `curl` ngày 2026-10-12** (giờ Việt Nam), không qua công cụ tóm tắt web.
- **File font và metadata:** `https://raw.githubusercontent.com/google/fonts/ba95515f1333efe9342c2ad988b9c2f6bef6dbad/ofl/tinos/<tên file>` — kho `google/fonts`, commit `ba95515f1333efe9342c2ad988b9c2f6bef6dbad` (commit mới nhất chạm `ofl/tinos` lúc lấy).
- **Giấy phép:** `https://raw.githubusercontent.com/googlefonts/tinos/3b4482a99b80ea5fc75f187b1be3120a3f5905b3/OFL.txt` — kho nguồn `googlefonts/tinos`, commit `3b4482a99b80ea5fc75f187b1be3120a3f5905b3` (commit nguồn ghi trong `METADATA.pb`). sha256 của `OFL.txt`: `cb3382d4643e8b02c12e322c220a3c76a5020d667e4fd4e7c75e744cca6caa6b`.

| File | sha256 |
|---|---|
| `Tinos-Regular.ttf` | `60a0e8ef0c04dd5dd69ffe91025fa2ae5836cbd35600a82ba031977557e2cb61` |
| `Tinos-Bold.ttf` | `393269dbab8899f938db19783eca5eac92eb431f7ae0ab45b8349ca895f1a06b` |
| `Tinos-Italic.ttf` | `5942266ed398b155d7dc23e36833e7ec6be988f2439bdbeb8ef1bede808eaa91` |
| `Tinos-BoldItalic.ttf` | `a5de79f0fe863ea0954757acb3d47b3ccd0a930ce3dd5b97230cd3866790a06e` |
| `METADATA.pb` | `e9db6bd24890351be0ac41486fbcf4ccb10b34ec19f2e77d7a5517f2eb1dbafe` |
| `DESCRIPTION.en_us.html` | `8dc9e6dbfd6dd44ad7a0781b5ef0eb3ca5b1c9aeb280b1aaa3c9432c32c51869` |

**Mâu thuẫn trong chính nguồn, nói thẳng:** `METADATA.pb` ghi `license: "OFL"`, bảng `name` của cả bốn file font ghi "licensed under the SIL Open Font License, Version 1.1", và `OFL.txt` của kho nguồn là OFL 1.1 — nhưng `DESCRIPTION.en_us.html` ghi nguyên văn *"Updated in May 2013 with improved hinting and released under the Apache 2.0 license."* Đọc theo ngày: mô tả là văn bản cũ chưa sửa; file font và giấy phép hiện hành là OFL 1.1. Bản phân phối được đề xuất là **đúng các file có sha256 ở bảng trên**, mang OFL 1.1 trong bảng `name` của chính chúng.

Nguyên văn câu mô tả về tương thích (`DESCRIPTION.en_us.html`): *"Tinos was designed by Steve Matteson as an innovative, refreshing serif design that is metrically compatible with Times New Roman™."*

## Nguyên văn `OFL.txt`

```text
Copyright 2026 The Tinos Project Authors (https://github.com/googlefonts/tinos)

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
https://openfontlicense.org


-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded, 
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```
