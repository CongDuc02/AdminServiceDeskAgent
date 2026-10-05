# import-linter 2.15 — cấu hình, `forbidden`, `layers`, `independence`, cách chạy

- **Nguồn — lấy bằng `curl`, ngày 2026-10-05** (tài liệu theo phiên bản; bản `v2.15`, phát hành 2026-09-04 theo trang Release notes):
  - `https://import-linter.readthedocs.io/en/v2.15/get_started/configure/` — sha256 `24a224d3196af1ae0d47870ba22c0e48b22b5ec1fff9e74734a3025b5cc2d0c8`
  - `https://import-linter.readthedocs.io/en/v2.15/get_started/run/` — sha256 `6f2a5296ef833e00d8bb6b79b2c2fe72925ca2414a5da7509a2cfe6e13993bd6`
  - `https://import-linter.readthedocs.io/en/v2.15/contract_types/` — sha256 `72baaf4f574afb47ecdd451a9fa90d46e5da8d69352b68792e6069c25a3cd303`
  - `https://import-linter.readthedocs.io/en/v2.15/contract_types/forbidden/` — sha256 `62d350db9e8b6aa4b91b6e72f3839f234b82915b08af6df792f8793978d69854`
  - `https://import-linter.readthedocs.io/en/v2.15/contract_types/layers/` — sha256 `2c3022cf6917ef5e42fb9043b0ea96ae523929beb35441fbe4c810960b6a5de4`
  - `https://import-linter.readthedocs.io/en/v2.15/contract_types/independence/` — sha256 `f0772090593100cd96e54adb09f2f241e6bf0898017c8211c97219a40242b118`
  - `https://import-linter.readthedocs.io/en/v2.15/release_notes/` — sha256 `424c8ef73f4a5fb5b8ed4519fb44cae5715b481efe0a1044f573e42562be6d51`
- **Cách tách:** bỏ thẻ HTML, giữ câu chữ nguyên văn. Tài liệu sống — có thể đổi sau ngày lấy. Trang `install` và `acyclic_siblings`, `protected` không dùng.
- **Phiên bản 2.15** do chính công cụ khoá chọn: `uv pip compile` ở mốc `--exclude-newer 2026-10-02T00:00:00Z` ra `import-linter==2.15`, kéo theo `grimp==3.17`, `rich==15.0.0`, `markdown-it-py==4.2.0`, `mdurl==0.1.2`, `pygments==2.21.0`, `typing-extensions==4.16.0` (`backend/requirements-dev-linux.lock`).
- **Dùng cho:** B1 của track build (CI, AC-1.12); mục Đặc tả `.importlinter` của `docs/design/06-structure.md`; ghi chú Cập nhật của ADR-030.

---

## 1. Cấu hình

> If not specified over the command line, Import Linter will look in the current directory for one of the following files:
> setup.cfg (INI format)
> .importlinter (INI format)
> pyproject.toml (TOML format)

> root_package: The name of the Python package to validate. For regular packages, this must be the top level package (i.e. one with no dots in its name). […] The root_package must be importable: usually this means it has been installed using a Python package manager, or it's in the current directory. (Either this or root_packages is required.)

> include_external_packages: Whether to include external packages when building the import graph. Unlike root packages, external packages are not statically analyzed, so no imports from external packages will be checked. However, imports of external packages will be available for checking. Not every contract type uses this.

> ini format: each contract has its own INI section, which begins importlinter:contract: and ends in a unique id (in the example above, the ids are one and two).

## 2. Chạy

> To check that your project adheres to the contracts you've defined, run: `lint-imports` (Or you can use the alias import-linter lint if you prefer.)

Tuỳ chọn có dùng: `--config` ("The configuration file to use. This overrides the default file search strategy."), `--no-cache` ("Disable caching."), `--contract` (giới hạn theo id), `--verbose`, `--debug`. Bộ đệm mặc định ở `.import_linter_cache`.

## 3. `forbidden`

> Forbidden contracts check that one set of modules is not imported by another set of modules.
> By default, descendants of each module will be checked - so if mypackage.one is forbidden from importing mypackage.two, then mypackage.one.blue will be forbidden from importing mypackage.two.green. **Indirect imports will also be checked.**
> External packages may also be forbidden. (Be sure to configure Import Linter to include external packages).

> allow_indirect_imports: If True, allow indirect imports to forbidden modules without interpreting them as a reason to mark the contract broken. (Optional.)

> source_modules: A list of modules that should not import the forbidden modules. Supports wildcards.
> forbidden_modules: […] These may include root level external packages (i.e. django, but not django.db.models). If external packages are included, the top level configuration must have include_external_packages = True. Supports wildcards.

## 4. `layers`

> Layers contracts enforce a 'layered architecture', where higher layers may depend on lower layers, but not the other way around.

> layers: An ordered list with the name of each layer module. […] The order is from higher to lower level layers. […] It's also possible to include multiple layer modules on the same line, separated by either exclusively pipes (|) or exclusively colons (:)

> Import Linter supports the presence of multiple sibling modules or packages within the same layer. In the diagram below, the modules blue, green and yellow are 'independent' in the same layer. This means that, in addition to not being allowed to import from layers above them, they are not allowed to import from each other. […] To allow siblings to depend on each other, use colons instead of pipes to separate them

## 5. `independence`

> Independence contracts check that a set of modules do not depend on each other. They do this by checking that there are no imports in any direction between the modules, even indirectly.

## 6. Release notes

Mục "2.15 (2026-09-04)" có trong trang Release notes.

---

## 7. Quan sát khi chạy 2.15, 2026-10-05 — **không** có trong tài liệu

- Một module liệt kê trong `source_modules`, `forbidden_modules` hay `layers` mà **không tồn tại** làm `lint-imports` dừng ngay: `Module 'bo19.orchestrator.runner' does not exist.` — không in kết quả của contract nào. Tìm "does not exist" trong sáu trang đã lấy không có kết quả. Hệ quả: contract chỉ nêu module đã có file (kể cả file khung).

## 8. Nguồn này **không** nói

| Câu hỏi | Theo nguồn |
|---|---|
| Mã thoát khi có contract bị phá | Không có trong các trang đã lấy — **kiểm bằng chạy thật** (`docs/design/CHANGELOG.md`, mục B1) |
| Cú pháp đúng cho chú thích cuối dòng trong `.importlinter` | Không có — chỉ dùng dòng chú thích riêng bắt đầu bằng `#` |
