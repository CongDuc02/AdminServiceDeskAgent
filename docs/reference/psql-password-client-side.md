# psql `\password` — mật khẩu được băm phía client, thuật toán lấy từ `password_encryption` của phiên

- **Nguồn:**
  - `https://www.postgresql.org/docs/17/app-psql.html` — psql, mục `\password`
  - `https://www.postgresql.org/docs/17/libpq-misc.html` — `PQencryptPasswordConn`, `PQchangePassword`
  - `https://raw.githubusercontent.com/postgres/postgres/REL_17_10/src/bin/psql/command.c` — `exec_command_password`
  - `https://raw.githubusercontent.com/postgres/postgres/REL_17_10/src/interfaces/libpq/fe-auth.c` — `PQencryptPasswordConn`
  - `https://www.postgresql.org/docs/16/sql-show.html` · `https://www.postgresql.org/docs/16/sql-set.html` · `https://www.postgresql.org/docs/16/runtime-config-connection.html` — phía server
- **Ngày lấy:** 2026-09-14, bằng `curl`. HTML được tách thẻ; câu chữ giữ nguyên. Mã nguồn chép nguyên văn, chỗ lược ghi `/* ... */`.
- **Phiên bản:** client là psql **17.10** — đúng bản đã dùng ở Spike 1 S0, nên mã nguồn ghim theo tag `REL_17_10`. Server là PostgreSQL **16** (số đo ở mục cuối), nên tài liệu phía server lấy bản 16.
- **Dùng cho:** thủ tục đặt mật khẩu `bo19_migrator`, `bo19_app` ở Spike 1 S0 — A-040; A-061.

> Hai mục đầu là **tuyên bố của tài liệu và mã nguồn**. Mục cuối là **số đo** trên instance Render. Hai loại không thay thế nhau.

---

## 1. psql — `\password` (tài liệu 17)

> Changes the password of the specified user (by default, the current user). This command prompts for the new password, encrypts it, and sends it to the server as an `ALTER ROLE` command. This makes sure that the new password does not appear in cleartext in the command history, the server log, or elsewhere.

Mã nguồn `src/bin/psql/command.c`, tag `REL_17_10`, dòng 2159–2175 — mật khẩu đọc bằng lời nhắc, rồi giao cho libpq:

```c
		pw1 = simple_prompt_extended(buf.data, false, &prompt_ctx);
		if (!prompt_ctx.canceled)
			pw2 = simple_prompt_extended("Enter it again: ", false, &prompt_ctx);
/* ... */
		else
		{
			PGresult   *res = PQchangePassword(pset.db, user, pw1);
```

## 2. libpq — thuật toán đến từ đâu (tài liệu 17 và mã nguồn)

`PQchangePassword`:

> This function uses `PQencryptPasswordConn` to build and execute the command `ALTER USER ... PASSWORD '...'`, thereby changing the user's password. It exists for the same reason as `PQencryptPasswordConn`, but is more convenient as it both builds and runs the command for you. `PQencryptPasswordConn` is passed a `NULL` for the algorithm argument, hence encryption is done according to the server's password_encryption setting.

`PQencryptPasswordConn`:

> This function is intended to be used by client applications that wish to send commands like `ALTER USER joe PASSWORD 'pwd'`. It is good practice not to send the original cleartext password in such a command, because it might be exposed in command logs, activity displays, and so on. Instead, use this function to convert the password to encrypted form before it is sent.

> […] If *algorithm* is `NULL`, this function will query the server for the current value of the password_encryption setting. […]

Mã nguồn `src/interfaces/libpq/fe-auth.c`, tag `REL_17_10`, dòng 1288–1294 và 1338–1348 — lệnh hỏi chạy **trên chính kết nối** được truyền vào:

```c
	/* If no algorithm was given, ask the server. */
	if (algorithm == NULL)
	{
		PGresult   *res;
		char	   *val;

		res = PQexec(conn, "show password_encryption");
/* ... */
	if (strcmp(algorithm, "scram-sha-256") == 0)
	{
		const char *errstr = NULL;

		crypt_pwd = pg_fe_scram_build_secret(passwd,
											 conn->scram_sha_256_iterations,
											 &errstr);
/* ... */
	else if (strcmp(algorithm, "md5") == 0)
```

## 3. Phía server — `SHOW`, `SET`, `password_encryption` (tài liệu 16)

`SHOW`:

> SHOW will display the current setting of run-time parameters. […]

`SET`:

> […] (Some parameters can only be changed by superusers and users who have been granted `SET` privilege on that parameter. There are also parameters that cannot be changed after server or session start.) `SET` only affects the value used by the current session.

`password_encryption`:

> When a password is specified in CREATE ROLE or ALTER ROLE, this parameter determines the algorithm to use to encrypt the password. Possible values are `scram-sha-256`, which will encrypt the password with SCRAM-SHA-256, and `md5`, which stores the password as an MD5 hash. The default is `scram-sha-256`.

**Chuỗi suy luận từ ba mục trên:** `\password` → `PQchangePassword` → `PQencryptPasswordConn(…, NULL)` → `show password_encryption` trên chính kết nối của psql → `SHOW` trả giá trị hiện hành của phiên, mà `SET` đổi được trong phiên. Vì vậy `SET password_encryption = 'scram-sha-256'` trong cùng phiên trước `\password` làm libpq băm bằng SCRAM-SHA-256. Tài liệu `PQchangePassword` viết "the server's password_encryption setting"; mã nguồn cho thấy đó là kết quả `SHOW` trên kết nối, tức giá trị của phiên.

---

## 4. Nguồn **không** nói

- Role **không phải superuser** có được `SET password_encryption` không. Trang `SET` chỉ nói "some parameters" bị giới hạn, không nói tham số nào. Đã **đo** ở mục 5.
- Cách đọc lại thuật toán thực sự đã lưu cho một role — chưa kiểm, `[CẦN XÁC MINH]`.

## 5. Đã đo trên instance Render — không phải tuyên bố

2026-09-14T04:34:12Z · psql 17.10 · server `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)` · role `bo19_owner` · gói Free, trước khi nâng gói.

```
        name         | setting |   boot_val    | reset_val | context |       source
---------------------+---------+---------------+-----------+---------+--------------------
 password_encryption | md5     | scram-sha-256 | md5       | user    | configuration file
```

Trong một giao dịch rồi `ROLLBACK`: `SET LOCAL password_encryption = 'scram-sha-256'` → `SET`; `SHOW password_encryption` → `scram-sha-256`. Sau `ROLLBACK`: `SHOW password_encryption` → `md5`.

Đọc: giá trị `md5` do tệp cấu hình của nền tảng đặt, khác mặc định `scram-sha-256` của bản build (`boot_val`) và của tài liệu mục 3. `context = user`, và `bo19_owner` — không phải superuser — `SET` được trong phiên.
