# pgvector — giới hạn số chiều (trích nguyên văn)

**Nguồn:** `README.md` và `CHANGELOG.md` của repository `pgvector/pgvector`, ghim tại commit `efa08fda9ec485d80292d0487a77939c087dedcc` (nhánh `master` lúc lấy).
**URL:**
- https://raw.githubusercontent.com/pgvector/pgvector/efa08fda9ec485d80292d0487a77939c087dedcc/README.md
- https://raw.githubusercontent.com/pgvector/pgvector/efa08fda9ec485d80292d0487a77939c087dedcc/CHANGELOG.md

**Ngày lấy:** 2026-09-12 · **Dùng ở:** A-028, A-037 trong `docs/design/ASSUMPTIONS.md`

> Đây là bản trích, không phải bản sao toàn văn. Chỉ gồm những đoạn mà thiết kế viện dẫn. Các đoạn dưới đây chép nguyên văn, không dịch, không sửa.

---

## 1. Kiểu được index — mục HNSW của README

```text
Supported types are:

- `vector` - up to 2,000 dimensions
- `halfvec` - up to 4,000 dimensions
- `bit` - up to 64,000 dimensions
- `sparsevec` - up to 1,000 non-zero elements
```

## 2. Kiểu được index — mục IVFFlat của README

```text
Supported types are:

- `vector` - up to 2,000 dimensions
- `halfvec` - up to 4,000 dimensions
- `bit` - up to 64,000 dimensions
```

## 3. FAQ — index vector trên 2,000 chiều

```text
#### What if I want to index vectors with more than 2,000 dimensions?

You can use [half-precision vectors](#half-precision-vectors) or [half-precision indexing](#half-precision-indexing) to index up to 4,000 dimensions or [binary quantization](#binary-quantization) to index up to 64,000 dimensions. Other options are [indexing subvectors](#indexing-subvectors) (for models that support it) or [dimensionality reduction](https://en.wikipedia.org/wiki/Dimensionality_reduction).
```

## 4. FAQ — lưu vector khác chiều trong cùng một cột

```text
#### Can I store vectors with different dimensions in the same column?

You can use `vector` as the type (instead of `vector(n)`).

CREATE TABLE embeddings (model_id bigint, item_id bigint, embedding vector, PRIMARY KEY (model_id, item_id));

However, you can only create indexes on rows with the same number of dimensions (using [expression](https://www.postgresql.org/docs/current/indexes-expressional.html) and [partial](https://www.postgresql.org/docs/current/indexes-partial.html) indexing):

CREATE INDEX ON embeddings USING hnsw ((embedding::vector(3)) vector_l2_ops) WHERE (model_id = 123);

and query with:

SELECT * FROM embeddings WHERE model_id = 123 ORDER BY embedding::vector(3) <-> '[3,1,2]' LIMIT 5;
```

## 5. Giới hạn lưu trữ của kiểu `vector` — README

```text
Each vector takes `4 * dimensions + 8` bytes of storage. Each element is a single-precision floating-point number (like the `real` type in Postgres), and all elements must be finite (no `NaN`, `Infinity` or `-Infinity`). Vectors can have up to 16,000 dimensions.
```

## 6. Mốc phiên bản — CHANGELOG

```text
## 0.7.0 (2024-04-29)

- Added `halfvec` type
- Added `sparsevec` type
- Added support for indexing `bit` type
```

```text
## 0.4.0 (2023-01-11)

- Increased max dimensions for vector from 1024 to 16000
- Increased max dimensions for index from 1024 to 2000
```

---

## Những gì bản trích này KHÔNG xác nhận

- **Phiên bản pgvector** mà PostgreSQL managed của Render cung cấp — vẫn `[CẦN XÁC MINH]` (A-037).
- **Số chiều của bất kỳ embedding model cụ thể nào** — phải lấy từ model card hay tài liệu của nhà cung cấp.
- **Trần 2,000 chiều cho index `vector` có từ bản 0.4.0**, không phải từ 0.7.0. Bản 0.7.0 thêm `halfvec` và thêm khả năng index `bit`; con số 2,000 của `vector` có từ trước đó.
