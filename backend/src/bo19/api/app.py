"""app factory — mount /api/v1, phục vụ bản build client, luật 404.

Trách nhiệm: xem 06-structure.md mục Cây backend (bo19.api) + 02-architecture.md mục Thành phần, phần api.
Không chứa business logic — chỉ tạo FastAPI, mount routers rỗng, phục vụ static.
Router thật sinh từ contracts/openapi.yaml ở BUILD MODE.
"""
