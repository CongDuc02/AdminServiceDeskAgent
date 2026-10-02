# Object storage chạy local — thử giao thức ghi một lần trên ba sản phẩm S3-compatible

- **Dùng cho:** A-072, ADR-031. Đầu vào phụ cho A-024 (yêu cầu T2).
- **Ngày lấy và ngày thử:** 2026-09-27, trên máy người triển khai (Windows 11, x86_64), **không dùng Docker** — ràng buộc ở mục Xác minh contract của `06-structure.md`.
- **Client:** `boto3` **1.37.3**, `botocore` **1.37.3** — đúng bản ghim trong `backend/pyproject.toml`; Python 3.11.9.
- **Nguồn — bản phân phối, phiên bản đọc từ chính binary hay metadata gói, không ghi từ trí nhớ:**
  - SeaweedFS **4.47** — `https://github.com/seaweedfs/seaweedfs/releases/download/4.47/windows_amd64.zip`, sha256 `8809359079e62fcd60574ff661449160899622c52072f3f569d346669079efe9`; md5 khớp file `.md5` đi kèm bản phát hành. `weed version` in: `version 30GB 4.47 c5073360007d28385a33426a42ac3e4ec504c5a3 windows amd64`. Bản phát hành ngày 2026-09-14 theo GitHub API.
  - rclone **v1.75.1** — `https://github.com/rclone/rclone/releases/download/v1.75.1/rclone-v1.75.1-windows-amd64.zip`, sha256 `200eb602c126d82aa38b51e0f6b9ae837473ff99b51278d3f6f837574c494d6e`, khớp file `SHA256SUMS` của bản phát hành.
  - moto **5.2.3** — cài bằng `pip install "moto[server]"`; phiên bản và `License: Apache-2.0` đọc từ `METADATA` của gói đã cài.
  - MinIO — `https://dl.min.io/server/minio/release/windows-amd64/minio.exe` (mục 1).
- **Nguồn — tài liệu:** wiki của SeaweedFS lấy bằng `curl` từ `https://raw.githubusercontent.com/wiki/seaweedfs/seaweedfs/<trang>.md` — các trang `Amazon-S3-API`, `S3-Conditional-Operations`, `S3-Object-Lock-and-Retention`, `S3-Credentials`. **Wiki không gắn phiên bản**: mô tả tình trạng ngày lấy, có thể mô tả bản mới hơn 4.47. Vì vậy mọi kết luận dưới đây dựa trên **phép thử trên binary 4.47**; wiki chỉ là căn cứ phụ. Giấy phép lấy từ file `LICENSE` ở tag `4.47` của repo.
- **Phải chạy lại khi đổi bản SeaweedFS hay `boto3`** — cùng bộ phép thử ở mục 3.

---

## 1. MinIO — không còn bản phân phối

Tải binary Windows từ trang phân phối chính thức. Server trả:

```text
HTTP/1.1 410 Gone
Date: Sun, 27 Sep 2026 14:44:39 GMT
```

Thân response, nguyên văn:

```text
410 Gone

The open-source MinIO Server, MinIO Client (mc) and MinIO KES projects are
archived and no longer maintained. MinIO does not provide product support,
security updates, or security advisories for them, and does not accept or
process vulnerability reports concerning them.

These files are no longer served from this site. This applies to all
community releases and to all hotfix builds for them.
```

GitHub API, cùng ngày, cho repo `minio/minio`: `"archived": true`, `"spdx_id": "AGPL-3.0"`, lần push cuối `2026-04-24T17:54:39Z`.

## 2. SeaweedFS — trích tài liệu

### 2.1 Ghi có điều kiện — trang `S3-Conditional-Operations`

> **The conditional check and the write are atomic — cluster-wide.** The
> precondition is evaluated against the live object and the write is applied
> under the same lock, on the filer that owns the key in the cluster's hash
> ring. Two clients racing an `If-Match` update never both succeed, regardless
> of which filer each one talks to. See
> [[Filer Operation Serialization]] for the underlying primitive
> (`ObjectTransaction`) and how it stays correct across filer restarts and
> ring changes.

> | Header | Type | Applies to | Special values |
> |--------|------|------------|----------------|
> | `If-Match` | ETag | GET, HEAD, PUT, POST, COPY, **DELETE** | `*` matches any existing object; comma-separated ETag list is honored |
> | `If-None-Match` | ETag | GET, HEAD, PUT, POST, COPY | `*` matches only when the object does **not** exist (compare-and-create); comma-separated ETag list is honored |
> | `If-Modified-Since` | RFC 1123 date | GET, HEAD, PUT, POST, COPY | — |
> | `If-Unmodified-Since` | RFC 1123 date | GET, HEAD, PUT, POST, COPY | — |

### 2.2 Khoá đối tượng — trang `S3-Object-Lock-and-Retention`

> ## Prerequisites
>
> - **Versioning Required**: Object Lock can only be enabled on buckets that have versioning enabled
> - **Immutable Setting**: Object Lock can only be enabled when creating a bucket, not on existing buckets
> - **S3 API**: All Object Lock operations are available through the S3 API

> #### Compliance Mode
> - Objects cannot be deleted or modified by any user, including the root user
> - Retention periods cannot be shortened
> - Provides the highest level of protection
> - Suitable for regulatory compliance requirements

### 2.3 Bảng API — trang `Amazon-S3-API`, ba dòng liên quan

| API Operation | Supported | Notes |
|---|---|---|
| PutBucketVersioning | Yes | |
| PutObject | Yes | Supports SSE, user metadata (`x-amz-meta-*`), conditional headers |
| PutObjectRetention | Yes | |

### 2.4 Credential — trang `S3-Credentials`

Định dạng file identity, trích:

```json
{
  "identities": [
    {
      "name": "admin_user",
      "credentials": [
        {
          "accessKey": "admin_access_key",
          "secretKey": "admin_secret_key"
        }
      ],
      "actions": ["Admin", "Read", "Write"]
    },
    {
      "name": "read_only_user",
      "credentials": [
        {
          "accessKey": "readonly_access_key",
          "secretKey": "readonly_secret_key"
        }
      ],
      "actions": ["Read"]
    }
  ]
}
```

### 2.5 Giấy phép — `LICENSE` ở tag `4.47`, hai dòng đầu

```text
                                 Apache License
                           Version 2.0, January 2004
```

GitHub API cùng ngày: `"spdx_id": "Apache-2.0"`, `"archived": false`, lần push cuối `2026-09-27T13:10:03Z`.

## 3. Phép thử

Một script Python dùng đúng `boto3` của dự án, `addressing_style = path`, `retries.max_attempts = 1` để lỗi hiện nguyên hình. Mỗi lần chạy tạo bucket mới. Khoá object theo dạng của mục Lưu trữ file và bất biến bản render ở `04-data.md`: `renders/<sha256>`. Script và dữ liệu thử nằm ngoài repo.

Cách khởi động từng sản phẩm:

- **SeaweedFS:** `weed mini -dir=<thư mục> -admin.ui=false -s3.config=<file identity>` — một identity `bo19_dev`, `actions: [Admin, Read, Write]`. Lượt đầu chạy không có `-s3.config`; kết quả T1–T9 giống hệt lượt có credential. Cấu hình ADR-031 chọn là `weed server`, ở mục 3.4.
- **rclone:** `rclone serve s3 --addr 127.0.0.1:8334 --auth-key <ak>,<sk> <thư mục>`.
- **moto:** `moto_server -p 8335`.

### 3.1 Giao thức ghi

| # | Phép thử | Ứng với | SeaweedFS 4.47 | moto 5.2.3 | rclone v1.75.1 |
|---|---|---|---|---|---|
| T1 | `PUT` khoá mới kèm `If-None-Match: *` | Bước 3 của giao thức ghi một lần | HTTP 200 | HTTP 200 | HTTP 200 |
| T2 | `PUT` lại **khoá đã có** kèm `If-None-Match: *`, byte khác, rồi đọc lại | Yêu cầu T2 của A-024 — ghi có điều kiện; ca (c) và rủi ro còn lại của giao thức | **Từ chối** `PreconditionFailed` 412; byte cũ nguyên vẹn: có | **Từ chối** `PreconditionFailed` 412; byte cũ nguyên vẹn: có | **Bị đè** — byte cũ nguyên vẹn: không |
| T3 | `PUT` kèm hai trường metadata `bo19-pin-reason`, `bo19-document-number` và checksum SHA-256; `HEAD` với `ChecksumMode=ENABLED`; đọc lại | Metadata của bản ghim `ISSUED` ghi trong cùng lệnh `PUT`; checksum | Metadata đọc lại: `bo19-document-number`, `bo19-pin-reason`; checksum SHA-256 trả về: có; byte đọc lại khớp: có | Metadata đọc lại: `bo19-pin-reason`, `bo19-document-number`; checksum SHA-256 trả về: có; byte đọc lại khớp: có | Metadata đọc lại: `Bo19-Document-Number`, `Bo19-Pin-Reason`; checksum SHA-256 trả về: có; byte đọc lại khớp: có |
| T4 | Bật versioning, ghi hai lần cùng khoá, đọc lại bản cũ theo `VersionId` | Yêu cầu T2 — versioning | `Enabled`; 2 bản; bản cũ đọc lại đúng: có | `Enabled`; 2 bản; bản cũ đọc lại đúng: có | Lỗi `NotImplemented` HTTP 501 |
| T5 | Bucket tạo có object lock; `PUT` kèm retention `COMPLIANCE` một ngày; xoá đúng version đó | Yêu cầu T2 — khoá đối tượng | **Từ chối** `AccessDenied` 403 | **Từ chối** `AccessDenied` 403 | Lỗi phía client: `ParamValidationError` |
| T6 | 8 luồng cùng `PUT` một khoá mới kèm `If-None-Match: *` | Ghi đồng thời — đúng một người thắng | **1** thành công, 7 bị từ chối | **1** thành công, 7 bị từ chối | **8** thành công, 0 bị từ chối |
| T7 | `ListObjectsV2` theo tiền tố `renders/` | Đối chiếu object mồ côi (runbook ở `11-ops.md`) | 3 object | 3 object | 7 object |
| T8 | `PUT` lại khoá đã có **không** kèm điều kiện | Chứng minh bảo vệ nằm ở header, không ở sản phẩm | **Bị đè** | **Bị đè** | **Bị đè** |
| T9 | Ghi không khoá, **sau đó** gắn retention `COMPLIANCE` (`PutObjectRetention`), đọc lại, xoá version | Khoá đối tượng gắn **lúc ghim**, sau khi ghi | Mode đọc lại `COMPLIANCE`; xoá: **từ chối** `AccessDenied` 403 | Lỗi `500` HTTP 500 | Lỗi phía client: `ParamValidationError` |
| T10 | Bucket versioning: `PUT` kèm `If-None-Match: *`, xoá (sinh delete marker), `PUT` lại kèm điều kiện; rồi thêm một `PUT` kèm điều kiện đóng vai lệnh ghi trễ của claim cũ | Đối soát `object_claim_reconcile` — ca (b) — trên bucket có versioning | Ghi lại sau delete marker: thành công; lệnh ghi trễ của claim cũ: **từ chối** `PreconditionFailed`; byte hiện hành `claim-2`; 2 bản, 1 delete marker | Ghi lại sau delete marker: thành công; lệnh ghi trễ của claim cũ: **từ chối** `PreconditionFailed`; byte hiện hành `claim-2`; 2 bản, 1 delete marker | Không chạy — rclone không có versioning (T4) |

Ghi chú cho bảng:

- **moto, T9:** server ghi `PUT …?retention` trả 200 và `GET …?retention` trả 200 trong log của chính nó, nhưng `botocore` nhận lỗi mã `500` khi đọc lại retention. Lặp lại y hệt ở lượt chạy thứ hai. Không điều tra thêm.
- **rclone, T6:** cả 8 lệnh ghi nhận **HTTP 200**, trong khi log của rclone ghi lỗi `rename … Access is denied` cho các lệnh ghi đồng thời vào cùng khoá. Client được báo thành công cho những lệnh ghi mà server ghi nhận là hỏng.
- **rclone, T5, T9:** lỗi phía client vì `PutObject` không trả `VersionId` — hệ quả của việc không có versioning (T4 `NotImplemented`).
- **rclone, T7:** 7 object ở lượt liệt kê, trong khi script chỉ ghi 3 khoá dưới tiền tố đó tới lúc ấy. Không điều tra thêm.
- **rclone, T3:** tên khoá metadata đọc lại bị đổi hoa thường — `Bo19-Pin-Reason` thay vì `bo19-pin-reason`.

### 3.2 Bền dữ liệu và credential

| Phép thử | SeaweedFS 4.47 | moto 5.2.3 |
|---|---|---|
| Ghi một object, **buộc tắt tiến trình** (`taskkill /F`), khởi động lại với cùng thư mục dữ liệu, đọc lại | Đọc lại được, byte khớp | `NoSuchBucket` 404 — **mất toàn bộ dữ liệu** |
| Sau khi khởi động lại với `-s3.config`: đọc bằng access key không có trong file identity | `InvalidAccessKeyId` 403 | — |
| Đọc bằng đúng credential | Đạt | — |

rclone không thử mục này vì đã trượt T2 và T4.

### 3.3 Cổng mạng — SeaweedFS

`weed help mini` in giá trị mặc định: `-ip.bind` là `0.0.0.0`. Chạy lại với `-ip=127.0.0.1 -ip.bind=127.0.0.1 -admin.ui=false -s3.config=…`, rồi liệt kê cổng đang nghe của tiến trình bằng `netstat -ano`:

- `127.0.0.1`: 7333, 8181, 8333, 8888, 9101, 9333, 9340, 18333, 18888, 19333, 19340, 23646.
- **Vẫn nghe trên mọi giao diện:** `0.0.0.0:33646` và `[::]:33646` — dù `-admin.ui=false`.

T1–T9 chạy lại trên cấu hình này: kết quả giống hệt bảng ở mục 3.1.

### 3.4 Cổng 33646 là gì, và cách tắt

**Là cổng gRPC cho worker của thành phần admin.** Mã nguồn ở tag `4.47`, lấy bằng `curl` từ `https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.47/weed/command/<file>`:

`weed/command/admin.go`, dòng 285–288:

```go
	// Set default gRPC port if not specified
	if *a.grpcPort == 0 {
		*a.grpcPort = *a.port + 10000
	}
```

`weed/command/mini.go`, dòng 948–960:

```go
	// Every other service binds within a moment of this check, but the admin
	// waits for all of them first. The admin gRPC port sits inside the Linux
	// ephemeral range, so during that gap one of the cluster's own outgoing
	// connections can take it and the admin then dies on bind. Hold a listener
	// from here and hand it to the admin instead of re-binding later. Clear
	// first: an in-process rerun would otherwise inherit the closed listener
	// of the previous run and only find out inside Serve.
	miniAdminOptions.workerGrpcListener = nil
	if listener, err := net.Listen("tcp", fmt.Sprintf(":%d", *miniAdminOptions.grpcPort)); err != nil {
		glog.Warningf("Could not reserve Admin gRPC port %d: %v", *miniAdminOptions.grpcPort, err)
	} else {
		miniAdminOptions.workerGrpcListener = listener
	}
```

`weed/command/mini.go`, dòng 1669–1669:

```go
		if err := startAdminServer(ctx, adminOptions, *miniEnableAdminUI, icebergPort, lancePort, urlPrefix); err != nil {
```

Ba điều đọc được từ mã:

- Cổng mặc định là cổng HTTP của admin cộng 10000: 23646 + 10000 = 33646.
- `weed mini` giữ trước cổng này bằng `net.Listen("tcp", ":<cổng>")` — địa chỉ rỗng, tức **mọi giao diện**, bất kể `-ip.bind`.
- `-admin.ui` chỉ là một tham số truyền vào `startAdminServer`. Admin server và cổng gRPC của nó vẫn chạy. Trong danh sách cờ bool của `weed mini` không có cờ nào tắt hẳn admin.

**Cách tắt: dùng `weed server` thay cho `weed mini`.** `weed help server` không có cờ nào của admin, và trong lượt chạy dưới đây không có cổng 23646 hay 33646 nào mở. Lệnh đã chạy:

```text
weed server -dir=<thư mục> -ip=127.0.0.1 -ip.bind=127.0.0.1 -filer -s3 -s3.config=<file identity> -master.telemetry=false -master.volumeSizeLimitMB=64 -volume.max=200
```

- **Cổng đang nghe của tiến trình** (`netstat -ano`): 8080, 8181, 8333, 8888, 9101, 9333, 18080, 18333, 18888, 19333 — **tất cả ở `127.0.0.1`**, không còn 33646.
- **T1–T9:** giống hệt bảng ở mục 3.1. **T10:** ghi lại sau delete marker thành công; lệnh ghi trễ của claim cũ bị từ chối `PreconditionFailed`; byte hiện hành `claim-2`.
- **Credential:** access key lạ bị trả `InvalidAccessKeyId` 403.
- **Bền dữ liệu:** ghi một object, `taskkill /F`, khởi động lại cùng lệnh và cùng thư mục, đọc lại — byte khớp.
- **`-master.volumeSizeLimitMB=64 -volume.max=200` là bắt buộc trên máy này.** Lần chạy đầu không có hai cờ này: từ bucket thứ hai trở đi, `PUT` trả `InternalError` 500, log ghi `create 7 volume, created 0: Not enough data nodes found!`. Mỗi bucket là một collection; `weed mini` tự thu nhỏ volume theo dung lượng đĩa (`weed help mini`), `weed server` thì không. Hai giá trị là chọn, không có căn cứ đo.

**Telemetry.** Cả `weed mini` lẫn `weed server` có cờ `-master.telemetry`, mặc định **bật**, gửi "anonymous cluster statistics" tới `-master.telemetry.url`, mặc định `https://telemetry.seaweedfs.com/api/collect` (`weed help server`; `mini.go` dòng 439–440). Các lượt chạy `weed mini` ở mục 3.1–3.3 **không** tắt cờ này. Lượt `weed server` ở trên có `-master.telemetry=false`.

## 4. Kết luận — với đúng các bản trên

| Câu hỏi | SeaweedFS 4.47 | moto 5.2.3 | rclone v1.75.1 | MinIO |
|---|---|---|---|---|
| Chạy native trên Windows, không Docker | Có | Có — gói Python | Có | Không tải được binary |
| Ghi có điều kiện `If-None-Match: *` chặn ghi đè | **Có** (T2, T6, T10) | **Có** (T2, T6, T10) | **Không** (T2, T6) | — |
| Versioning | Có (T4) | Có (T4) | Không (T4) | — |
| Khoá đối tượng, kể cả gắn sau khi ghi | Có (T5, T9) | Có khi gắn lúc ghi (T5); gắn sau khi ghi lỗi (T9) | Không | — |
| Metadata và checksum SHA-256 | Có (T3) | Có (T3) | Có, tên khoá đổi hoa thường (T3) | — |
| Dữ liệu còn sau khi tiến trình chết | **Có** | **Không** | Không thử | — |
| Bắt buộc credential | Có, với `-s3.config` | Không thử | Không thử — có tuỳ chọn `--auth-key`, không thử khoá sai | — |
| Bảo vệ khi client **không** gửi điều kiện (T8) | Không — bị đè | Không — bị đè | Không — bị đè | — |

Dòng cuối là điều kiện của **adapter**, không phải của sản phẩm: ghi có điều kiện chỉ bảo vệ khi mọi lệnh `PUT` mang header.
