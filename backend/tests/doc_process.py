"""Tiến trình thật cho test khởi động lại (B9a, điểm dừng của PO 2026-10-13) — KHÔNG phải test, chạy bằng `python -m tests.doc_process <chế độ>`.

Mỗi lần chạy là một tiến trình Python mới: mở pool, mở `DocumentRunner` (checkpointer PostgreSQL THẬT), làm đúng một việc rồi in MỘT dòng `RESULT {json}` (chỉ mã và số) lên stdout. Provider LLM là transport giả trong tiến trình
(`BO19_PROC_LLM=ok` trả một nội dung hợp lệ; `none` — không kịch bản — mọi lời gọi LLM là lỗi 500, nên một lời gọi LLM ngoài ý muốn làm tiến trình hỏng).

Chế độ:
  render <request_id>          chạy `run_render`; xong thì ngủ (nếu `BO19_PROC_SLEEP=1`) để test giết nó khi graph đang chờ ở `interrupt`;
  hang <request_id>            như `render` nhưng bản render bị treo ở `docx_render` (in `HANGING` rồi ngủ) — test giết nó GIỮA lúc chạy;
  resume <document_id> <decision_record_id>   chạy `resume_document`.
Môi trường: BO19_PROC_DSN (role `bo19_app`), BO19_PROC_BUCKET, BO19_TEST_S3_* (như test), BO19_PROC_LLM.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

from bo19.ai_gateway.budget import Budget
from bo19.ai_gateway.gateway import Gateway
from bo19.ai_gateway.providers import ProviderClient
from bo19.ai_gateway.routing.profiles import load_profiles
from bo19.orchestrator.runner import DocumentRunner
from bo19.persistence.pool import Pool
from tests.doc_support import FINGERPRINT_KEY, draft_output
from tests.graph_support import KEY, FakeLlm
from tests.s3_support import storage_for


def emit(**fields) -> None:
    print("RESULT " + json.dumps(fields, ensure_ascii=False), flush=True)


def main(argv: list[str]) -> int:
    mode = argv[0]
    dsn, bucket = os.environ["BO19_PROC_DSN"], os.environ["BO19_PROC_BUCKET"]
    llm = FakeLlm()
    if os.environ.get("BO19_PROC_LLM") == "ok":
        llm.will("draft_free_content", draft_output())
    pool = Pool(dsn, application_name="bo19-test-proc", min_size=1, max_size=4)
    pool.open()
    gateway = Gateway(profiles=load_profiles().profiles, client=ProviderClient(base_url="https://llm.example.test/openai/v1", api_key=KEY, transport=llm.transport), budget=Budget(pool))
    runner = DocumentRunner.open(pool=pool, gateway=gateway, storage=storage_for(bucket), dsn=dsn, fingerprint_key=FINGERPRINT_KEY)
    try:
        if mode in ("render", "hang"):
            if mode == "hang":
                from bo19.orchestrator.document_graph import nodes as nodes_module

                def hang(*a, **k):
                    print("HANGING", flush=True)
                    time.sleep(3600)
                nodes_module.docx_render = hang  # giữa `draft_free_content` (đã lưu) và `render_draft`
            out = runner.run_render(request_id=uuid.UUID(argv[1]))
            emit(status=out.status, waiting_at=out.waiting_at, already=out.already, llm_calls=len(llm.calls("draft_free_content")), pid=os.getpid())
            if os.environ.get("BO19_PROC_SLEEP") == "1":
                time.sleep(3600)
        elif mode == "resume":
            out = runner.resume_document(document_id=uuid.UUID(argv[1]), decision_record_id=uuid.UUID(argv[2]))
            emit(status=out.status, already=out.already, llm_calls=len(llm.calls("draft_free_content")), pid=os.getpid())
        else:
            return 2
        return 0
    except Exception as e:  # noqa: BLE001 — chỉ mã
        emit(error=getattr(e, "reason_code", type(e).__name__), raw=getattr(e, "raw_code", None), llm_calls=len(llm.calls("draft_free_content")))
        return 1
    finally:
        runner.close()
        pool.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
