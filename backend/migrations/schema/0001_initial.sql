-- =============================================================================
-- BO-19 Admin Service Desk Agent — contract DDL
-- Phase 4 — Data Architecture. Diễn giải đầy đủ: docs/design/04-data.md
-- =============================================================================
--
-- Quy ước của file này
--   * DDL thuần. KHÔNG seed data — kể cả danh mục permission, mã request_type,
--     vai trò hay mã lý do. Nơi nạp dữ liệu danh mục: mục Nguyên tắc dữ liệu
--     của 04-data.md.
--   * Không có hàm, trigger hay thủ tục nào. Mọi ràng buộc là khai báo:
--     CHECK, UNIQUE, FOREIGN KEY, cột GENERATED, và quyền GRANT/REVOKE.
--   * Enum viết bằng text + CHECK, không dùng CREATE TYPE ... AS ENUM.
--   * id là uuid do ứng dụng sinh; DB không có giá trị mặc định cho id.
--   * Mọi thời điểm là timestamptz.
--
-- Hai role — tạo NGOÀI file này, xem A-040
--   * bo19_migrator — sở hữu mọi bảng, chạy file này và mọi migration sau.
--   * bo19_app      — role runtime của api và queue_worker. KHÔNG sở hữu bảng
--                     nào. Chỉ có đúng các quyền cấp ở cuối file.
--
-- Bảng checkpoint của LangGraph KHÔNG nằm ở đây: thư viện sở hữu chúng
-- (mục Vòng đời checkpoint của 04-data.md).
-- =============================================================================

-- pgvector. Tên extension theo README của pgvector; nằm ngoài bản trích ở
-- docs/reference/pgvector-dimension-limits.md — [CẦN XÁC MINH], cùng A-037.
CREATE EXTENSION IF NOT EXISTS vector;


-- =============================================================================
-- A. Nhân sự, quyền, uỷ quyền
-- =============================================================================

CREATE TABLE employee (
    id                     uuid        PRIMARY KEY,
    employee_code          text        NOT NULL,
    full_name              text        NOT NULL,              -- PER
    department_code        text        NOT NULL,              -- INT; khoá lọc quyền theo phòng ban
    department_name        text        NOT NULL,              -- INT
    job_title              text        NOT NULL,              -- INT
    contract_type          text        NOT NULL,              -- PER; danh sách chờ A-013
    employment_start_date  date        NOT NULL,              -- PER
    employment_end_date    date,                              -- PER
    date_of_birth          date,                              -- PER
    national_id            text,                              -- RES
    is_active              boolean     NOT NULL DEFAULT true,
    source                 text        NOT NULL,              -- provenance (D-002)
    synced_at              timestamptz NOT NULL,              -- provenance (D-002)
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    row_version            integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_employee_code UNIQUE (employee_code),
    CONSTRAINT ck_employee_contract_type
        CHECK (contract_type IN ('PROBATION', 'FIXED_TERM', 'INDEFINITE')),
    CONSTRAINT ck_employee_employment_dates
        CHECK (employment_end_date IS NULL OR employment_end_date >= employment_start_date),
    CONSTRAINT ck_employee_source_not_blank CHECK (btrim(source) <> ''),
    CONSTRAINT ck_employee_department_code_not_blank CHECK (btrim(department_code) <> '')
);

CREATE TABLE role (
    code        text PRIMARY KEY,
    name_vi     text NOT NULL,
    CONSTRAINT ck_role_code CHECK (code ~ '^[A-Z][A-Z_]*$')
);

CREATE TABLE permission (
    code         text PRIMARY KEY,
    description  text NOT NULL,
    CONSTRAINT ck_permission_code CHECK (code ~ '^[a-z_]+\.[a-z_]+$')
);

CREATE TABLE role_permission (
    role_code        text NOT NULL REFERENCES role (code),
    permission_code  text NOT NULL REFERENCES permission (code),
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE employee_role (
    employee_id  uuid        NOT NULL REFERENCES employee (id),
    role_code    text        NOT NULL REFERENCES role (code),
    granted_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (employee_id, role_code)
);

-- Cấp lẻ permission ngoài gói vai trò: document.sign, document.revoke_confirm,
-- procedure.manage ở Sprint đầu (mục Permission và vai trò của 00-domain.md).
CREATE TABLE employee_permission_grant (
    id               uuid        PRIMARY KEY,
    employee_id      uuid        NOT NULL REFERENCES employee (id),
    permission_code  text        NOT NULL REFERENCES permission (code),
    granted_at       timestamptz NOT NULL DEFAULT now(),
    revoked_at       timestamptz,
    CONSTRAINT ck_permission_grant_revoke_after_grant
        CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

-- [Should] — nhưng đã có việc thật: employee_lookup và điều kiện 4 của
-- "Yêu cầu đủ điều kiện xử lý" (F1) đọc bảng này.
CREATE TABLE delegation (
    id                     uuid        PRIMARY KEY,
    delegator_employee_id  uuid        NOT NULL REFERENCES employee (id),
    delegate_employee_id   uuid        NOT NULL REFERENCES employee (id),
    permission_code        text        NOT NULL REFERENCES permission (code),
    valid_from             timestamptz NOT NULL,
    valid_to               timestamptz NOT NULL,
    revoked_at             timestamptz,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    row_version            integer     NOT NULL DEFAULT 1,
    CONSTRAINT ck_delegation_distinct_people CHECK (delegator_employee_id <> delegate_employee_id),
    CONSTRAINT ck_delegation_window CHECK (valid_to > valid_from)
);


-- =============================================================================
-- B. Cấu hình: sổ văn bản, loại yêu cầu, slot schema, file, template
-- =============================================================================

-- Sổ văn bản (ADR-011). Mọi giá trị ảnh hưởng tới chuỗi số nằm ở
-- document_register_format, không ở đây.
CREATE TABLE document_register (
    id            uuid        PRIMARY KEY,
    code          text        NOT NULL,
    name          text        NOT NULL,
    reset_policy  text        NOT NULL,
    is_active     boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    row_version   integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_document_register_code UNIQUE (code),
    CONSTRAINT ck_document_register_reset_policy CHECK (reset_policy IN ('YEARLY', 'NEVER'))
);

-- Mẫu định dạng theo (sổ, dải). Chỉ thêm, không sửa: đổi định dạng là thêm
-- dòng mới với effective_from mới. Giá trị cụ thể: A-009.
CREATE TABLE document_register_format (
    id                    uuid        PRIMARY KEY,
    document_register_id  uuid        NOT NULL REFERENCES document_register (id),
    series                text        NOT NULL,
    format_pattern        text        NOT NULL,
    symbol                text        NOT NULL,
    seq_min_digits        smallint    NOT NULL DEFAULT 1,
    effective_from        timestamptz NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_register_format_effective UNIQUE (document_register_id, series, effective_from),
    CONSTRAINT uq_register_format_id_scope UNIQUE (id, document_register_id, series),
    CONSTRAINT ck_register_format_series CHECK (series IN ('TRIAL', 'OFFICIAL')),
    CONSTRAINT ck_register_format_has_seq CHECK (strpos(format_pattern, '{seq}') > 0),
    CONSTRAINT ck_register_format_symbol_not_blank CHECK (btrim(symbol) <> ''),
    CONSTRAINT ck_register_format_seq_digits CHECK (seq_min_digits >= 1)
);

-- Bộ đếm: một dòng cho mỗi (sổ, dải, kỳ). Tăng bằng UPDATE khoá dòng trong
-- giao dịch cấp số ngắn (ADR-011).
CREATE TABLE document_register_counter (
    document_register_id  uuid        NOT NULL REFERENCES document_register (id),
    series                text        NOT NULL,
    period_key            text        NOT NULL,
    next_seq              bigint      NOT NULL DEFAULT 1,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_register_id, series, period_key),
    CONSTRAINT ck_register_counter_series CHECK (series IN ('TRIAL', 'OFFICIAL')),
    CONSTRAINT ck_register_counter_next_seq CHECK (next_seq >= 1),
    CONSTRAINT ck_register_counter_period CHECK (period_key ~ '^([0-9]{4}|ALL)$')
);

CREATE TABLE request_type (
    code                   text        PRIMARY KEY,
    name_vi                text        NOT NULL,
    description            text        NOT NULL,
    support_status         text        NOT NULL,
    artifact_kind          text        NOT NULL,
    requires_seal_default  boolean,
    seal_type_default      text,
    document_register_id   uuid        REFERENCES document_register (id),
    sla_target             interval,                           -- TBD, A-002
    example_phrases        text[]      NOT NULL DEFAULT '{}',  -- INT; đầu vào request_type_catalog
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    row_version            integer     NOT NULL DEFAULT 1,
    CONSTRAINT ck_request_type_code CHECK (code ~ '^[A-Z][A-Z_]*$'),
    CONSTRAINT ck_request_type_support_status
        CHECK (support_status IN ('SUPPORTED', 'KNOWN_UNSUPPORTED')),
    CONSTRAINT ck_request_type_artifact_kind
        CHECK (artifact_kind IN ('DOCUMENT', 'ROOM_BOOKING', 'SEAL_ACTION')),
    CONSTRAINT ck_request_type_seal_type_default
        CHECK (seal_type_default IS NULL
               OR seal_type_default IN ('ORGANIZATION_ROUND', 'TITLE_STAMP', 'OVERLAP_STAMP', 'EDGE_STAMP')),
    CONSTRAINT ck_request_type_seal_default_complete
        CHECK (requires_seal_default IS NOT TRUE OR seal_type_default IS NOT NULL),
    CONSTRAINT ck_request_type_supported_document_has_register
        CHECK (artifact_kind <> 'DOCUMENT' OR support_status <> 'SUPPORTED'
               OR document_register_id IS NOT NULL)
);

-- Slot schema. Không version (mục Bảng chi tiết của 04-data.md, P5).
-- sensitivity là phân loại HIỆN HÀNH; luật xoá khi EXPIRED đọc cột này lúc xoá.
CREATE TABLE slot_definition (
    request_type_code  text        NOT NULL REFERENCES request_type (code),
    slot_name          text        NOT NULL,
    data_type          text        NOT NULL,
    source             text        NOT NULL,
    sensitivity        text        NOT NULL,
    is_required        boolean     NOT NULL,
    validation_rules   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    description        text        NOT NULL,                   -- INT; đầu vào slot_specs
    display_order      smallint    NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    row_version        integer     NOT NULL DEFAULT 1,
    PRIMARY KEY (request_type_code, slot_name),
    CONSTRAINT ck_slot_definition_name CHECK (slot_name ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_slot_definition_data_type
        CHECK (data_type IN ('STRING', 'TEXT', 'INT', 'DATE', 'TIMESTAMP', 'ENUM', 'LIST', 'BOOL', 'FILE')),
    CONSTRAINT ck_slot_definition_source
        CHECK (source IN ('USER_INPUT', 'HR_PROFILE', 'RESOURCE_CATALOG', 'UPLOAD', 'SYSTEM')),
    CONSTRAINT ck_slot_definition_sensitivity CHECK (sensitivity IN ('INT', 'PER', 'RES'))
);

-- Sổ giành khoá ghi-một-lần cho object_storage (A-021, mục Lưu trữ file và bất
-- biến bản render của 04-data.md). Không có quyền UPDATE: một claim không bao giờ bị đổi chủ.
CREATE TABLE stored_object (
    object_key        text        PRIMARY KEY,
    purpose           text        NOT NULL,
    content_type      text        NOT NULL,
    claim_token       uuid        NOT NULL,
    claimed_at        timestamptz NOT NULL DEFAULT now(),
    lease_expires_at  timestamptz NOT NULL,
    CONSTRAINT uq_stored_object_claim UNIQUE (object_key, claim_token),
    CONSTRAINT ck_stored_object_key_not_blank CHECK (btrim(object_key) <> ''),
    CONSTRAINT ck_stored_object_purpose
        CHECK (purpose IN ('TEMPLATE_SOURCE', 'RENDER_DOCX', 'RENDER_PDF', 'PROCEDURE_SOURCE')),
    CONSTRAINT ck_stored_object_lease CHECK (lease_expires_at > claimed_at)
);

-- Kết quả ghi, ghi đúng một lần (khoá chính). Chỉ chủ claim commit được:
-- khoá ngoại ghép (object_key, committed_claim_token).
CREATE TABLE stored_object_commit (
    object_key             text        PRIMARY KEY,
    committed_claim_token  uuid        NOT NULL,
    checksum_sha256        bytea       NOT NULL,
    size_bytes             bigint      NOT NULL,
    committed_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_stored_object_commit_claim
        FOREIGN KEY (object_key, committed_claim_token)
        REFERENCES stored_object (object_key, claim_token),
    CONSTRAINT ck_stored_object_commit_checksum CHECK (octet_length(checksum_sha256) = 32),
    CONSTRAINT ck_stored_object_commit_size CHECK (size_bytes >= 0)
);

CREATE TABLE template (
    id                 uuid        PRIMARY KEY,
    code               text        NOT NULL,
    request_type_code  text        NOT NULL REFERENCES request_type (code),
    name               text        NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    row_version        integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_template_code UNIQUE (code)
);

-- Phiên bản template. Bản gốc bất biến qua stored_object_commit. Danh mục biến
-- và danh sách input tự khai của từng biến nằm dưới đây, trên phiên bản.
CREATE TABLE template_version (
    id                       uuid        PRIMARY KEY,
    template_id              uuid        NOT NULL REFERENCES template (id),
    version_no               integer     NOT NULL,
    status                   text        NOT NULL,
    source_object_key        text        NOT NULL REFERENCES stored_object_commit (object_key),
    uploaded_by_employee_id  uuid        NOT NULL REFERENCES employee (id),
    required_fonts           text[]      NOT NULL,            -- manifest font của phiên bản (ADR-015, A-058)
    activated_at             timestamptz,
    retired_at               timestamptz,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
    row_version              integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_template_version_no UNIQUE (template_id, version_no),
    CONSTRAINT ck_template_version_fonts CHECK (cardinality(required_fonts) >= 1),
    CONSTRAINT ck_template_version_no CHECK (version_no >= 1),
    CONSTRAINT ck_template_version_status CHECK (status IN ('UPLOADED', 'ACTIVE', 'RETIRED')),
    CONSTRAINT ck_template_version_activated
        CHECK (status = 'UPLOADED' OR activated_at IS NOT NULL),
    CONSTRAINT ck_template_version_retired
        CHECK ((status = 'RETIRED') = (retired_at IS NOT NULL))
);

CREATE TABLE template_variable (
    template_version_id  uuid     NOT NULL REFERENCES template_version (id),
    variable_name        text     NOT NULL,
    kind                 text     NOT NULL,
    source_slot_name     text,
    fill_after_approval  boolean  NOT NULL DEFAULT false,
    variable_guidance    text,                                -- INT
    max_length           integer,
    PRIMARY KEY (template_version_id, variable_name),
    CONSTRAINT uq_template_variable_kind UNIQUE (template_version_id, variable_name, kind),
    CONSTRAINT ck_template_variable_name CHECK (variable_name ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_template_variable_kind CHECK (kind IN ('DIRECT_SLOT', 'FREE_CONTENT', 'SYSTEM')),
    CONSTRAINT ck_template_variable_direct_has_slot
        CHECK ((kind = 'DIRECT_SLOT') = (source_slot_name IS NOT NULL)),
    CONSTRAINT ck_template_variable_post_approval_is_system
        CHECK (NOT fill_after_approval OR kind = 'SYSTEM'),
    CONSTRAINT ck_template_variable_free_content_spec
        CHECK (kind <> 'FREE_CONTENT' OR (variable_guidance IS NOT NULL AND max_length IS NOT NULL)),
    CONSTRAINT ck_template_variable_max_length CHECK (max_length IS NULL OR max_length > 0)
);

-- Danh sách input tự khai của biến nội dung tự do — danh sách nạp của INV-03,
-- đồng thời là đồ thị phụ thuộc slot → biến của ADR-009.
CREATE TABLE template_variable_input (
    template_version_id  uuid NOT NULL,
    variable_name        text NOT NULL,
    variable_kind        text NOT NULL DEFAULT 'FREE_CONTENT',
    slot_name            text NOT NULL,
    PRIMARY KEY (template_version_id, variable_name, slot_name),
    CONSTRAINT fk_template_variable_input_variable
        FOREIGN KEY (template_version_id, variable_name, variable_kind)
        REFERENCES template_variable (template_version_id, variable_name, kind),
    CONSTRAINT ck_template_variable_input_only_free_content CHECK (variable_kind = 'FREE_CONTENT')
);


-- =============================================================================
-- C. Hội thoại và request
-- =============================================================================

CREATE TABLE chat_session (
    id               uuid        PRIMARY KEY,
    employee_id      uuid        NOT NULL REFERENCES employee (id),
    status           text        NOT NULL DEFAULT 'OPEN',
    opened_at        timestamptz NOT NULL DEFAULT now(),
    last_message_at  timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    close_reason     text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    row_version      integer     NOT NULL DEFAULT 1,
    CONSTRAINT ck_chat_session_status CHECK (status IN ('OPEN', 'CLOSED')),
    CONSTRAINT ck_chat_session_close_reason
        CHECK (close_reason IS NULL OR close_reason IN ('IDLE_TIMEOUT', 'REQUEST_EXPIRED')),
    CONSTRAINT ck_chat_session_closed_complete
        CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL AND close_reason IS NOT NULL))
);

CREATE TABLE request (
    id                          uuid        PRIMARY KEY,
    request_type_code           text        NOT NULL REFERENCES request_type (code),
    status                      text        NOT NULL,
    status_changed_at           timestamptz NOT NULL DEFAULT now(),
    chat_session_id             uuid        REFERENCES chat_session (id),
    created_by_employee_id      uuid        NOT NULL REFERENCES employee (id),
    beneficiary_employee_id     uuid        NOT NULL REFERENCES employee (id),
    delegation_id               uuid        REFERENCES delegation (id),
    replaces_request_id         uuid        REFERENCES request (id),
    opened_by_message_id        uuid,                          -- idempotency của request_open; FK sau chat_message
    needs_info_asked_at         timestamptz,                   -- mốc đếm của A-014
    expires_at                  timestamptz,                   -- thời hạn TBD, A-014
    submitted_at                timestamptz,
    due_at                      timestamptz,                   -- SLA TBD, A-002
    closed_at                   timestamptz,
    retained_values_cleared_at  timestamptz,                   -- mục Lưu trữ và xoá dữ liệu cá nhân
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),
    row_version                 integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_request_id_type UNIQUE (id, request_type_code),
    CONSTRAINT uq_request_opened_by_message UNIQUE (opened_by_message_id),
    CONSTRAINT ck_request_status CHECK (status IN (
        'DRAFT', 'NEEDS_INFO', 'SUBMITTED', 'IN_REVIEW', 'CHANGES_REQUESTED',
        'APPROVED', 'FULFILLED', 'REJECTED', 'CANCELLED', 'EXPIRED')),
    CONSTRAINT ck_request_closed_iff_terminal
        CHECK ((status IN ('FULFILLED', 'REJECTED', 'CANCELLED', 'EXPIRED')) = (closed_at IS NOT NULL)),
    CONSTRAINT ck_request_needs_info_anchor
        CHECK (status <> 'NEEDS_INFO' OR needs_info_asked_at IS NOT NULL),
    CONSTRAINT ck_request_retained_clear_only_expired
        CHECK (retained_values_cleared_at IS NULL OR status = 'EXPIRED'),
    CONSTRAINT ck_request_not_replacing_itself
        CHECK (replaces_request_id IS NULL OR replaces_request_id <> id)
);

-- Văn bản tin nhắn xếp RES bằng luật chung (mục Memory của 03-agents.md),
-- không qua slot_sensitivity.
CREATE TABLE chat_message (
    id                 uuid        PRIMARY KEY,
    chat_session_id    uuid        NOT NULL REFERENCES chat_session (id),
    seq                integer     NOT NULL,
    author             text        NOT NULL,
    request_id         uuid        REFERENCES request (id),
    body               text,                                   -- RES
    reply_template_id  text,
    retrieval_query    text,                                   -- RES
    content_erased_at  timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_chat_message_seq UNIQUE (chat_session_id, seq),
    CONSTRAINT ck_chat_message_seq CHECK (seq >= 1),
    CONSTRAINT ck_chat_message_author CHECK (author IN ('EMPLOYEE', 'AGENT')),
    CONSTRAINT ck_chat_message_erased_means_empty
        CHECK (content_erased_at IS NULL OR (body IS NULL AND retrieval_query IS NULL)),
    CONSTRAINT ck_chat_message_body_until_erased
        CHECK (content_erased_at IS NOT NULL OR body IS NOT NULL),
    CONSTRAINT ck_chat_message_template_only_agent
        CHECK (author = 'AGENT' OR reply_template_id IS NULL),
    CONSTRAINT ck_chat_message_query_only_employee
        CHECK (author = 'EMPLOYEE' OR retrieval_query IS NULL)
);

ALTER TABLE request
    ADD CONSTRAINT fk_request_opened_by_message
        FOREIGN KEY (opened_by_message_id) REFERENCES chat_message (id);

-- Một dòng mỗi slot. KHÔNG có cột chụp độ nhạy (J3): luật xoá đọc
-- slot_definition.sensitivity hiện hành. Bằng chứng là vị trí trong
-- chat_message.body, không phải bản chép.
CREATE TABLE request_slot (
    request_id                uuid        NOT NULL,
    request_type_code         text        NOT NULL,
    slot_name                 text        NOT NULL,
    value                     jsonb,
    value_status              text        NOT NULL,
    provenance_source         text,                            -- employee.source lúc đề xuất
    provenance_synced_at      timestamptz,                     -- employee.synced_at lúc đề xuất
    proposed_from_request_id  uuid        REFERENCES request (id),
    evidence_message_id       uuid        REFERENCES chat_message (id),
    evidence_span             int4range,
    confirmed_at              timestamptz,
    value_erased_at           timestamptz,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    row_version               integer     NOT NULL DEFAULT 1,
    PRIMARY KEY (request_id, slot_name),
    CONSTRAINT fk_request_slot_request_type
        FOREIGN KEY (request_id, request_type_code) REFERENCES request (id, request_type_code),
    CONSTRAINT fk_request_slot_definition
        FOREIGN KEY (request_type_code, slot_name) REFERENCES slot_definition (request_type_code, slot_name),
    CONSTRAINT ck_request_slot_value_status
        CHECK (value_status IN ('PROVIDED', 'PROPOSED', 'CONFIRMED', 'SYSTEM_SET', 'ERASED')),
    CONSTRAINT ck_request_slot_erased_iff_status
        CHECK ((value_status = 'ERASED') = (value_erased_at IS NOT NULL)),
    CONSTRAINT ck_request_slot_value_presence
        CHECK ((value_status = 'ERASED') = (value IS NULL)),
    CONSTRAINT ck_request_slot_confirmed_has_time
        CHECK (value_status <> 'CONFIRMED' OR confirmed_at IS NOT NULL),
    CONSTRAINT ck_request_slot_provided_has_evidence
        CHECK (value_status <> 'PROVIDED' OR evidence_message_id IS NOT NULL),
    CONSTRAINT ck_request_slot_evidence_pair
        CHECK ((evidence_message_id IS NULL) = (evidence_span IS NULL)),
    CONSTRAINT ck_request_slot_evidence_span
        CHECK (evidence_span IS NULL OR (NOT isempty(evidence_span) AND lower(evidence_span) >= 0)),
    CONSTRAINT ck_request_slot_provenance_pair
        CHECK ((provenance_source IS NULL) = (provenance_synced_at IS NULL)),
    CONSTRAINT ck_request_slot_not_self_proposed
        CHECK (proposed_from_request_id IS NULL OR proposed_from_request_id <> request_id)
);

-- =============================================================================
-- D. Văn bản, nội dung tự do, bản render
-- =============================================================================

CREATE TABLE document (
    id                        uuid        PRIMARY KEY,
    request_id                uuid        NOT NULL REFERENCES request (id),
    template_version_id       uuid        NOT NULL REFERENCES template_version (id),
    status                    text        NOT NULL,
    status_changed_at         timestamptz NOT NULL DEFAULT now(),
    operating_mode            text        NOT NULL,                    -- ghim lúc tạo DRAFT (INV-01)
    register_series           text        GENERATED ALWAYS AS (
                                  CASE WHEN operating_mode = 'NON_PRODUCTION' THEN 'TRIAL' ELSE 'OFFICIAL' END
                              ) STORED,
    requires_seal             boolean,
    seal_type                 text,
    revision_round            integer     NOT NULL DEFAULT 0,
    current_draft_render_id   uuid,                                    -- FK thêm ở cuối nhóm E
    approved_content_hash     bytea,
    approved_decision_id      uuid,                                    -- FK thêm ở cuối nhóm E
    approved_render_id        uuid,                                    -- FK thêm ở cuối nhóm E
    signer_employee_id        uuid        REFERENCES employee (id),    -- biến signer_user_id
    final_render_id           uuid,                                    -- FK thêm ở cuối nhóm E
    issued_register_entry_id  uuid,                                    -- FK thêm ở cuối nhóm E
    issued_date               date,
    issued_at                 timestamptz,
    supersedes_document_id    uuid        REFERENCES document (id),
    archived_from_status      text,
    archive_reason            text,                                    -- bảng mã: Phase 8
    archived_at               timestamptz,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    row_version               integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_document_id_mode UNIQUE (id, operating_mode),
    CONSTRAINT uq_document_id_series UNIQUE (id, register_series),
    CONSTRAINT uq_document_supersedes UNIQUE (supersedes_document_id),
    CONSTRAINT ck_document_status CHECK (status IN (
        'DRAFT', 'PENDING_APPROVAL', 'CHANGES_REQUESTED', 'REJECTED', 'APPROVED',
        'PENDING_SIGNATURE', 'SIGNED', 'PENDING_SEAL', 'SEALED', 'ISSUED',
        'REVOKED', 'SUPERSEDED', 'ARCHIVED')),
    CONSTRAINT ck_document_operating_mode CHECK (operating_mode IN ('NON_PRODUCTION', 'PRODUCTION')),
    CONSTRAINT ck_document_seal_type
        CHECK (seal_type IS NULL
               OR seal_type IN ('ORGANIZATION_ROUND', 'TITLE_STAMP', 'OVERLAP_STAMP', 'EDGE_STAMP')),
    CONSTRAINT ck_document_seal_complete CHECK (requires_seal IS NOT TRUE OR seal_type IS NOT NULL),
    CONSTRAINT ck_document_seal_determined
        CHECK (status IN ('DRAFT', 'CHANGES_REQUESTED') OR requires_seal IS NOT NULL),
    CONSTRAINT ck_document_seal_path
        CHECK (status NOT IN ('PENDING_SEAL', 'SEALED') OR requires_seal IS TRUE),
    CONSTRAINT ck_document_revision_round CHECK (revision_round >= 0),
    CONSTRAINT ck_document_approved_complete
        CHECK (status NOT IN ('APPROVED', 'PENDING_SIGNATURE', 'SIGNED', 'PENDING_SEAL', 'SEALED',
                              'ISSUED', 'REVOKED', 'SUPERSEDED')
               OR (approved_content_hash IS NOT NULL
                   AND approved_decision_id IS NOT NULL
                   AND approved_render_id IS NOT NULL)),
    CONSTRAINT ck_document_signer_assigned
        CHECK (status NOT IN ('PENDING_SIGNATURE', 'SIGNED', 'PENDING_SEAL', 'SEALED',
                              'ISSUED', 'REVOKED', 'SUPERSEDED')
               OR signer_employee_id IS NOT NULL),
    CONSTRAINT ck_document_issued_complete
        CHECK (status NOT IN ('ISSUED', 'REVOKED', 'SUPERSEDED')
               OR (issued_register_entry_id IS NOT NULL
                   AND final_render_id IS NOT NULL
                   AND issued_date IS NOT NULL
                   AND issued_at IS NOT NULL)),
    CONSTRAINT ck_document_number_only_after_issue
        CHECK (issued_register_entry_id IS NULL
               OR status IN ('ISSUED', 'REVOKED', 'SUPERSEDED', 'ARCHIVED')),
    CONSTRAINT ck_document_archived_complete
        CHECK ((status = 'ARCHIVED') = (archived_from_status IS NOT NULL AND archived_at IS NOT NULL)),
    CONSTRAINT ck_document_archived_from
        CHECK (archived_from_status IS NULL
               OR archived_from_status IN ('ISSUED', 'REVOKED', 'SUPERSEDED', 'REJECTED', 'CHANGES_REQUESTED')),
    -- Đường vào ARCHIVED thứ hai — bản nháp bỏ vì request bị huỷ (A-035) — bắt buộc có mã lý do.
    CONSTRAINT ck_document_archive_reason_abandoned_draft
        CHECK (archived_from_status IS DISTINCT FROM 'CHANGES_REQUESTED'
               OR (archive_reason IS NOT NULL AND btrim(archive_reason) <> '')),
    CONSTRAINT ck_document_not_superseding_itself
        CHECK (supersedes_document_id IS NULL OR supersedes_document_id <> id)
);

-- Văn bản của biến nội dung tự do, mỗi lần sinh một dòng. Giá trị hiện hành của
-- một biến = dòng PASSED có (revision_round, attempt_no) lớn nhất.
CREATE TABLE document_free_content (
    id                     uuid        PRIMARY KEY,
    document_id            uuid        NOT NULL REFERENCES document (id),
    variable_name          text        NOT NULL,
    revision_round         integer     NOT NULL,
    attempt_no             smallint    NOT NULL,
    template_version_id    uuid        NOT NULL REFERENCES template_version (id),  -- dựng lại danh sách input (P5)
    body                   text        NOT NULL,                       -- RES (dẫn xuất từ slot RES)
    validation_outcome     text        NOT NULL,
    prompt_module_version  text        NOT NULL,
    input_fingerprint      bytea       NOT NULL,                       -- hash có khoá (ADR-009)
    fingerprint_key_id     text        NOT NULL,
    generated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_free_content_attempt UNIQUE (document_id, variable_name, revision_round, attempt_no),
    CONSTRAINT ck_free_content_round CHECK (revision_round >= 0),
    CONSTRAINT ck_free_content_attempt CHECK (attempt_no IN (1, 2)),
    CONSTRAINT ck_free_content_outcome CHECK (validation_outcome IN ('PASSED', 'FAILED'))
);

-- Bản ghi nghiệp vụ "document này có những bản render nào". Chỉ thêm và xoá,
-- không sửa; dòng bị ghim không xoá được (document_render_pin).
CREATE TABLE document_render (
    id                   uuid        PRIMARY KEY,
    document_id          uuid        NOT NULL,
    operating_mode       text        NOT NULL,
    render_kind          text        NOT NULL,
    input_hash           bytea       NOT NULL,
    template_version_id  uuid        NOT NULL REFERENCES template_version (id),
    revision_round       integer     NOT NULL,
    docx_object_key      text        NOT NULL REFERENCES stored_object_commit (object_key),
    pdf_object_key       text        NOT NULL REFERENCES stored_object_commit (object_key),
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_render_input UNIQUE (document_id, render_kind, input_hash),
    CONSTRAINT uq_document_render_id_document UNIQUE (id, document_id),
    -- Watermark theo chế độ đã ghim: bản render không thể mang chế độ khác document.
    CONSTRAINT fk_document_render_mode
        FOREIGN KEY (document_id, operating_mode) REFERENCES document (id, operating_mode),
    CONSTRAINT ck_document_render_kind CHECK (render_kind IN ('DRAFT', 'FINAL')),
    CONSTRAINT ck_document_render_two_files CHECK (docx_object_key <> pdf_object_key),
    CONSTRAINT ck_document_render_round CHECK (revision_round >= 0)
);


-- =============================================================================
-- E. Duyệt, quyết định, sổ số, sổ dấu
-- =============================================================================

-- Việc YÊU CẦU một người hành động. Kết quả hành động nằm ở decision_record.
CREATE TABLE approval_step (
    id                      uuid        PRIMARY KEY,
    document_id             uuid        REFERENCES document (id),
    room_booking_id         uuid,                                      -- [Should]; FK ở nhóm H
    step_kind               text        NOT NULL,
    level                   smallint    NOT NULL DEFAULT 1,            -- nhiều cấp: [Should]
    revision_round          integer     NOT NULL DEFAULT 0,
    assignee_employee_id    uuid        REFERENCES employee (id),
    delegation_id           uuid        REFERENCES delegation (id),
    status                  text        NOT NULL DEFAULT 'OPEN',
    opened_at               timestamptz NOT NULL DEFAULT now(),
    due_at                  timestamptz,                               -- SLA TBD, A-002
    closed_at               timestamptz,
    self_approval_expected  boolean     NOT NULL DEFAULT false,
    self_approved           boolean     NOT NULL DEFAULT false,
    self_approval_reason    text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    row_version             integer     NOT NULL DEFAULT 1,
    CONSTRAINT ck_approval_step_one_subject CHECK (num_nonnulls(document_id, room_booking_id) = 1),
    CONSTRAINT ck_approval_step_kind
        CHECK (step_kind IN ('CONTENT_REVIEW', 'SIGNATURE', 'SEAL', 'BOOKING_CONFIRM')),
    CONSTRAINT ck_approval_step_booking_subject
        CHECK ((step_kind = 'BOOKING_CONFIRM') = (room_booking_id IS NOT NULL)),
    CONSTRAINT ck_approval_step_level CHECK (level >= 1),
    CONSTRAINT ck_approval_step_round CHECK (revision_round >= 0),
    CONSTRAINT ck_approval_step_status CHECK (status IN ('OPEN', 'DECIDED', 'CANCELLED')),
    CONSTRAINT ck_approval_step_closed_iff_not_open CHECK ((status = 'OPEN') = (closed_at IS NULL)),
    -- D-006: tự duyệt luôn kèm lý do không rỗng; lý do chỉ tồn tại khi tự duyệt.
    CONSTRAINT ck_approval_step_self_approval_reason
        CHECK (self_approved = (self_approval_reason IS NOT NULL)),
    CONSTRAINT ck_approval_step_self_approval_not_blank
        CHECK (self_approval_reason IS NULL OR btrim(self_approval_reason) <> ''),
    CONSTRAINT ck_approval_step_self_approved_decided
        CHECK (NOT self_approved OR status = 'DECIDED')
);

-- Bản ghi dừng có kiểm soát (document_halt_record). Chỉ mang mã.
CREATE TABLE document_halt (
    id              uuid        PRIMARY KEY,
    document_id     uuid        NOT NULL REFERENCES document (id),
    reason_code     text        NOT NULL,                              -- bảng mã: Phase 8
    at_node         text        NOT NULL,
    revision_round  integer     NOT NULL,
    trace_id        text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_halt_once UNIQUE (document_id, at_node, revision_round),
    CONSTRAINT ck_document_halt_reason_code CHECK (reason_code ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT ck_document_halt_node CHECK (at_node ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_document_halt_round CHECK (revision_round >= 0)
);

-- Hành động của người thật tại một thao tác cổng. Bất biến; chỉ mang mã và
-- tham chiếu. Văn bản lý do (có thể mang PII) nằm ở decision_record_text.
CREATE TABLE decision_record (
    id                 uuid        PRIMARY KEY,
    kind               text        NOT NULL,
    actor_employee_id  uuid        NOT NULL REFERENCES employee (id),
    delegation_id      uuid        REFERENCES delegation (id),
    request_id         uuid        NOT NULL REFERENCES request (id),
    document_id        uuid        REFERENCES document (id),
    approval_step_id   uuid        REFERENCES approval_step (id),
    document_halt_id   uuid        REFERENCES document_halt (id),
    change_scope       text,
    change_targets     text[],
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_decision_record_id_document UNIQUE (id, document_id),
    CONSTRAINT ck_decision_record_kind CHECK (kind IN (
        'APPROVED', 'CHANGES_REQUESTED', 'REJECTED', 'SIGNED', 'SEALED', 'ISSUE_ORDERED',
        'SUBMITTED', 'RESUBMITTED', 'REQUEST_CANCELLED', 'TAKEOVER_RESOLVED',
        'REVOKE_INITIATED', 'REVOKE_CONFIRMED', 'BOOKING_CONFIRMED')),
    CONSTRAINT ck_decision_record_change_scope_iff_changes
        CHECK ((kind = 'CHANGES_REQUESTED') = (change_scope IS NOT NULL)),
    CONSTRAINT ck_decision_record_change_scope_value
        CHECK (change_scope IS NULL OR change_scope IN ('FREE_CONTENT', 'SLOT_DATA')),
    CONSTRAINT ck_decision_record_targets_only_changes
        CHECK (change_targets IS NULL OR kind = 'CHANGES_REQUESTED'),
    CONSTRAINT ck_decision_record_document_kinds
        CHECK (kind NOT IN ('APPROVED', 'CHANGES_REQUESTED', 'SIGNED', 'SEALED', 'ISSUE_ORDERED',
                            'TAKEOVER_RESOLVED', 'REVOKE_INITIATED', 'REVOKE_CONFIRMED')
               OR document_id IS NOT NULL),
    CONSTRAINT ck_decision_record_step_kinds
        CHECK (kind NOT IN ('APPROVED', 'CHANGES_REQUESTED', 'SIGNED', 'SEALED', 'BOOKING_CONFIRMED')
               OR approval_step_id IS NOT NULL),
    CONSTRAINT ck_decision_record_takeover_has_halt
        CHECK ((kind = 'TAKEOVER_RESOLVED') = (document_halt_id IS NOT NULL))
);

-- Văn bản lý do: ghi một lần, xoá được khi hết hạn lưu (A-010), không sửa được.
CREATE TABLE decision_record_text (
    decision_record_id  uuid        NOT NULL REFERENCES decision_record (id),
    text_kind           text        NOT NULL,
    body                text        NOT NULL,                          -- RES
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (decision_record_id, text_kind),
    CONSTRAINT ck_decision_record_text_kind
        CHECK (text_kind IN ('CHANGE_REASON', 'REJECTION_REASON', 'REVOCATION_REASON')),
    CONSTRAINT ck_decision_record_text_not_blank CHECK (btrim(body) <> '')
);

-- Ghim bản render. Không có quyền UPDATE/DELETE: ghim là một chiều. Khoá ngoại
-- (mặc định NO ACTION) làm dòng document_render bị ghim không xoá được.
CREATE TABLE document_render_pin (
    render_id           uuid        PRIMARY KEY REFERENCES document_render (id),
    pin_reason          text        NOT NULL,
    decision_record_id  uuid        NOT NULL REFERENCES decision_record (id),
    pinned_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_document_render_pin_reason CHECK (pin_reason IN ('APPROVED_CONTENT', 'ISSUED'))
);

-- Dòng sổ văn bản (ADR-011). Số đã cấp lưu nguyên dạng chuỗi.
CREATE TABLE document_register_entry (
    id                    uuid        PRIMARY KEY,
    document_register_id  uuid        NOT NULL,
    series                text        NOT NULL,
    period_key            text        NOT NULL,
    seq                   bigint      NOT NULL,
    formatted_number      text        NOT NULL,
    format_id             uuid        NOT NULL,
    document_id           uuid        NOT NULL,
    issue_decision_id     uuid        NOT NULL REFERENCES decision_record (id),
    status                text        NOT NULL DEFAULT 'ASSIGNED',
    assigned_at           timestamptz NOT NULL DEFAULT now(),
    voided_at             timestamptz,
    void_reason           text,
    CONSTRAINT uq_register_entry_seq UNIQUE (document_register_id, series, period_key, seq),
    CONSTRAINT uq_register_entry_number UNIQUE (document_register_id, series, formatted_number),
    CONSTRAINT uq_register_entry_id_document UNIQUE (id, document_id),
    CONSTRAINT fk_register_entry_counter
        FOREIGN KEY (document_register_id, series, period_key)
        REFERENCES document_register_counter (document_register_id, series, period_key),
    CONSTRAINT fk_register_entry_format
        FOREIGN KEY (format_id, document_register_id, series)
        REFERENCES document_register_format (id, document_register_id, series),
    -- D-009: dải của số buộc khớp chế độ đã ghim trên document.
    CONSTRAINT fk_register_entry_document_series
        FOREIGN KEY (document_id, series) REFERENCES document (id, register_series),
    CONSTRAINT ck_register_entry_seq CHECK (seq >= 1),
    CONSTRAINT ck_register_entry_status CHECK (status IN ('ASSIGNED', 'VOIDED')),
    CONSTRAINT ck_register_entry_voided_time CHECK ((status = 'VOIDED') = (voided_at IS NOT NULL)),
    CONSTRAINT ck_register_entry_void_reason
        CHECK (status <> 'VOIDED' OR (void_reason IS NOT NULL AND btrim(void_reason) <> ''))
);

-- Sổ theo dõi con dấu = toàn bộ bảng này, sắp theo sealed_at. Không chung dãy
-- số với document_register. Mỗi loại dấu một dòng, một quyết định (EC-SR-04).
CREATE TABLE seal_action (
    id                  uuid        PRIMARY KEY,
    document_id         uuid        NOT NULL,          -- external_document: [Could], chưa có DDL
    operating_mode      text        NOT NULL,          -- NON_PRODUCTION = dấu thử nghiệm (D-009)
    seal_type           text        NOT NULL,
    copies_count        integer     NOT NULL,
    page_count          integer,
    decision_record_id  uuid        NOT NULL REFERENCES decision_record (id),
    sealed_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_seal_action_decision UNIQUE (decision_record_id),
    CONSTRAINT fk_seal_action_document_mode
        FOREIGN KEY (document_id, operating_mode) REFERENCES document (id, operating_mode),
    CONSTRAINT ck_seal_action_type
        CHECK (seal_type IN ('ORGANIZATION_ROUND', 'TITLE_STAMP', 'OVERLAP_STAMP', 'EDGE_STAMP')),
    CONSTRAINT ck_seal_action_copies CHECK (copies_count >= 1),
    CONSTRAINT ck_seal_action_page_count CHECK (page_count IS NULL OR page_count >= 1),
    CONSTRAINT ck_seal_action_edge_stamp CHECK (seal_type <> 'EDGE_STAMP' OR page_count >= 2)
);

-- Khoá ngoại của document tới các bảng tạo sau nó. Mỗi khoá ghép với id của
-- chính document: bản render, quyết định và dòng sổ được trỏ tới phải thuộc
-- đúng document này.
ALTER TABLE document
    ADD CONSTRAINT fk_document_current_draft_render
        FOREIGN KEY (current_draft_render_id, id) REFERENCES document_render (id, document_id),
    ADD CONSTRAINT fk_document_approved_render
        FOREIGN KEY (approved_render_id, id) REFERENCES document_render (id, document_id),
    ADD CONSTRAINT fk_document_final_render
        FOREIGN KEY (final_render_id, id) REFERENCES document_render (id, document_id),
    ADD CONSTRAINT fk_document_approved_decision
        FOREIGN KEY (approved_decision_id, id) REFERENCES decision_record (id, document_id),
    ADD CONSTRAINT fk_document_issued_register_entry
        FOREIGN KEY (issued_register_entry_id, id) REFERENCES document_register_entry (id, document_id);

-- =============================================================================
-- F. Kho quy trình và vector collection (ADR-002, ADR-012)
-- =============================================================================

CREATE TABLE procedure_document (
    id           uuid        PRIMARY KEY,
    code         text        NOT NULL,
    title        text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    row_version  integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_procedure_document_code UNIQUE (code)
);

CREATE TABLE procedure_document_version (
    id                       uuid        PRIMARY KEY,
    procedure_document_id    uuid        NOT NULL REFERENCES procedure_document (id),
    version_no               integer     NOT NULL,
    source_object_key        text        NOT NULL REFERENCES stored_object_commit (object_key),
    procedure_visibility     text        NOT NULL,
    department_scope         text[],                         -- mã employee.department_code
    effective_from           date        NOT NULL,
    is_active                boolean     NOT NULL DEFAULT false,
    activated_at             timestamptz,
    deactivated_at           timestamptz,
    ingested_by_employee_id  uuid        NOT NULL REFERENCES employee (id),
    pii_free_attested        boolean     NOT NULL,           -- cam kết của người nạp (A-033)
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
    row_version              integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_procedure_version_no UNIQUE (procedure_document_id, version_no),
    CONSTRAINT ck_procedure_version_no CHECK (version_no >= 1),
    CONSTRAINT ck_procedure_visibility CHECK (procedure_visibility IN ('ORG_WIDE', 'DEPARTMENT_ONLY')),
    CONSTRAINT ck_procedure_scope_matches_visibility
        CHECK ((procedure_visibility = 'ORG_WIDE') = (department_scope IS NULL)),
    CONSTRAINT ck_procedure_scope_not_empty
        CHECK (department_scope IS NULL OR cardinality(department_scope) >= 1),
    CONSTRAINT ck_procedure_pii_free_attested CHECK (pii_free_attested),
    CONSTRAINT ck_procedure_active_has_time CHECK (NOT is_active OR activated_at IS NOT NULL)
);

-- Đơn vị trích dẫn. body không chứa PII theo chính sách nạp kho.
CREATE TABLE procedure_chunk (
    id                             uuid        PRIMARY KEY,
    procedure_document_version_id  uuid        NOT NULL REFERENCES procedure_document_version (id),
    chunk_no                       integer     NOT NULL,
    heading_path                   text        NOT NULL,
    body                           text        NOT NULL,     -- văn bản nguyên văn để hiển thị
    normalized_text                text        NOT NULL,     -- chuẩn hoá Unicode và dấu thanh, do ứng dụng
    unaccented_text                text        NOT NULL,     -- dạng không dấu, tín hiệu phụ
    -- Kênh lexical trên full-text lõi của PostgreSQL, cấu hình 'simple'.
    -- Khả năng tách từ tiếng Việt và BM25: [CẦN XÁC MINH], A-030.
    lexical_tsv                    tsvector    GENERATED ALWAYS AS (
                                       to_tsvector('simple'::regconfig, normalized_text || ' ' || unaccented_text)
                                   ) STORED,
    created_at                     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_procedure_chunk_no UNIQUE (procedure_document_version_id, chunk_no),
    CONSTRAINT ck_procedure_chunk_no CHECK (chunk_no >= 1),
    CONSTRAINT ck_procedure_chunk_body_not_blank CHECK (btrim(body) <> '')
);

-- dimension là BẢN KHAI phải khớp n thật của cột embedding trong bảng
-- embedding_table; lệch thì api và queue_worker từ chối khởi động (ADR-012).
CREATE TABLE embedding_collection (
    id               uuid        PRIMARY KEY,
    code             text        NOT NULL,
    embedding_table  text        NOT NULL,
    model_id         text        NOT NULL,
    dimension        integer     NOT NULL,
    distance_metric  text        NOT NULL DEFAULT 'L2_UNIT_NORMALIZED',
    status           text        NOT NULL DEFAULT 'BUILDING',
    activated_at     timestamptz,
    retired_at       timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    row_version      integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_embedding_collection_code UNIQUE (code),
    CONSTRAINT uq_embedding_collection_table UNIQUE (embedding_table),
    CONSTRAINT ck_embedding_collection_table_name
        CHECK (embedding_table ~ '^procedure_chunk_embedding_v[0-9]+$'),
    CONSTRAINT ck_embedding_collection_dimension CHECK (dimension BETWEEN 1 AND 1024),  -- A-028
    CONSTRAINT ck_embedding_collection_metric CHECK (distance_metric IN ('L2_UNIT_NORMALIZED')),
    CONSTRAINT ck_embedding_collection_status CHECK (status IN ('BUILDING', 'ACTIVE', 'RETIRED')),
    CONSTRAINT ck_embedding_collection_activated CHECK (status = 'BUILDING' OR activated_at IS NOT NULL),
    CONSTRAINT ck_embedding_collection_retired CHECK ((status = 'RETIRED') = (retired_at IS NOT NULL))
);

-- Phiên bản collection 1: một model, một cột vector(1024) cố định (ADR-012).
-- Không có index ANN ở phiên bản này — tìm chính xác.
CREATE TABLE procedure_chunk_embedding_v1 (
    chunk_id       uuid          PRIMARY KEY REFERENCES procedure_chunk (id),
    collection_id  uuid          NOT NULL REFERENCES embedding_collection (id),
    embedding      vector(1024)  NOT NULL,                   -- đã chuẩn hoá độ dài đơn vị
    embedded_at    timestamptz   NOT NULL DEFAULT now()
);


-- =============================================================================
-- G. Vận hành, audit, chế độ vận hành
-- =============================================================================

-- Bảng job của queue_worker (ADR-004, ADR-010). payload chỉ mang tham chiếu.
CREATE TABLE job (
    id                   uuid        PRIMARY KEY,
    job_type             text        NOT NULL,
    payload              jsonb       NOT NULL DEFAULT '{}'::jsonb,
    subject_document_id  uuid        REFERENCES document (id),
    dedupe_key           text,
    status               text        NOT NULL DEFAULT 'QUEUED',
    attempts             integer     NOT NULL DEFAULT 0,
    max_attempts         integer     NOT NULL,                  -- giá trị: A-031
    run_after            timestamptz NOT NULL DEFAULT now(),
    locked_by            text,
    locked_at            timestamptz,
    lease_expires_at     timestamptz,
    enqueued_at          timestamptz NOT NULL DEFAULT now(),
    started_at           timestamptz,
    finished_at          timestamptz,
    last_error_code      text,
    CONSTRAINT ck_job_type CHECK (job_type IN (
        'render_document', 'resume_document_graph', 'finalize_issue',
        'checkpoint_purge', 'procedure_ingest', 'notification_send')),
    CONSTRAINT ck_job_status CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    CONSTRAINT ck_job_attempts CHECK (attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts),
    CONSTRAINT ck_job_running_has_lease
        CHECK ((status = 'RUNNING') = (locked_at IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CONSTRAINT ck_job_finished_iff_terminal
        CHECK ((status IN ('SUCCEEDED', 'FAILED')) = (finished_at IS NOT NULL)),
    CONSTRAINT ck_job_error_code CHECK (last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT ck_job_document_subject
        CHECK (job_type NOT IN ('resume_document_graph', 'finalize_issue') OR subject_document_id IS NOT NULL)
);

-- Sổ thread LangGraph, cạnh bảng checkpoint của thư viện. Nguồn cho
-- checkpoint_purge và cho hai dạng phát hiện thread kẹt.
CREATE TABLE graph_thread (
    thread_id             text        PRIMARY KEY,
    graph_name            text        NOT NULL,
    chat_session_id       uuid        REFERENCES chat_session (id),
    document_id           uuid        REFERENCES document (id),
    status                text        NOT NULL DEFAULT 'ACTIVE',
    waiting_at_node       text,
    state_schema_version  integer     NOT NULL,
    last_step_at          timestamptz NOT NULL DEFAULT now(),
    ended_at              timestamptz,
    purged_at             timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_graph_thread_chat_session UNIQUE (chat_session_id),
    CONSTRAINT uq_graph_thread_document UNIQUE (document_id),
    CONSTRAINT ck_graph_thread_graph CHECK (graph_name IN ('intake_graph', 'document_graph')),
    CONSTRAINT ck_graph_thread_intake_subject
        CHECK ((graph_name = 'intake_graph') = (chat_session_id IS NOT NULL)),
    CONSTRAINT ck_graph_thread_document_subject
        CHECK ((graph_name = 'document_graph') = (document_id IS NOT NULL)),
    CONSTRAINT ck_graph_thread_intake_id
        CHECK (graph_name <> 'intake_graph' OR thread_id = 'intake:' || chat_session_id::text),
    CONSTRAINT ck_graph_thread_document_id
        CHECK (graph_name <> 'document_graph' OR thread_id = 'document:' || document_id::text),
    CONSTRAINT ck_graph_thread_status CHECK (status IN ('ACTIVE', 'WAITING', 'ENDED', 'PURGED')),
    CONSTRAINT ck_graph_thread_waiting_node
        CHECK ((status = 'WAITING') = (waiting_at_node IS NOT NULL)),
    CONSTRAINT ck_graph_thread_interrupt_names
        CHECK (waiting_at_node IS NULL OR waiting_at_node IN (
            'await_content_review', 'await_signature', 'await_seal',
            'await_issue', 'await_resubmission', 'await_human_takeover')),
    CONSTRAINT ck_graph_thread_intake_never_waits
        CHECK (graph_name = 'document_graph' OR waiting_at_node IS NULL),
    CONSTRAINT ck_graph_thread_ended
        CHECK ((status IN ('ENDED', 'PURGED')) = (ended_at IS NOT NULL)),
    CONSTRAINT ck_graph_thread_purged CHECK ((status = 'PURGED') = (purged_at IS NOT NULL))
);

-- Thông báo trong ứng dụng. Chỉ mang mã và tham chiếu, không mang giá trị slot.
CREATE TABLE notification (
    id                     uuid        PRIMARY KEY,
    recipient_employee_id  uuid        NOT NULL REFERENCES employee (id),
    event_code             text        NOT NULL,
    request_id             uuid        REFERENCES request (id),
    document_id            uuid        REFERENCES document (id),
    dedupe_key             text        NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    pushed_at              timestamptz,
    read_at                timestamptz,
    CONSTRAINT uq_notification_dedupe UNIQUE (recipient_employee_id, event_code, dedupe_key),
    CONSTRAINT ck_notification_event_code CHECK (event_code ~ '^[A-Z][A-Z0-9_]*$')
);

-- Kế toán token của ai_gateway. RÀNG BUỘC CỨNG (cùng luật với audit_event):
-- bảng này TUYỆT ĐỐI KHÔNG chứa văn bản prompt, văn bản output hay bất kỳ giá
-- trị slot nào. Chỉ mã lời gọi, tier, số token, tham chiếu và trace_id.
CREATE TABLE llm_usage (
    id                             uuid        PRIMARY KEY,
    call_name                      text        NOT NULL,
    model_tier                     text        NOT NULL,
    prompt_module_version          text,
    request_id                     uuid        REFERENCES request (id),
    chat_session_id                uuid        REFERENCES chat_session (id),
    document_id                    uuid        REFERENCES document (id),
    procedure_document_version_id  uuid        REFERENCES procedure_document_version (id),
    input_tokens                   integer     NOT NULL,
    output_tokens                  integer,
    outcome                        text        NOT NULL,
    trace_id                       text        NOT NULL,
    created_at                     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_llm_usage_call_name CHECK (call_name IN (
        'classify_intent', 'extract_slots', 'select_procedure_passages',
        'draft_free_content', 'revise_free_content', 'embed_query', 'embed_corpus_chunk')),
    CONSTRAINT ck_llm_usage_tier CHECK (model_tier IN ('CHEAP', 'STRONG', 'EMBEDDING')),
    CONSTRAINT ck_llm_usage_embedding_tier
        CHECK ((call_name IN ('embed_query', 'embed_corpus_chunk')) = (model_tier = 'EMBEDDING')),
    CONSTRAINT ck_llm_usage_tokens
        CHECK (input_tokens >= 0 AND (output_tokens IS NULL OR output_tokens >= 0)),
    CONSTRAINT ck_llm_usage_outcome CHECK (outcome IN (
        'OK', 'PARSE_REPAIRED', 'PARSE_FAILED', 'PROVIDER_ERROR', 'BUDGET_EXCEEDED', 'BUDGET_UNAVAILABLE',
        'ALLOWLIST_REJECTED')),
    CONSTRAINT ck_llm_usage_has_budget_owner
        CHECK (num_nonnulls(request_id, chat_session_id, procedure_document_version_id) >= 1)
);

-- Quyết định đổi chế độ vận hành (D-009). Chế độ hiện hành = dòng có
-- effective_at lớn nhất đã tới; chưa có dòng nào = NON_PRODUCTION.
CREATE TABLE operating_mode_change (
    id                      uuid        PRIMARY KEY,
    from_mode               text        NOT NULL,
    to_mode                 text        NOT NULL,
    decided_by_employee_id  uuid        NOT NULL REFERENCES employee (id),
    decision_reference      text        NOT NULL,            -- tham chiếu văn bản quyết định có người ký
    effective_at            timestamptz NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_operating_mode_change_effective UNIQUE (effective_at),
    CONSTRAINT ck_operating_mode_change_modes
        CHECK (from_mode IN ('NON_PRODUCTION', 'PRODUCTION') AND to_mode IN ('NON_PRODUCTION', 'PRODUCTION')),
    CONSTRAINT ck_operating_mode_change_differs CHECK (from_mode <> to_mode),
    CONSTRAINT ck_operating_mode_change_reference CHECK (btrim(decision_reference) <> '')
);

-- Nhật ký nghiệp vụ bất biến. Không khoá ngoại: audit phải sống lâu hơn dòng
-- nghiệp vụ mà nó ghi nhận. payload chỉ mang mã — không văn bản tự do, không
-- giá trị slot.
CREATE TABLE audit_event (
    id                  uuid        PRIMARY KEY,
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    actor_kind          text        NOT NULL,
    actor_employee_id   uuid,
    action              text        NOT NULL,
    severity            text        NOT NULL DEFAULT 'INFO',
    entity_type         text        NOT NULL,
    entity_id           text        NOT NULL,
    request_id          uuid,
    document_id         uuid,
    decision_record_id  uuid,
    payload             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    trace_id            text,
    CONSTRAINT ck_audit_event_actor_kind CHECK (actor_kind IN ('EMPLOYEE', 'SYSTEM')),
    CONSTRAINT ck_audit_event_actor
        CHECK ((actor_kind = 'EMPLOYEE') = (actor_employee_id IS NOT NULL)),
    CONSTRAINT ck_audit_event_severity CHECK (severity IN ('INFO', 'WARNING')),
    CONSTRAINT ck_audit_event_action CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
    CONSTRAINT ck_audit_event_entity_type CHECK (entity_type ~ '^[a-z][a-z_]*$')
);


-- =============================================================================
-- H. [Should] Phòng họp
-- =============================================================================

CREATE TABLE room (
    id           uuid        PRIMARY KEY,
    code         text        NOT NULL,
    name         text        NOT NULL,
    capacity     integer     NOT NULL,                        -- A-012
    equipment    text[]      NOT NULL DEFAULT '{}',
    is_active    boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    row_version  integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_room_code UNIQUE (code),
    CONSTRAINT ck_room_capacity CHECK (capacity >= 1)
);

-- Chống trùng lịch: TẠM THỜI tuần tự hoá theo khoá dòng room trong giao dịch
-- giữ chỗ. Thiết kế đích là exclusion constraint, chờ A-046 (mục Bảng chi tiết
-- của 04-data.md).
CREATE TABLE room_booking (
    id               uuid        PRIMARY KEY,
    request_id       uuid        NOT NULL REFERENCES request (id),
    room_id          uuid        NOT NULL REFERENCES room (id),
    start_at         timestamptz NOT NULL,
    end_at           timestamptz NOT NULL,
    attendee_count   integer     NOT NULL,
    status           text        NOT NULL DEFAULT 'HELD',
    hold_expires_at  timestamptz,                             -- A-008
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    row_version      integer     NOT NULL DEFAULT 1,
    CONSTRAINT uq_room_booking_request UNIQUE (request_id),
    CONSTRAINT ck_room_booking_window CHECK (end_at > start_at),
    CONSTRAINT ck_room_booking_attendees CHECK (attendee_count >= 1),
    CONSTRAINT ck_room_booking_status
        CHECK (status IN ('HELD', 'CONFIRMED', 'RELEASED', 'CANCELLED', 'COMPLETED'))
);

ALTER TABLE approval_step
    ADD CONSTRAINT fk_approval_step_room_booking
        FOREIGN KEY (room_booking_id) REFERENCES room_booking (id);

-- =============================================================================
-- I. Index — lý do của từng index ở mục Bảng chi tiết của 04-data.md
-- =============================================================================

CREATE UNIQUE INDEX uq_permission_grant_active
    ON employee_permission_grant (employee_id, permission_code) WHERE revoked_at IS NULL;
CREATE INDEX ix_delegation_lookup
    ON delegation (delegate_employee_id, delegator_employee_id, permission_code) WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX uq_template_version_one_active
    ON template_version (template_id) WHERE status = 'ACTIVE';

CREATE INDEX ix_chat_session_open_by_employee ON chat_session (employee_id) WHERE status = 'OPEN';
CREATE INDEX ix_chat_session_idle ON chat_session (last_message_at) WHERE status = 'OPEN';
CREATE INDEX ix_chat_message_request ON chat_message (request_id) WHERE request_id IS NOT NULL;

CREATE UNIQUE INDEX uq_request_one_retained_attempt
    ON request (beneficiary_employee_id, request_type_code)
    WHERE status = 'EXPIRED' AND retained_values_cleared_at IS NULL;
CREATE INDEX ix_request_needs_info_expiry ON request (expires_at) WHERE status = 'NEEDS_INFO';
CREATE INDEX ix_request_created_by ON request (created_by_employee_id, created_at);
CREATE INDEX ix_request_chat_session ON request (chat_session_id) WHERE chat_session_id IS NOT NULL;
CREATE INDEX ix_request_open_due
    ON request (due_at) WHERE status IN ('SUBMITTED', 'IN_REVIEW', 'CHANGES_REQUESTED', 'APPROVED');

CREATE INDEX ix_document_request ON document (request_id);
CREATE INDEX ix_document_review_queue
    ON document (status, status_changed_at)
    WHERE status IN ('PENDING_APPROVAL', 'PENDING_SIGNATURE', 'PENDING_SEAL');

CREATE UNIQUE INDEX uq_approval_step_one_open
    ON approval_step (document_id, step_kind, level) WHERE status = 'OPEN' AND document_id IS NOT NULL;
CREATE INDEX ix_approval_step_assignee
    ON approval_step (assignee_employee_id, opened_at) WHERE status = 'OPEN';
CREATE INDEX ix_approval_step_self_approved ON approval_step (closed_at) WHERE self_approved;

CREATE UNIQUE INDEX uq_decision_one_per_approval_step
    ON decision_record (approval_step_id) WHERE approval_step_id IS NOT NULL;
CREATE INDEX ix_decision_record_document ON decision_record (document_id, created_at) WHERE document_id IS NOT NULL;
CREATE INDEX ix_decision_record_request ON decision_record (request_id, created_at);

CREATE UNIQUE INDEX uq_register_entry_one_assigned_per_document
    ON document_register_entry (document_id) WHERE status = 'ASSIGNED';
CREATE INDEX ix_register_entry_issue_decision ON document_register_entry (issue_decision_id);

CREATE INDEX ix_seal_action_document ON seal_action (document_id);
CREATE INDEX ix_seal_action_sealed_at ON seal_action (sealed_at);

CREATE INDEX ix_stored_object_lease ON stored_object (lease_expires_at);

CREATE UNIQUE INDEX uq_procedure_version_one_active
    ON procedure_document_version (procedure_document_id) WHERE is_active;
CREATE INDEX ix_procedure_chunk_lexical ON procedure_chunk USING gin (lexical_tsv);
CREATE UNIQUE INDEX uq_embedding_collection_one_active
    ON embedding_collection (status) WHERE status = 'ACTIVE';

CREATE INDEX ix_job_dispatch ON job (run_after) WHERE status = 'QUEUED';
CREATE INDEX ix_job_running_lease ON job (lease_expires_at) WHERE status = 'RUNNING';
CREATE UNIQUE INDEX uq_job_dedupe_pending
    ON job (job_type, dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('QUEUED', 'RUNNING');
CREATE INDEX ix_job_pending_by_document
    ON job (subject_document_id) WHERE subject_document_id IS NOT NULL AND status IN ('QUEUED', 'RUNNING');

CREATE INDEX ix_graph_thread_waiting ON graph_thread (waiting_at_node) WHERE status = 'WAITING';
CREATE INDEX ix_graph_thread_to_purge ON graph_thread (ended_at) WHERE status = 'ENDED';

CREATE INDEX ix_notification_inbox ON notification (recipient_employee_id, created_at);

CREATE INDEX ix_llm_usage_request ON llm_usage (request_id) WHERE request_id IS NOT NULL;
CREATE INDEX ix_llm_usage_chat_session ON llm_usage (chat_session_id) WHERE chat_session_id IS NOT NULL;
CREATE INDEX ix_llm_usage_created ON llm_usage (created_at);

CREATE INDEX ix_audit_event_request ON audit_event (request_id, occurred_at) WHERE request_id IS NOT NULL;
CREATE INDEX ix_audit_event_document ON audit_event (document_id, occurred_at) WHERE document_id IS NOT NULL;
CREATE INDEX ix_audit_event_occurred ON audit_event (occurred_at);
CREATE INDEX ix_audit_event_warning ON audit_event (occurred_at) WHERE severity = 'WARNING';

CREATE INDEX ix_room_booking_overlap
    ON room_booking (room_id, start_at) WHERE status IN ('HELD', 'CONFIRMED');
CREATE INDEX ix_room_booking_hold_expiry ON room_booking (hold_expires_at) WHERE status = 'HELD';


-- =============================================================================
-- J. Quyền của role runtime bo19_app — bất biến bằng GRANT/REVOKE (J4)
-- =============================================================================
-- bo19_app không sở hữu bảng nào, nên chỉ có đúng các quyền dưới đây.
-- Không cấp TRUNCATE cho bảng nào. Không dùng row-level security.

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;

-- J.1 Danh mục nạp bằng data migration — ứng dụng chỉ đọc.
GRANT SELECT ON role, permission, role_permission, employee_role, employee_permission_grant TO bo19_app;

-- J.2 Chỉ thêm (append-only): không UPDATE, không DELETE.
GRANT SELECT, INSERT ON
    audit_event, decision_record, document_render_pin, document_register_format,
    template_variable, template_variable_input, seal_action, document_halt,
    operating_mode_change, llm_usage, procedure_chunk
    TO bo19_app;

-- J.3 Thêm và xoá, không sửa: ghi một lần, xoá được khi hết hạn lưu, không sửa được.
GRANT SELECT, INSERT, DELETE ON
    decision_record_text, document_render, document_free_content,
    stored_object, stored_object_commit, procedure_chunk_embedding_v1
    TO bo19_app;

-- J.4 Sửa được, không xoá cứng. document và request không bao giờ bị xoá (F3).
GRANT SELECT, INSERT, UPDATE ON
    employee, request, request_slot, chat_session, document, approval_step,
    graph_thread, delegation, request_type, slot_definition, template,
    procedure_document, room, room_booking
    TO bo19_app;

-- J.5 Sửa được, nhưng chỉ ở đúng các cột liệt kê.
GRANT SELECT, INSERT ON chat_message TO bo19_app;
GRANT UPDATE (request_id, body, retrieval_query, content_erased_at) ON chat_message TO bo19_app;

GRANT SELECT, INSERT ON template_version TO bo19_app;
GRANT UPDATE (status, activated_at, retired_at, updated_at, row_version) ON template_version TO bo19_app;

GRANT SELECT, INSERT ON document_register TO bo19_app;
GRANT UPDATE (name, is_active, updated_at, row_version) ON document_register TO bo19_app;

GRANT SELECT, INSERT ON document_register_counter TO bo19_app;
GRANT UPDATE (next_seq, updated_at) ON document_register_counter TO bo19_app;

GRANT SELECT, INSERT ON document_register_entry TO bo19_app;
GRANT UPDATE (status, voided_at, void_reason) ON document_register_entry TO bo19_app;

GRANT SELECT, INSERT ON notification TO bo19_app;
GRANT UPDATE (pushed_at, read_at) ON notification TO bo19_app;

GRANT SELECT, INSERT ON procedure_document_version TO bo19_app;
GRANT UPDATE (is_active, activated_at, deactivated_at, updated_at, row_version)
    ON procedure_document_version TO bo19_app;

GRANT SELECT, INSERT ON embedding_collection TO bo19_app;
GRANT UPDATE (status, activated_at, retired_at, updated_at, row_version) ON embedding_collection TO bo19_app;

-- J.6 Hàng đợi job: vòng đời đầy đủ, kể cả dọn job đã xong (Phase 11).
GRANT SELECT, INSERT, UPDATE, DELETE ON job TO bo19_app;

-- Bảng checkpoint của LangGraph: tạo và cấp quyền theo migration của thư viện,
-- ngoài file này — [CẦN XÁC MINH] theo tài liệu phiên bản thư viện được dùng.
