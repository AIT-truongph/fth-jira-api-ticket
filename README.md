# Jira API cho AI — Demo & Tài liệu sống

Web nhỏ minh họa **toàn bộ chuỗi Jira Cloud REST API v3** phục vụ flow:

```
Webhook từ Jira → đọc hết thông tin ticket → tìm ticket tương tự đã giải quyết
→ AI phán đoán nên làm gì (phần AI do AI team đảm nhận)
```

## Web có gì — trang tổng hợp TOÀN BỘ kết quả điều tra

- **Tab "Demo trực tiếp"** — webhook event đổ về realtime; bấm event → thấy **AI context**
  (đúng JSON mà AI sẽ nhận: ticket normalize + ticket tương tự đã Done kèm cách fix + hành động khả dụng)
  cùng **trace từng API call thực tế** (endpoint, tham số, thời gian, vai trò trong flow).
- **Tab "Danh mục API"** — **45 API** nhóm theo 6 vai trò (webhook trigger → đọc hiểu →
  tìm tương tự → phán đoán & hành động → danh mục ngữ cảnh → 2 họ API ngoài Platform);
  mỗi API ghi rõ **"giúp gì cho AI"** + cách dùng; 27 API GET có nút **Gọi thử** trả response thật từ Jira.
- **Tab "Lưu ý quan trọng"** — **29 phát hiện** từ điều tra + kiểm chứng trên site thật,
  gắn nhãn `bẫy` / `đã test` / `khuyến nghị`: ADF vs text thuần, thứ tự webhook không đảm bảo,
  text ~ không quét labels, endpoint /search đã khai tử, accountId-only, rate limit, idempotency...

Nội dung 2 tab sau nằm trong `catalog_data.py` — bổ sung/sửa trực tiếp file đó, không cần đụng code server.

## Postman collection (cho ai thích gọi từng API bằng tay)

`Jira_AI.postman_collection.json` — 45 request khớp 100% danh mục trên web
(được sinh tự động từ `catalog_data.py` bằng `python generate_postman.py`).

**Folder và tên request đặt theo tài liệu chính thống Jira** (tag + operation summary của
Atlassian) — vd folder "Issue comments" chứa "Get comments", "Add comment"... giống hệt
developer.atlassian.com, để khách đối chiếu trực tiếp API nào ứng với API nào trên doc.
Mỗi request có khối mô tả gồm: **JIRA DOC** (folder, operation, link tài liệu) + **GIÚP GÌ CHO AI**.

Cách dùng: Postman → **Import** → kéo file vào → mở collection → tab **Variables** →
điền `apiToken` (tạo tại id.atlassian.com → Security → API tokens), sửa `baseUrl`/`username`/
`issueKey` nếu cần → mở request bất kỳ → **Send**. Auth đã cấu hình sẵn ở cấp collection;
API ghi (POST/PUT) có body mẫu sẵn.

> Collection được sinh từ `catalog_data.py` + tra metadata trong `../Full_APIs/swagger-jira-v3.json`
> bằng `python generate_postman.py`. Để regenerate cần có thư mục `Full_APIs` cạnh repo.

## Chạy trong 5 phút

```powershell
# 1. Cau hinh (hoac tao file API_token.txt canh repo - da gitignore)
$env:JIRA_SITE = "https://<site>.atlassian.net"
$env:JIRA_EMAIL = "<email>"
$env:JIRA_API_TOKEN = "<token tu id.atlassian.com>"

# 2. Chay web (Python 3.9+, khong can pip install gi)
python web_demo.py          # -> http://localhost:8765
```

Đến đây tab **Danh mục API** và **Xem AI context** đã dùng được. Muốn nhận webhook realtime:

```powershell
# 3. Mo tunnel (hoac ngrok)
cloudflared tunnel --url http://localhost:8765
# 4. Dang ky webhook voi URL tunnel vua duoc cap (can quyen admin Jira)
python register_webhook.py https://<random>.trycloudflare.com SCRUM
```

Sửa một ticket trong Jira → event hiện ra trên web trong ~1 giây.
URL tunnel đổi mỗi lần khởi động lại → chạy lại bước 4 (gỡ webhook cũ bằng DELETE vào URL `self` mà script in ra).

## File

| File | Vai trò |
|---|---|
| `API_GUIDE.md` | **Giải thích chi tiết vai trò từng API (52 cái) khi dùng cho AI** — đọc để hiểu mỗi API đóng góp gì vào việc hiểu/phán đoán ticket, kèm ví dụ chuỗi gọi thật |
| `web_demo.py` | Server: nhận webhook, API catalog, proxy gọi thử (chỉ GET), build context + trace |
| `index.html` | Giao diện 3 tab |
| `catalog_data.py` | Nguồn dữ liệu 52 API + 29 lưu ý (web, Postman, API_GUIDE đều sinh từ đây) |
| `ai_context.py` | **Contract với AI team** — ghép chuỗi API thành JSON context; chạy độc lập được |
| `jira_client.py` | Client REST tối giản (`call`, `adf_to_text`, hook trace) |
| `generate_postman.py` / `generate_api_guide.py` | Sinh Postman collection / API_GUIDE.md từ `catalog_data.py` |
| `register_webhook.py` | Đăng ký webhook qua API |

## 5 điều quan trọng nhất về Jira API (rút từ điều tra + test thật)

1. **Webhook chỉ là trigger** — payload comment event chỉ chứa issue rút gọn, thứ tự event
   không đảm bảo → luôn lấy `issue.key` rồi gọi `GET /issue/{key}` lấy trạng thái mới nhất.
2. **API v3 trả description/comment dạng ADF (JSON)** nhưng payload webhook là text thuần →
   parser xử lý cả hai (`adf_to_text` trong `jira_client.py`).
3. **Tìm tương tự = keyword search** (`text ~`), không có semantic search; `text ~` không quét
   labels → JQL nên là `(text ~ "..." OR labels in (...))`. Không đủ tốt → cân nhắc vector DB.
4. **`/rest/api/3/search` cũ đã khai tử** — dùng `/search/jql`, JQL phải bounded, phân trang `nextPageToken`.
5. **Trước khi hành động**: `GET /issue/{key}/transitions` (bước chuyển hợp lệ),
   `GET /user/assignable/search` (người được gán), `GET /mypermissions` (bot đủ quyền chưa).

## Bảo mật

API token = toàn quyền tài khoản tạo nó. Token chỉ nằm trong env var hoặc `API_token.txt`
(đã gitignore). Không commit, không hardcode, revoke khi không dùng.
