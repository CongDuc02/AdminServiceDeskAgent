# CLAUDE.md — Admin Service Desk Agent (BO-19)

> File này là **nguồn sự thật** cho mọi phiên làm việc. Đọc toàn bộ file này trước khi làm bất cứ việc gì.

---

## 0. Chế độ làm việc hiện tại

**DESIGN MODE.** Nhiệm vụ là sinh tài liệu thiết kế, **không implement business logic**.

Được phép sinh (vì đây là *contract*, không phải implementation):

- `openapi.yaml`
- JSON Schema / Pydantic model chỉ chứa field + type + validator khai báo
- SQL DDL (`CREATE TABLE`, index, constraint)
- File `.md` tài liệu và Mermaid diagram
- Cây thư mục rỗng + `__init__.py` + docstring mô tả trách nhiệm module

Không được phép sinh: hàm có thân xử lý, prompt gọi LLM thật, code kết nối DB, test chạy được, Dockerfile hoạt động. Khi nào chuyển sang BUILD MODE tôi sẽ nói rõ.

---

## 1. Bối cảnh đề tài

**Mã:** BO-19 — Hỗ trợ / Back office
**Tên:** AI Agent Xử lý Yêu cầu Hành chính & Cấp phát Văn bản (Admin Service Desk Agent)

**Thực trạng:** Nhân viên gửi yêu cầu hành chính (xác nhận công tác, giấy giới thiệu, đặt phòng họp, xin con dấu) qua nhiều kênh rời rạc. Phòng Hành chính xử lý thủ công → trả kết quả trễ, khó theo dõi trạng thái.

**Bài toán:** Cần agent tiếp nhận yêu cầu bằng ngôn ngữ tự nhiên, phân loại, kiểm tra điều kiện, soạn văn bản từ mẫu, định tuyến duyệt & ký, cán bộ hành chính duyệt rồi phát hành.

**Ràng buộc nghiệp vụ bắt buộc:**

- HITL **bắt buộc** trước khi phát hành văn bản hoặc dùng con dấu. Không có đường vòng, không có auto-approve, kể cả khi confidence cao.
- Bảo mật thông tin nhân viên và văn bản chính thức.
- Độ chính xác nội dung văn bản (sai thể thức = văn bản vô hiệu).
- Kiểm soát chi phí LLM.

---

## 2. Phạm vi — bám sát đề bài, không tự mở rộng

### MVP (bắt buộc)

- Web deploy, đăng nhập 2 vai trò: **Nhân viên** và **Cán bộ hành chính**
- Tạo yêu cầu bằng chat → agent phân loại + kiểm tra điều kiện + sinh văn bản từ mẫu
- Duyệt & phát hành, theo dõi trạng thái

### Nâng cao (thiết kế kiến trúc sẵn sàng, không đưa vào Sprint đầu)

- Agent tự điền template & tạo bản in
- Định tuyến ký nhiều cấp
- Memory yêu cầu định kỳ của nhân viên
- Đặt lịch / tài nguyên qua tool
- HITL duyệt con dấu
- Dashboard SLA, cảnh báo tồn đọng & giới hạn

> **Quy ước ưu tiên:** dùng **MoSCoW** (Must / Should / Could / Won't) theo `docs/reference/sample_prd.md`, không dùng P0/P1/P2. Ánh xạ: "Cơ bản" → Must · "Nâng cao" → Should hoặc Could · phần dưới đây → Won't.
>
> Mức MoSCoW **khai báo đúng một lần** ở PRD mục 5. Các phase khác chỉ tham chiếu tên feature; chỗ nào cần đánh dấu hạng mục sẽ bị cắt khỏi Sprint đầu thì dùng nhãn `[Should]` hoặc `[Could]`. Nhãn `[MVP]`/`[ADVANCED]` đã bỏ hẳn.

### Ngoài phạm vi (không thiết kế trừ khi tôi yêu cầu)

- Graph database / Neo4j — **cấm tự thêm.** Nếu thực sự cần, phải viết ADR chứng minh SQL + vector không giải quyết được, và chờ tôi duyệt.
- Mobile app, SSO doanh nghiệp, tích hợp ERP/HRM thật, multi-tenant, i18n.

---

## 3. Tech stack

**Bắt buộc theo đề bài:** LLM + LangGraph · RAG trên kho mẫu văn bản & quy trình hành chính · tool điền template `.docx` và đặt lịch phòng họp · Vector DB · Backend FastAPI · Frontend React · Deploy Render + PostgreSQL.

**Quy tắc:**

- Mọi lựa chọn công nghệ **ngoài** danh sách trên phải có ADR với ít nhất một phương án bị loại và lý do loại.
- Ưu tiên phương án chạy được trên Render với PostgreSQL managed. Cân nhắc rõ `pgvector` vs vector DB ngoài, có so sánh chi phí.
- Ràng buộc Render phải được nêu trong thiết kế: cold start, filesystem không bền vững, background worker, cron job, giới hạn thời gian request.

---

## 4. Luật viết tài liệu

1. **Đọc trước khi viết.** Trước mỗi phase, đọc `docs/design/_PLAN.md`, `docs/design/decisions/*.md` và toàn bộ file của các phase phụ thuộc. Không thiết kế lại thứ đã chốt.
2. **Một phase = một lần chạy.** Không nhảy sang phase sau. Kết thúc phase thì dừng và báo cáo.
3. **Không có thông tin thì hỏi, không bịa.** Mọi giả định ghi vào `docs/design/ASSUMPTIONS.md` theo dạng `A-xxx | Giả định | Ảnh hưởng nếu sai | Cách xác minh`. Cấm bịa số liệu (số nhân viên, SLA, ngân sách, benchmark, giá token) — nếu cần thì ghi `TBD` kèm mục trong ASSUMPTIONS.
4. **Mọi quyết định kiến trúc → ADR** tại `docs/design/decisions/ADR-xxx-<slug>.md`: Context · Options · Decision · Consequences · Rejected alternatives. Trong tài liệu chỉ trích dẫn `ADR-xxx`, không lặp lại lập luận.
5. **Nhất quán là tiêu chí đánh giá.** Tên entity, tên trạng thái, tên agent, tên tool phải giống hệt nhau giữa các phase. Nếu cần đổi, sửa file gốc rồi ghi vào `docs/design/CHANGELOG.md`.
6. **Ngôn ngữ:** tiếng Việt cho diễn giải, giữ nguyên thuật ngữ kỹ thuật tiếng Anh (agent, tool, retrieval, checkpointer, embedding). Tên bảng/cột/endpoint/biến bằng tiếng Anh `snake_case`.
7. **Mermaid phải hợp lệ.** Không dùng ký tự đặc biệt chưa escape trong nhãn node. Mỗi diagram tối đa ~20 node; phức tạp hơn thì tách nhiều diagram.
8. **Bảng cho requirement, bullet cho decision.** Mỗi requirement có ID ổn định (`FR-xx`, `NFR-xx`, `US-xx`, `RISK-xx`).
9. **Tài liệu tham chiếu trong `docs/reference/` là chuẩn format, không phải nội dung.** `sample_prd.md` là PRD của một dự án khác (trợ lý tra cứu kế toán). Học **cấu trúc, giọng văn, mức chi tiết, quy ước** của nó; tuyệt đối không bê nội dung nghiệp vụ kế toán, persona, metric hay pain point sang BO-19. Nếu một mục trong mẫu không áp dụng được cho BO-19, nói rõ trong một dòng thay vì bịa nội dung cho đầy.
10. **Không nhồi.** Thà 1 trang chính xác còn hơn 5 trang lấp chỗ. Cấm viết mục kiểu "N/A cho hệ thống này" — nếu một mục không áp dụng thì nói rõ trong một dòng và giải thích tại sao.
11. **Không tự ý sửa `CLAUDE.md`.** File này chỉ được sửa khi tôi cho phép **từng lần một**, và sau khi sửa phải **báo cáo diff** đầy đủ trong phần báo cáo cuối phase. Cho phép ở lần trước không có giá trị cho lần sau. Phát hiện `CLAUDE.md` sai hay mâu thuẫn thì **báo cáo và chờ**, không tự sửa. Riêng `docs/design/` thì được ghi tự do theo `_PLAN.md`.

---

## 5. Ràng buộc domain bắt buộc phải xử lý

Mọi phase liên quan phải trả lời được, không được lướt qua:

- **Thể thức văn bản hành chính**: tham chiếu Nghị định 30/2020/NĐ-CP về công tác văn thư.
  **Quy tắc trích dẫn — áp cho MỌI nguồn bên ngoài, không riêng mục này:** cấm viết **từ trí nhớ** số điều, khoản, điểm, phụ lục của văn bản pháp luật; số hiệu và nội dung tiêu chuẩn; phiên bản, giới hạn và con số trong tài liệu sản phẩm; số liệu benchmark. Chỉ được trích dẫn khi bản gốc đã có trong `docs/reference/`. Chưa có thì ghi `[CẦN XÁC MINH]` kèm **tên văn bản** và chỉ mô tả ở mức nguyên tắc.
- **Dữ liệu cá nhân nhân viên**: tham chiếu Nghị định 13/2023/NĐ-CP, xử lý ở mức nghĩa vụ (mục đích thu thập, thời hạn lưu, quyền của chủ thể), không phán quyết pháp lý.
- **Cấp số văn bản**: sổ văn bản, chống trùng số, chống lỗ hổng số khi request thất bại, xử lý đồng thời.
- **Vòng đời văn bản**: draft → duyệt → ký → đóng dấu → phát hành → lưu trữ → **thu hồi/huỷ hiệu lực**. Trạng thái thu hồi bắt buộc có mặt.
- **Template `.docx`**: versioning template, biến thay thế, kiểm tra biến thiếu, render sang PDF, lưu bản gốc bất biến.
- **Định tuyến duyệt**: nhiều cấp, ủy quyền khi vắng mặt, escalation quá hạn, từ chối kèm lý do, yêu cầu sửa lại.
- **Tiếng Việt**: embedding tiếng Việt, chuẩn hoá dấu, hybrid search (BM25 + vector) cho mã nhân viên và tên riêng.
- **LangGraph**: state schema, node/edge, conditional edge, `interrupt` để dừng chờ người duyệt, checkpointer trên PostgreSQL để resume sau nhiều giờ/ngày.
- **Chi phí**: model routing (model rẻ cho phân loại/trích slot, model mạnh cho soạn thảo), token budget mỗi request, cache, ngưỡng cảnh báo.

---

## 6. Cấu trúc output

```
docs/reference/
  sample_prd.md          # chuẩn FORMAT cho PRD — không phải nguồn nội dung
docs/design/
  _PLAN.md               # kế hoạch phase + trạng thái (do tôi quản lý)
  ASSUMPTIONS.md         # giả định + câu hỏi mở
  GLOSSARY.md            # thuật ngữ, tên entity/trạng thái chuẩn
  CHANGELOG.md           # mọi thay đổi liên phase
  01-prd.md
  02-architecture.md
  ...
  decisions/ADR-001-*.md
  contracts/openapi.yaml
  contracts/schema.sql
```

---

## 7. Definition of Done cho mọi phase

- [ ] File đích đã ghi đúng đường dẫn trong `_PLAN.md`
- [ ] Không mâu thuẫn với phase trước (đã đối chiếu, ghi rõ đã kiểm tra những file nào)
- [ ] Mọi giả định mới đã vào `ASSUMPTIONS.md`
- [ ] Mọi quyết định công nghệ mới đã có ADR
- [ ] Mermaid render được
- [ ] Cuối file có mục **Open Questions** — nếu trống thì phải nói rõ "không có"
- [ ] Báo cáo cuối phase: đã tạo file nào, quyết định gì đáng chú ý, cần tôi xác nhận điều gì trước khi sang phase kế
