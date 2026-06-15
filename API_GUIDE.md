# Vai trò từng API Jira khi dùng cho AI xử lý ticket

> Tài liệu này giải thích **mỗi API đóng vai trò gì** trong hệ thống AI nhận webhook → đọc hiểu ticket → tìm ticket tương tự → phán đoán hành động.
>
> Sinh tự động từ `catalog_data.py` bằng `python generate_api_guide.py` — luôn khớp với web demo và Postman collection. Tổng cộng **52 API**, chia 6 giai đoạn theo luồng xử lý.

## Mục lục

- [1. Trigger — Webhook (Jira chủ động gọi mình)](#1-trigger--webhook-jira-chủ-động-gọi-mình) — 3 API
- [2. Đọc hiểu ticket (input chính cho AI)](#2-đọc-hiểu-ticket-input-chính-cho-ai) — 14 API
- [3. Tìm ticket tương tự đã giải quyết](#3-tìm-ticket-tương-tự-đã-giải-quyết) — 7 API
- [4. Phán đoán & hành động (AI quyết → service làm)](#4-phán-đoán--hành-động-ai-quyết--service-làm) — 15 API
- [5. Danh mục ngữ cảnh (cache 1 lần khi khởi động)](#5-danh-mục-ngữ-cảnh-cache-1-lần-khi-khởi-động) — 10 API
- [6. Hai họ API ngoài Platform (cùng site, cùng auth, tài liệu riêng)](#6-hai-họ-api-ngoài-platform-cùng-site-cùng-auth-tài-liệu-riêng) — 3 API

## Các API nối với nhau như thế nào — ví dụ thật

Khi service nhận webhook báo ticket **SCRUM-7** ("Customer charged twice when payment timeout")
vừa được tạo, đây là chuỗi API thực tế chạy để dựng dữ liệu cho AI (đo bằng trace trên web demo):

| # | API | Mục đích trong bước này |
|---|-----|------------------------|
| 1 | `GET /issue/SCRUM-7?expand=names,changelog` | Đọc toàn bộ ticket vừa được báo |
| 2 | `GET /issue/SCRUM-7/comment` | Đọc thảo luận trên ticket |
| 3 | `POST /search/jql` (statusCategory=Done, text~"payment timeout") | Tìm ticket tương tự đã giải quyết |
| 4–7 | `GET /issue/SCRUM-6` + `/comment`, `GET /issue/SCRUM-5` + `/comment` | Đọc chi tiết + cách fix của 2 ứng viên |
| 8 | `GET /issue/SCRUM-7/transitions` | Lấy các bước chuyển hợp lệ |
| 9 | `GET /user/assignable/search?issueKey=SCRUM-7` | Lấy danh sách người được phép gán |

Kết quả: 9 API call (~4 giây tuần tự, ~1.5 giây nếu gọi song song) → một gói JSON context
chứa **ticket đã normalize + 2 ticket tương tự kèm cách fix + khung hành động hợp lệ**.
Gói này chính là input cho AI. AI đọc xong sẽ thấy: "bug này giống SCRUM-5 (đã fix bằng
idempotency key) và SCRUM-6 (tăng timeout) → đề xuất gán cho người từng xử lý + comment gợi ý".

Toàn bộ logic ghép chuỗi này nằm trong `ai_context.py` (hàm `build_context`).

---

## 1. Trigger — Webhook (Jira chủ động gọi mình)

Đây là **điểm bắt đầu** của toàn bộ hệ thống. Thay vì cứ vài giây lại hỏi Jira "có ticket nào mới không" (tốn tài nguyên, chậm), ta đăng ký webhook một lần để Jira **tự gọi sang** mỗi khi có thay đổi. Webhook không mang đủ dữ liệu để AI làm việc — nó chỉ là *tiếng chuông báo* kèm khóa ticket (issue.key). Vai trò của giai đoạn này với AI: khởi động đúng lúc, đúng ticket, và lọc sẵn rác (qua JQL filter) để AI không bị gọi dậy bởi những thay đổi không liên quan.

### Đăng ký webhook (cần quyền admin)

`🔵 POST` `/rest/webhooks/1.0/webhook`

**Vai trò cho AI:** Điểm khởi đầu của cả flow: Jira tự báo khi ticket được tạo/sửa/comment, kèm JQL filter để chỉ nhận đúng project. Service KHÔNG cần polling.

**Cách dùng / lưu ý:** Body: {"name", "url", "events": ["jira:issue_created","jira:issue_updated","comment_created"], "filters": {"issue-related-events-section": "project = SCRUM"}}.

### Liệt kê webhook đã đăng ký

`🟢 GET` `/rest/webhooks/1.0/webhook`

**Vai trò cho AI:** Kiểm tra webhook đang trỏ về đâu, còn enabled không. DELETE vào URL self của từng webhook để gỡ.

**Cách dùng / lưu ý:** Không tham số.

### Webhook động (chỉ cho OAuth/Connect app)

`🔵 POST` `/rest/api/3/webhook`

**Vai trò cho AI:** Phương án webhook khi xây app phân phối chính thức. KHÔNG dùng được với API token.

**Cách dùng / lưu ý:** Kèm GET /rest/api/3/webhook/failed (xem webhook gửi lỗi) và PUT /rest/api/3/webhook/refresh (gia hạn — webhook OAuth hết hạn sau 30 ngày).

---

## 2. Đọc hiểu ticket (input chính cho AI)

Sau khi webhook báo, đây là giai đoạn **thu thập toàn bộ dữ liệu** để AI thực sự hiểu ticket đang nói về cái gì. Một ticket không chỉ là tiêu đề + mô tả: nó còn có comment (nơi chứa thảo luận và manh mối), lịch sử thay đổi (đã qua tay ai, bị trả lại mấy lần), file đính kèm (log, ảnh lỗi), và hàng loạt custom field. Vai trò của giai đoạn này với AI: biến dữ liệu thô, rời rạc, định dạng máy (ADF, customfield_xxxxx) thành một bức tranh sạch sẽ, đầy đủ ngữ cảnh mà mô hình ngôn ngữ đọc được.

### Get issue — API trung tâm

`🟢 GET` `/rest/api/3/issue/{key}`

**Vai trò cho AI:** Một call lấy gần hết: summary, description, status, priority, labels, custom fields, issue links, subtasks, attachment metadata, changelog. 'names' dịch customfield_xxxxx thành tên người hiểu được; 'renderedFields' trả HTML thay vì ADF.

**Cách dùng / lưu ý:** Description mặc định là ADF (JSON) — cần converter sang text cho AI (xem adf_to_text trong jira_client.py).

### Get comments

`🟢 GET` `/rest/api/3/issue/{key}/comment`

**Vai trò cho AI:** Thảo luận trong comment thường chứa nguyên nhân gốc và cách fix — phần giá trị nhất khi AI đọc ticket tương tự đã giải quyết.

**Cách dùng / lưu ý:** Phân trang startAt/maxResults; body comment cũng là ADF. Ticket JSM có cờ jsdPublic phân biệt comment nội bộ/công khai.

### Get changelog

`🟢 GET` `/rest/api/3/issue/{key}/changelog`

**Vai trò cho AI:** Lịch sử ai đổi gì khi nào — AI hiểu ticket đã đi qua những bước nào, bị trả lại bao nhiêu lần.

**Cách dùng / lưu ý:** Hoặc gộp vào Get issue bằng expand=changelog. Đọc hàng loạt: POST /rest/api/3/changelog/bulkfetch.

### Tải nội dung attachment (đã test: khớp 100%)

`🟢 GET` `/rest/api/3/attachment/content/{id}`

**Vai trò cho AI:** Đọc log lỗi, config đính kèm — GET issue chỉ trả metadata, muốn AI đọc nội dung file phải gọi endpoint này.

**Cách dùng / lưu ý:** id từ fields.attachment[].id; response binary. Upload: POST /issue/{key}/attachments (multipart + header X-Atlassian-Token: no-check).

### Thumbnail ảnh đính kèm

`🟢 GET` `/rest/api/3/attachment/thumbnail/{id}`

**Vai trò cho AI:** Lấy bản thu nhỏ của screenshot khi không cần ảnh gốc (tiết kiệm băng thông/token vision).

**Cách dùng / lưu ý:** Kèm GET /attachment/{id}/expand/human — xem danh sách file BÊN TRONG file zip mà không cần tải về.

### Get remote links

`🟢 GET` `/rest/api/3/issue/{key}/remotelink`

**Vai trò cho AI:** Link ngoài gắn vào ticket (trang Confluence, PR...) — ngữ cảnh bổ sung.

**Cách dùng / lưu ý:** Không tham số.

### Get worklogs

`🟢 GET` `/rest/api/3/issue/{key}/worklog`

**Vai trò cho AI:** Ai đã làm bao nhiêu giờ trên ticket — tín hiệu về độ phức tạp thực tế và người hiểu ticket nhất.

**Cách dùng / lưu ý:** Phân trang startAt/maxResults.

### Get watchers

`🟢 GET` `/rest/api/3/issue/{key}/watchers`

**Vai trò cho AI:** Ai đang theo dõi ticket — tín hiệu mức độ quan tâm, ứng viên để hỏi thêm thông tin.

**Cách dùng / lưu ý:** Kèm GET /issue/{key}/votes — số vote (mức độ mong muốn từ người dùng).

### Đọc issue properties

`🟢 GET` `/rest/api/3/issue/{key}/properties`

**Vai trò cho AI:** Đọc lại trạng thái AI đã lưu trên ticket (đã xử lý chưa, kết quả gì) — xem mục PUT properties ở nhóm 4.

**Cách dùng / lưu ý:** GET .../properties liệt kê keys; GET .../properties/{propertyKey} đọc giá trị.

### Bulk fetch — lấy chi tiết hàng loạt

`🔵 POST` `/rest/api/3/issue/bulkfetch`

**Vai trò cho AI:** Sau khi search ra danh sách key, lấy chi tiết tối đa 100 ticket/call thay vì gọi lẻ.

**Cách dùng / lưu ý:** Body: {"issueIdsOrKeys": ["SCRUM-5","SCRUM-6"], "fields": [...]}. Tương tự POST /comment/list đọc comment hàng loạt theo id.

### Đọc comment hàng loạt theo ID

`🔵 POST` `/rest/api/3/comment/list`

**Vai trò cho AI:** Khi đã có id của nhiều comment (vd từ nhiều ticket tương tự), lấy hết trong 1 call thay vì gọi lẻ từng ticket.

**Cách dùng / lưu ý:** Body: {"ids": [10000, 10001, ...]}.

### Đọc changelog hàng loạt

`🔵 POST` `/rest/api/3/changelog/bulkfetch`

**Vai trò cho AI:** Lấy lịch sử thay đổi của nhiều ticket cùng lúc — dựng bức tranh các ticket tương tự đã đi qua những bước nào.

**Cách dùng / lưu ý:** Body: {"issueIdsOrKeys": ["SCRUM-5","SCRUM-6"]}.

### Danh mục toàn bộ field

`🟢 GET` `/rest/api/3/field`

**Vai trò cho AI:** Bảng tra customfield_xxxxx → tên + kiểu dữ liệu. Cache 1 lần dùng mãi.

**Cách dùng / lưu ý:** Với custom field dạng select: GET /field/{fieldId}/contexts rồi GET /field/{fieldId}/context/{contextId}/option để lấy danh sách giá trị hợp lệ.

### Context của một custom field

`🟢 GET` `/rest/api/3/field/{fieldId}/context`

**Vai trò cho AI:** Bước trung gian để lấy danh sách giá trị hợp lệ của custom field dạng select/multi-select — cần khi AI muốn set custom field.

**Cách dùng / lưu ý:** Lấy contextId ở đây rồi GET /field/{fieldId}/context/{contextId}/option. (Đừng dùng /contexts số nhiều — Atlassian đã deprecated.) fieldId vd customfield_10020.

---

## 3. Tìm ticket tương tự đã giải quyết

Đây là giai đoạn tạo ra **giá trị cốt lõi**: thay vì để AI phán đoán từ con số 0, ta tìm những ticket *đã từng xảy ra và đã được giải quyết* để AI học từ cách team đã xử lý. Jira chỉ hỗ trợ tìm theo từ khóa (không hiểu ngữ nghĩa), nên giai đoạn này là sự phối hợp: Jira lo phần lọc nhanh ra ứng viên, AI lo phần đọc kỹ và xếp hạng mức độ giống nhau. Vai trò với AI: cung cấp *tiền lệ* — "bug y hệt thế này lần trước fix bằng cách tăng connection pool".

### Enhanced JQL search — endpoint hiện hành

`🟢 GET` `/rest/api/3/search/jql`

**Vai trò cho AI:** Trái tim của việc tìm ticket tương tự. JQL mẫu: statusCategory = Done AND (text ~ "keywords" OR labels in (...)). LƯU Ý: text ~ là keyword search (không semantic) và KHÔNG quét labels.

**Cách dùng / lưu ý:** Endpoint /search cũ đã khai tử. JQL phải bounded (có project=...). Phân trang bằng nextPageToken (không còn startAt). reconcileIssues=[ids] nếu cần đọc-ngay-sau-ghi.

### Enhanced JQL search — bản POST (code thật dùng bản này)

`🔵 POST` `/rest/api/3/search/jql`

**Vai trò cho AI:** Giống bản GET nhưng truyền JQL/fields trong body — bắt buộc khi JQL dài hoặc có ký tự đặc biệt. ai_context.py của service đang dùng đúng bản này.

**Cách dùng / lưu ý:** Body: {"jql": "...", "fields": [...], "maxResults": 50, "nextPageToken": "..."}.

### Issue picker — gợi ý nhanh theo text

`🟢 GET` `/rest/api/3/issue/picker`

**Vai trò cho AI:** Bước tìm ứng viên rẻ và nhanh trước khi search JQL đầy đủ. Trả 2 danh sách: lịch sử người dùng + kết quả khớp text.

**Cách dùng / lưu ý:** query = chuỗi tự do; currentJQL để giới hạn phạm vi; currentProjectId lọc theo project.

### Đếm nhanh số kết quả

`🔵 POST` `/rest/api/3/search/approximate-count`

**Vai trò cho AI:** Biết JQL trả khoảng bao nhiêu ticket trước khi fetch — quyết định có cần thu hẹp điều kiện không.

**Cách dùng / lưu ý:** Body: {"jql": "..."}. JQL phải bounded.

### Validate JQL

`🔵 POST` `/rest/api/3/jql/parse`

**Vai trò cho AI:** Nếu để AI tự sinh JQL: parse trước khi chạy, lỗi thì trả cho AI sửa — tránh request hỏng.

**Cách dùng / lưu ý:** Body: {"queries": ["project = SCRUM AND ..."]}.

### Kiểm tra issue khớp JQL

`🔵 POST` `/rest/api/3/jql/match`

**Vai trò cho AI:** Trả lời câu 'ticket X có thuộc diện Y không' mà không cần search lại toàn bộ.

**Cách dùng / lưu ý:** Body: {"jqls": [...], "issueIds": [...]}.

### Danh mục field/operator JQL

`🟢 GET` `/rest/api/3/jql/autocompletedata`

**Vai trò cho AI:** Đưa vào prompt làm tài liệu tham chiếu để AI sinh JQL đúng cú pháp, đúng tên field của site.

**Cách dùng / lưu ý:** Cache 1 lần.

---

## 4. Phán đoán & hành động (AI quyết → service làm)

Sau khi hiểu ticket và có tiền lệ, AI đưa ra đề xuất. Nhưng AI **không được tự do làm gì tùy thích** — mỗi project có workflow, quyền hạn, danh sách người riêng. Giai đoạn này cung cấp cho AI *khung ràng buộc* (được chuyển sang trạng thái nào, gán cho ai, bot có quyền gì) trước khi quyết định, và các API để *thực thi* quyết định đó. Vai trò với AI: biến phán đoán thành hành động hợp lệ, an toàn, có thể kiểm soát.

### Các bước chuyển hợp lệ

`🟢 GET` `/rest/api/3/issue/{key}/transitions`

**Vai trò cho AI:** AI chỉ được đề xuất chuyển trạng thái trong danh sách này — workflow mỗi project khác nhau, không đoán được.

**Cách dùng / lưu ý:** Lấy transition id ở đây rồi POST cùng đường dẫn để thực hiện.

### Field nào sửa được + giá trị hợp lệ

`🟢 GET` `/rest/api/3/issue/{key}/editmeta`

**Vai trò cho AI:** Trước khi AI đề xuất sửa field: biết field đó có trên màn hình edit không, nhận giá trị gì — tránh đề xuất bất khả thi.

**Cách dùng / lưu ý:** Không tham số.

### Metadata để TẠO ticket

`🟢 GET` `/rest/api/3/issue/createmeta/{project}/issuetypes`

**Vai trò cho AI:** Chỉ cần nếu cho AI tạo ticket mới (vd tách bug, tạo subtask): liệt kê các issue type mà project cho phép tạo.

**Cách dùng / lưu ý:** Đây là bước 1 (lấy issueTypeId). Bước 2: GET /issue/createmeta/{project}/issuetypes/{issueTypeId} để biết field nào bắt buộc của từng loại.

### Người được phép gán (đã test)

`🟢 GET` `/rest/api/3/user/assignable/search`

**Vai trò cho AI:** AI đề xuất assignee phải nằm trong danh sách này, nếu không PUT assignee sẽ 400.

**Cách dùng / lưu ý:** Trả accountId — Jira Cloud chỉ nhận accountId, không nhận username/email.

### Quyền của tài khoản bot (đã test)

`🟢 GET` `/rest/api/3/mypermissions`

**Vai trò cho AI:** Service tự kiểm tra đủ quyền làm hành động AI đề xuất không, trước khi thử và thất bại.

**Cách dùng / lưu ý:** permissions = danh sách permission key cách nhau dấu phẩy.

### Components + lead

`🟢 GET` `/rest/api/3/project/{project}/components`

**Vai trò cho AI:** Mỗi component có 'lead' (người phụ trách) — nguồn cho quy ước 'bug component X → giao lead X'.

**Cách dùng / lưu ý:** Kèm GET /component/{id}/relatedIssueCounts — component nào đang nhiều bug.

### Vai trò trong project

`🟢 GET` `/rest/api/3/project/{project}/role`

**Vai trò cho AI:** Ai là Developer/Admin của project — gợi ý assignee theo vai trò.

**Cách dùng / lưu ý:** Trả URL từng role, gọi tiếp để lấy thành viên.

### Tìm người theo tên

`🟢 GET` `/rest/api/3/groupuserpicker`

**Vai trò cho AI:** Resolve tên người được nhắc trong comment ('giao cho anh Nam') → accountId.

**Cách dùng / lưu ý:** query = tên gần đúng.

### Ghi comment (hành động an toàn nhất — nên là mặc định)

`🔵 POST` `/rest/api/3/issue/{key}/comment`

**Vai trò cho AI:** AI ghi kết quả phân tích + link ticket tương tự + gợi ý cách fix vào ticket.

**Cách dùng / lưu ý:** Body comment phải là ADF.

### Gán người xử lý

`🟠 PUT` `/rest/api/3/issue/{key}/assignee`

**Vai trò cho AI:** Thực thi đề xuất assignee của AI.

**Cách dùng / lưu ý:** Body: {"accountId": "..."}. Kiểm tra assignable trước (xem trên).

### Chuyển trạng thái

`🔵 POST` `/rest/api/3/issue/{key}/transitions`

**Vai trò cho AI:** Thực thi đề xuất chuyển workflow của AI.

**Cách dùng / lưu ý:** Body: {"transition": {"id": "41"}}. Response 204 RỖNG — client phải xử lý body rỗng (đã vấp khi test).

### Sửa field (label, priority, component...)

`🟠 PUT` `/rest/api/3/issue/{key}`

**Vai trò cho AI:** Thực thi đề xuất chỉnh field của AI.

**Cách dùng / lưu ý:** Thêm ?notifyUsers=false để không spam email watcher. Body theo editmeta.

### Gửi thông báo đích danh

`🔵 POST` `/rest/api/3/issue/{key}/notify`

**Vai trò cho AI:** Khi AI xác định cần người cụ thể chú ý (vd nghi trùng ticket đang mở của họ).

**Cách dùng / lưu ý:** Body: {"subject", "textBody", "to": {"users": [...]}}.

### Tạo link giữa 2 ticket

`🔵 POST` `/rest/api/3/issueLink`

**Vai trò cho AI:** AI phát hiện trùng/liên quan → tạo link 'duplicates'/'relates to' để người đọc thấy ngay.

**Cách dùng / lưu ý:** Body: {"type": {"name": "Duplicate"}, "inwardIssue": {"key"}, "outwardIssue": {"key"}}. Danh sách loại link: GET /issueLinkType.

### Issue property — bộ nhớ ẩn của AI trên ticket

`🟠 PUT` `/rest/api/3/issue/{key}/properties/ai-state`

**Vai trò cho AI:** Lưu 'ticket này AI xử lý chưa, kết quả gì' ngay trên ticket mà không làm bẩn field hiển thị → giải quyết webhook bắn trùng (idempotency).

**Cách dùng / lưu ý:** PUT body JSON bất kỳ; GET cùng đường dẫn để đọc lại.

---

## 5. Danh mục ngữ cảnh (cache 1 lần khi khởi động)

Đây là các bảng tra cứu **ít thay đổi** (mức priority, loại resolution, danh sách label, version...). Chúng không gắn với một ticket cụ thể mà mô tả "luật chơi" của cả project. Nên gọi một lần lúc khởi động và cache lại. Vai trò với AI: cung cấp tập giá trị hợp lệ để khi AI đề xuất (vd đổi priority sang "High"), giá trị đó chắc chắn tồn tại và đúng chuẩn của project.

### Tài khoản đang đăng nhập

`🟢 GET` `/rest/api/3/myself`

**Vai trò cho AI:** Smoke test xác thực; lấy accountId của bot để lọc comment do chính bot viết (tránh AI tự đọc lại output của mình).

### Thông tin site

`🟢 GET` `/rest/api/3/serverInfo`

**Vai trò cho AI:** Kiểm tra kết nối + xác nhận deploymentType=Cloud (API v3 chỉ có trên Cloud).

**Cách dùng / lưu ý:** Gọi được không cần đăng nhập.

### Get project — chi tiết 1 project

`🟢 GET` `/rest/api/3/project/{project}`

**Vai trò cho AI:** Lấy projectId (id số, cần cho vài API khác), lead, mô tả, loại project (software/JSM) làm ngữ cảnh.

**Cách dùng / lưu ý:** Nhận projectKey hoặc projectId.

### Get projects — danh sách phân trang

`🟢 GET` `/rest/api/3/project/search`

**Vai trò cho AI:** Liệt kê các project service được phép xử lý — hữu ích khi mở rộng ra nhiều project.

**Cách dùng / lưu ý:** Phân trang startAt/maxResults; query để lọc theo tên/key.

### Các mức priority

`🟢 GET` `/rest/api/3/priority`

**Vai trò cho AI:** AI đề xuất đổi priority phải dùng giá trị trong này.

### Các loại resolution

`🟢 GET` `/rest/api/3/resolution`

**Vai trò cho AI:** Hiểu 'Fixed' khác 'Won't Fix' khi đọc ticket đã đóng.

### Workflow theo issue type của project

`🟢 GET` `/rest/api/3/project/{project}/statuses`

**Vai trò cho AI:** Bug và Task có thể đi workflow khác nhau — AI cần biết trước khi đề xuất.

**Cách dùng / lưu ý:** Toàn site: GET /statuses/search; nhóm trạng thái: GET /statuscategory.

### Toàn bộ labels

`🟢 GET` `/rest/api/3/label`

**Vai trò cho AI:** AI gắn label nên chọn label có sẵn thay vì sinh mới tùy tiện.

### Versions của project

`🟢 GET` `/rest/api/3/project/{project}/versions`

**Vai trò cho AI:** Ngữ cảnh affectedVersion/fixVersion khi AI đề xuất gắn bản phát hành.

**Cách dùng / lưu ý:** Kèm GET /version/{id}/unresolvedIssueCount — version nào còn nhiều bug.

### Issue types của project

`🟢 GET` `/rest/api/3/issuetype/project`

**Vai trò cho AI:** AI phân loại ticket (Bug/Task/Story) theo đúng bộ loại của project.

**Cách dùng / lưu ý:** projectId là id số (lấy từ GET /project/{key}).

---

## 6. Hai họ API ngoài Platform (cùng site, cùng auth, tài liệu riêng)

Jira Cloud có 3 họ API tách biệt. Phần lõi (mọi thứ ở trên) thuộc họ Platform. Hai họ còn lại chỉ cần đến trong tình huống cụ thể: **Agile** khi cần ngữ cảnh sprint/board, **JSM** khi ticket là yêu cầu hỗ trợ của khách hàng. Vai trò với AI: bổ sung ngữ cảnh chuyên biệt mà họ Platform không có.

### Agile API — boards

`🟢 GET` `/rest/agile/1.0/board`

**Vai trò cho AI:** Ngữ cảnh Scrum/Kanban: ticket thuộc board nào. Platform API chỉ lộ sprint qua customfield.

**Cách dùng / lưu ý:** Họ /rest/agile/1.0/: board/{id}/sprint (sprint active), sprint/{id}/issue, epic... Tài liệu: developer.atlassian.com → Jira Software Cloud REST API.

### Agile API — sprint đang chạy

`🟢 GET` `/rest/agile/1.0/board/{boardId}/sprint`

**Vai trò cho AI:** Ticket mới có thuộc sprint hiện tại không → mức độ khẩn cấp khác nhau.

**Cách dùng / lưu ý:** boardId từ GET /rest/agile/1.0/board.

### JSM API — support request

`🟢 GET` `/rest/servicedeskapi/request/{key}`

**Vai trò cho AI:** CHỈ cần khi ticket là support request của khách hàng (project JSM): SLA, request type, comment public/internal (cờ jsdPublic).

**Cách dùng / lưu ý:** Site phải bật Jira Service Management. Với ticket software thuần thì bỏ qua nhóm này.

---

## Ghi nhớ tổng quát

1. **Webhook chỉ là chuông báo** — luôn gọi lại `GET /issue` để có dữ liệu tươi và đầy đủ.
2. **Service làm sạch dữ liệu trước khi đưa AI** — chuyển ADF → text, dịch customfield_xxxxx → tên thật. AI không nên phải tự xử lý định dạng máy.
3. **AI đề xuất, không tự tung tự tác** — mọi hành động phải nằm trong khung `transitions` + `assignable_users` + `permissions` mà API trả về.
4. **Tìm tương tự là keyword, không phải ngữ nghĩa** — Jira lọc thô, AI xếp hạng tinh. Cần ngữ nghĩa thật thì phải có vector DB riêng (ngoài phạm vi Jira API).
5. **Hành động mặc định nên là comment** — an toàn nhất; các hành động mạnh hơn (chuyển trạng thái, gán người) nên có người duyệt cho tới khi tin tưởng AI.
