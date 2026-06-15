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

Mỗi dev tự lấy source về và cấu hình **của riêng mình** trong **một file `.env`**
(copy từ `.env.example`, đã gitignore — không commit):

```powershell
# 1. Tao file cau hinh cua ban
copy .env.example .env
#    roi mo .env dien: JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN (token tao tai id.atlassian.com)

# 2. Chay (Python 3.9+, khong can pip install gi)
python web_demo.py          # -> http://localhost:8765
```

> Toàn bộ cấu hình gom trong `.env`. Code tự nạp file này lúc khởi động (không cần `pip install`).
> Nếu bạn đã set sẵn biến môi trường thật ở shell thì biến đó được ưu tiên hơn giá trị trong `.env`.

Chỉ một lệnh `python web_demo.py` lo **toàn bộ**: mở web server → tự chạy `cloudflared`
tunnel → lấy URL công khai mới → **tự đăng ký/cập nhật webhook riêng của bạn** trên Jira.
Không cần chạy tunnel hay đăng ký webhook bằng tay. Sửa một ticket trong Jira → event hiện
ra trên web trong ~1 giây. `Ctrl+C` để dừng (tự tắt luôn tunnel).

> **Cần:** `cloudflared` đã cài (tự tìm trong PATH và `C:\Program Files (x86)\cloudflared`),
> và token có **quyền admin** trên site (đăng ký webhook đòi quyền admin).

**Webhook riêng theo từng dev** — tên webhook tự đặt theo email bạn cấu hình
(vd. `AI ticket demo - haitruong7592`), nên **nhiều dev dùng chung một site không giẫm lên nhau**:
mỗi người có webhook riêng, Jira gửi event tới tất cả → ai cũng nhận. Chạy lại nhiều lần chỉ
cập nhật đúng webhook đó (không tạo trùng). Cấu hình thêm qua env (đều có mặc định):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `JIRA_PROJECT` | `SCRUM` | Project key để lọc sự kiện webhook |
| `JIRA_WEBHOOK_NAME` | `AI ticket demo - <phần trước @ của email>` | Đặt tay nếu nhiều dev chung một máy/email |

> `register_webhook.py` (đăng ký tay) vẫn còn cho ai muốn tự kiểm soát, nhưng quy trình tự động
> ở trên đã thay thế nó trong luồng chạy thường ngày.

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
