# PDF 32000-1:2008 — từ điển thông tin tài liệu (`Info`), mục 14.3.3 và Table 317, từ nguồn gốc bằng `curl`

- **Ngày lấy:** 2026-10-13. **Cách lấy:** `curl -sS -L https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf` — 22491828 byte — sha256 `9de0ca9e8570d6209e8bd48a355be8eb6ec376acfc3fc3ae97cd8730351417ff`. Excerpt dưới đây tách bằng `pdftotext -layout` (poppler, image `bo19-test`), dòng 36427–36509 của bản văn bản; giữ nguyên chữ (gồm cả ví dụ và chân trang), dừng trước mục 14.4.
- **Dùng cho:** B9a / M5 (PO, 2026-10-13) — ghi chuỗi watermark vào `/Subject` của PDF và kiểm bằng `pdfinfo`. Nguồn là **ISO 32000-1 (PDF 1.7)**.
- **Chưa có bản gốc:** ISO 32000-2 (PDF 2.0). `https://pdfa.org/norm-refs/ISO_32000-2.pdf` trả `403` (2026-10-13). Địa vị của từ điển `Info` ở PDF 2.0 vì vậy là **`[CẦN XÁC MINH]`** — A-096. Không suy ra từ tài liệu này.

## Điều nguồn nói, và điều nó không nói

- `Info` là mục **tuỳ chọn** của trailer; `Subject` là mục tuỳ chọn, kiểu *text string*, "(Optional; PDF 1.1) The subject of the document." Tương tự `Title`, `Author` ("The name of the person who created the document.").
- Nguồn **không** nói LibreOffice ánh xạ thuộc tính nào của `.docx` sang trường nào. Ánh xạ ấy là **số đo của B9a** trên LibreOffice 25.2.3.2 (`proposals/b9a-ke-hoach.md` mục A.1; thủ tục kiểm ở `11-ops.md`): `dc:subject` → `/Subject`; `dc:creator` → `/Author`; `keywords` bị tách từ; `comments`, `category` không ra PDF. Đó là quan sát, được giữ đúng bằng test trong CI chứ không phải quy tắc của nguồn này.

## Excerpt (nguyên văn)

```text
14.3.3   Document Information Dictionary

The optional Info entry in the trailer of a PDF file (see 7.5.5, “File Trailer”) shall hold a document information
dictionary containing metadata for the document; Table 317 shows its contents. Any entry whose value is not
known should be omitted from the dictionary rather than included with an empty string as its value.



© Adobe Systems Incorporated 2008 – All rights reserved                                                                549
PDF 32000-1:2008


Some conforming readers may choose to permit searches on the contents of the document information
dictionary. To facilitate browsing and editing, all keys in the dictionary shall be fully spelled out, not abbreviated.
New keys should be chosen with care so that they make sense to users.

The value associated with any key not specifically mentioned in Table 317 shall be a text string.

Although conforming readers may store custom metadata in the document information dictionary, they may not
store private content or structural information there. Such information shall be stored in the document
catalogue instead (see 7.7.2, “Document Catalog”).

                           Table 317 – Entries in the document information dictionary

         Key                Type           Value

         Title              text string    (Optional; PDF 1.1) The document’s title.

         Author             text string    (Optional) The name of the person who created the document.

         Subject            text string    (Optional; PDF 1.1) The subject of the document.

         Keywords           text string    (Optional; PDF 1.1) Keywords associated with the document.

         Creator            text string    (Optional) If the document was converted to PDF from another format,
                                           the name of the conforming product that created the original document
                                           from which it was converted.

         Producer           text string    (Optional) If the document was converted to PDF from another format,
                                           the name of the conforming product that converted it to PDF.

         CreationDate       date           (Optional) The date and time the document was created, in human-
                                           readable form (see 7.9.4, “Dates”).

         ModDate            date           (Required if PieceInfo is present in the document catalogue;
                                           otherwise optional; PDF 1.1) The date and time the document was
                                           most recently modified, in human-readable form (see 7.9.4, “Dates”).

         Trapped            name           (Optional; PDF 1.3) A name object indicating whether the document
                                           has been modified to include trapping information (see 14.11.6,
                                           “Trapping Support”):
                                           True       The document has been fully trapped; no further trapping
                                                      shall be needed. This shall be the name True, not the
                                                      boolean value true.
                                           False      The document has not yet been trapped. This shall be the
                                                      name False, not the boolean value false.
                                           Unknown Either it is unknown whether the document has been
                                                       trapped or it has been partly but not yet fully trapped; some
                                                       additional trapping may still be needed.
                                           Default value: Unknown.
                                           NOTE          The value of this entry may be set automatically by the
                                                         software creating the document’s trapping information, or
                                                         it may be known only to a human operator and entered
                                                         manually.

EXAMPLE            This example shows a typical document information dictionary.

                   1 0 obj
                      << /Title ( PostScript Language Reference, Third Edition )
                           /Author ( Adobe Systems Incorporated )
                           /Creator ( Adobe FrameMaker 5 . 5 . 3 for Power Macintosh® )
                           /Producer ( Acrobat Distiller 3 . 01 for Power Macintosh )
                           /CreationDate ( D : 19970915110347 - 08 ' 00 ' )
                           /ModDate ( D : 19990209153925 - 08 ' 00 ' )
                      >>
                   endobj



550                                             © Adobe Systems Incorporated 2008 – All rights reserved
                                                                                                          PDF 32000-1:2008
```
