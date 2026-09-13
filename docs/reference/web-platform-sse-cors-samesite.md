# Nền tảng web — `EventSource`, cookie `SameSite=Strict`, CORS preflight

- **Nguồn và phiên bản:**

| Tài liệu | URL | Phiên bản / mốc |
|---|---|---|
| HTML Standard — Server-sent events | `https://html.spec.whatwg.org/multipage/server-sent-events.html` | Living Standard, "Last Updated 8 September 2026" |
| HTML Standard — URLs and fetching | `https://html.spec.whatwg.org/multipage/urls-and-fetching.html` | Living Standard, "Last Updated 8 September 2026" |
| Fetch Standard | `https://fetch.spec.whatwg.org/` | Living Standard, "Last Updated 2 September 2026" |
| Cookies: HTTP State Management Mechanism | `https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-22.txt` | **Internet-Draft** `draft-ietf-httpbis-rfc6265bis-22`, ngày 1 December 2025, ghi "Expires: 4 June 2026". Là bản mới nhất mà datatracker trả về lúc lấy; **không phải RFC**, và đã qua ngày hết hạn ghi trên chính nó |

- **Ngày lấy:** 2026-09-13, bằng `curl`. Văn bản HTML được tách thẻ; khoảng trắng và xuống dòng đã chuẩn hoá, câu chữ giữ nguyên.
- **Dùng cho:** A-051 (1), (2), (3).

---

## A-051(1) — `EventSource`: không header tuỳ biến, gửi cookie cùng origin, tự nối lại

**IDL — HTML Standard, Server-sent events:**

```webidl
dictionary EventSourceInit {
 boolean withCredentials = false;
};
```

**Constructor — HTML Standard, Server-sent events:**

> Let corsAttributeState be Anonymous.
> If the value of eventSourceInitDict's withCredentials member is true, then set corsAttributeState to Use Credentials and set ev's withCredentials attribute to true.
> Let request be the result of creating a potential-CORS request given urlRecord, the empty string, and corsAttributeState.

**Tạo request — HTML Standard, URLs and fetching:**

> To create a potential-CORS request, given a url, destination, corsAttributeState, and an optional same-origin fallback flag, run these steps:
> Let mode be "no-cors" if corsAttributeState is No CORS, and "cors" otherwise.
> If same-origin fallback flag is set and mode is "no-cors", set mode to "same-origin".
> Let credentialsMode be "include".
> If corsAttributeState is Anonymous, set credentialsMode to "same-origin".

**Nghĩa của "same-origin" — Fetch Standard:**

> "same-origin"
> Include credentials with requests made to same-origin URLs, and use any credentials sent back in responses from same-origin URLs.

**Nối lại — HTML Standard, Server-sent events:**

> Let processEventSourceEndOfBody given response res be the following step: if res is not a network error, then reestablish the connection.

> If res is an aborted network error, then fail the connection.
> Otherwise, if res is a network error, then reestablish the connection, unless the user agent knows that to be futile, in which case the user agent may fail the connection.

> A reconnection time, in milliseconds. This must initially be an implementation-defined value, probably in the region of a few seconds.

> Wait a delay equal to the reconnection time of the event source.
> Optionally, wait some more. In particular, if the previous attempt failed, then user agents might introduce an exponential backoff delay to avoid overloading a potentially already overloaded server.

**Kết luận cho A-051(1):** `EventSourceInit` chỉ có `withCredentials` — không có chỗ cho header tuỳ biến. Mặc định `Anonymous` cho credentials mode `"same-origin"`, tức cookie **được gửi** với URL cùng origin. Khi server kết thúc body bình thường, `EventSource` **tự nối lại** sau reconnection time.

---

## A-051(2) — `SameSite=Strict`

**draft-ietf-httpbis-rfc6265bis-22:**

>    If the "SameSite" attribute's value is "Strict", the cookie will only
>    be sent along with "same-site" requests.

>    Two origins are same-site if they satisfy the "same site" criteria
>    defined in [SAMESITE].  A request is "same-site" if the following
>    criteria are true:
>
>    1.  The request is not the result of a reload navigation triggered
>        through a user interface element (as defined by the user agent;
>        e.g., a request triggered by the user clicking a refresh button
>        on a toolbar).
>
>    2.  The request's current url's origin is same-site with the
>        request's client's "site for cookies" (which is an origin), or if
>        the request has no client or the request's client is null.
>
>    Requests which are the result of a reload navigation triggered
>    through a user interface element are same-site if the reloaded
>    document was originally navigated to via a same-site request.  A
>    request that is not "same-site" is instead "cross-site".

**Kết luận cho A-051(2):** cookie `SameSite=Strict` chỉ đi kèm request "same-site"; request "cross-site" không mang nó. Tiêu chí "same site" của hai origin nằm ở tài liệu `[SAMESITE]` mà bản trích không kèm.

---

## A-051(3) — header tuỳ biến buộc preflight; preflight hỏng thì request hỏng

**Header được liệt kê an toàn — Fetch Standard:**

> To determine whether a header (name, value) is a CORS-safelisted request-header, run these steps:
> If value's length is greater than 128, then return false.
> Byte-lowercase name and switch on the result:
> `accept`
> …
> `accept-language`
> `content-language`
> …
> `content-type`
> …

Danh sách nhánh `switch` chỉ gồm các tên cố định (bản trích lược phần kiểm giá trị); tên nằm ngoài danh sách không phải CORS-safelisted.

> The CORS-unsafe request-header names, given a header list headers, are determined as follows:
> Let unsafeNames be a new list.
> …
> For each header of headers:
> If header is not a CORS-safelisted request-header, then append header's name to unsafeNames.

**Khi nào có preflight — Fetch Standard, HTTP fetch:**

> If makeCORSPreflight is true and one of these conditions is true:
> There is no method cache entry match for request's method using request, and either request's method is not a CORS-safelisted method or request's use-CORS-preflight flag is set.
> There is at least one item in the CORS-unsafe request-header names with request's header list for which there is no header-name cache entry match using request.
> Then:
> Let preflightResponse be the result of running CORS-preflight fetch given request.
> If preflightResponse is a network error, then return preflightResponse.

> The unsafe-request flag is set by APIs such as fetch() and XMLHttpRequest to ensure a CORS-preflight fetch is done based on the supplied method and header list.

**CORS check — Fetch Standard:**

> To perform a CORS check for a request and response, run these steps:
> Let origin be the result of getting `Access-Control-Allow-Origin` from response's header list.
> If origin is null, then return failure.
> …
> If the result of byte-serializing a request origin with request is not origin, then return failure.

> If request's response tainting is "cors" and a CORS check for request and response returns failure, then return a network error.

**Kết luận cho A-051(3):** một header như `X-BO19-CSRF` không phải CORS-safelisted, nên request khác origin mang nó bị buộc qua preflight; server không trả `Access-Control-Allow-Origin` khớp origin gọi thì CORS check thất bại và fetch trả network error.
