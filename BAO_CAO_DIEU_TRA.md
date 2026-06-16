# Báo cáo điều tra: Jira API cho AI đọc & xử lý ticket

**Người thực hiện:** (điền tên) · **Ngày:** (điền) · **Trạng thái:** Điều tra — đề xuất hướng

**Phạm vi task:** điều tra Jira có những API nào để AI **đọc và hiểu ticket**, tìm ticket cũ tương tự, và đề xuất hành động. Phần tích hợp AI do team AI đảm nhận. *(Không bao gồm: thiết kế hệ thống production, chọn vector DB, governance, ROI — đó là phase sau nếu công ty quyết định làm thật, xem [phase2_enterprise/](phase2_enterprise/).)*

---

## Kết luận nhanh (TL;DR)

- **Jira API hoàn toàn đủ dữ liệu** cho mục tiêu này: lấy được issue, comments, changelog, attachments, lịch sử giải quyết, và thực hiện hành động (comment/assign/transition).
- Mục tiêu là **Action Recommendation** (dựa vào ticket cũ để biết *nên làm gì*), **không phải** Duplicate Detection (tìm ticket giống).
- **Hướng đề xuất:** Semantic Search + AI Recommendation. Giai đoạn đầu chỉ **comment đề xuất**, người vẫn kiểm soát, chưa tự động đóng ticket.
- Đã kiểm chứng API thật trên một site Jira Cloud → có vài điểm kỹ thuật quan trọng (mục 2) team AI cần biết trước.

---

## 1. Các Jira API cần dùng

| Nhóm | API | Vai trò |
|---|---|---|
| **Kích hoạt (trigger)** | Webhook `jira:issue_created` / `issue_updated` (đăng ký qua `POST /rest/webhooks/1.0/webhook`, kèm JQL filter) | Jira tự gọi sang khi có ticket mới/đổi — điểm bắt đầu của flow. **Lưu ý:** chỉ lấy `issue.key` từ payload rồi gọi `GET issue` để có dữ liệu đầy đủ (payload event comment bị rút gọn; thứ tự event không đảm bảo). |
| **Đọc & hiểu ticket** | `GET /rest/api/3/issue/{key}` (`expand=renderedFields,names,changelog`) | Lấy gần như toàn bộ: summary, description, status, priority, custom field, links, subtasks, changelog. |
| | `GET /rest/api/3/issue/{key}/comment` | Đọc thảo luận — nơi thường chứa nguyên nhân & cách fix. |
| | `GET /rest/api/3/issue/{key}/changelog` | Lịch sử thay đổi (ai xử lý, qua những bước nào). |
| | `GET /rest/api/3/attachment/content/{id}` | Tải nội dung file đính kèm (log, ảnh lỗi). |
| **Tìm ticket tương tự** | `POST /rest/api/3/search/jql` | Tìm ticket bằng JQL (endpoint hiện hành). |
| | `POST /rest/api/3/issue/bulkfetch` | Lấy chi tiết tối đa 100 ticket/lần. |
| **Hành động (team AI thực thi)** | `POST /rest/api/3/issue/{key}/comment` | Thêm comment đề xuất (hành động an toàn nhất). |
| | `PUT /rest/api/3/issue/{key}/assignee` | Gán người xử lý. |
| | `GET` + `POST /rest/api/3/issue/{key}/transitions` | Lấy & thực hiện chuyển trạng thái. |
| | `GET /rest/api/3/user/assignable/search` | Danh sách người được phép gán (trước khi đề xuất assignee). |
| **Nếu là Service Desk (JSM)** | `/rest/servicedeskapi/request/{id}/sla`, `/comment` | SLA (ưu tiên/escalate) và comment **public vs internal**. |

> Danh mục đầy đủ 52 API + giải thích vai trò: xem `API_GUIDE.md`, web demo (`web_demo.py`), và Postman collection (`Jira_AI.postman_collection.json`) trong cùng repo.

## 2. Lưu ý kỹ thuật quan trọng (đã kiểm chứng trên Jira thật)

- Dùng **`/search/jql`** — endpoint `/search` cũ Atlassian **đã khai tử**.
- description/comment trả về dạng **ADF (JSON)**, không phải text thuần → cần convert cho AI đọc. (Webhook lại trả text thuần — phải xử lý cả hai.)
- Jira Cloud chỉ nhận **`accountId`**, không nhận username/email (do GDPR).
- **`text ~` trong JQL chỉ là keyword search, KHÔNG phải semantic** — đây là lý do cốt lõi vì sao Hướng 2 (semantic) tốt hơn nhiều cho bài toán này.
- Rate limit theo cost-budget từng tenant; cần xử lý `429`.

## 3. Ba hướng triển khai khả thi

**Hướng 1 — JQL Search → AI comment**
`Ticket mới → JQL text ~ → ticket tương tự → AI comment`
- Ưu: nhanh, dễ làm, chỉ dùng API sẵn có, không cần hạ tầng ngoài.
- Nhược: chỉ khớp từ khóa → chất lượng thấp, không "hiểu" ngữ nghĩa, dễ sót.

**Hướng 2 — Semantic Search → AI Recommendation** ⭐
`Ticket mới → index ticket lịch sử (vector) → tìm tương tự theo ngữ nghĩa → AI đề xuất action`
- Ưu: chính xác hơn hẳn, đúng tinh thần "dựa vào ticket cũ để biết nên làm gì", xử lý được cách diễn đạt khác nhau.
- Nhược: phải đồng bộ dữ liệu ra một store ngoài Jira; phức tạp hơn Hướng 1.

**Hướng 3 — Knowledge Base + ticket lịch sử + AI Agent**
`Ticket mới → KB + lịch sử → AI Agent → đề xuất/thực thi hành động`
- Ưu: mạnh nhất, là hướng tương lai (đề xuất + tự động hóa có kiểm soát).
- Nhược: tốn công nhất, cần governance & quy trình kiểm soát.

## 4. Hướng đề xuất

Với quy mô **hàng trăm nghìn ticket**, đề xuất **Hướng 2 — Semantic Search + AI Recommendation**:
- Jira API đủ dữ liệu để thực hiện (issue, comments, changelog, attachments, resolution history).
- `text ~` của Jira không đủ (chỉ keyword) → cần semantic search ở store ngoài.
- **Giai đoạn đầu chỉ comment đề xuất, người vẫn quyết định** — chưa tự động assign/đóng ticket. Hướng 3 là bước tiến hóa tiếp theo khi đã tin tưởng.

**Lộ trình hành động (đúng yêu cầu "tự phán đoán hết"):** comment đề xuất *(an toàn nhất, làm trước)* → gán người / kéo SME vào (`assignee` + `watcher` + @mention) → escalate / đổi priority → cuối cùng mới **tự đóng ticket** (`transition` sang Done) khi độ tin cậy đủ cao. Mỗi mức là một bước "nới quyền" có kiểm soát.

## 4.1 Kết hợp API ở quy mô hàng trăm nghìn ticket

Điểm mấu chốt về quy mô: **KHÔNG quét toàn bộ ticket qua Jira API mỗi lần có ticket mới** (sẽ đụng rate limit và cực chậm). Mẫu kết hợp đúng:

1. **Backfill 1 lần (offline):** xuất toàn bộ ticket lịch sử qua `POST /search/jql` (phân trang bằng `nextPageToken`) + `POST /issue/bulkfetch` (100 ticket/lần), **có throttle** để không giành rate-budget với người dùng thật → đẩy vào một **index ngoài Jira** (semantic/vector).
2. **Realtime (online):** webhook báo ticket mới → chỉ `GET issue` đúng 1 ticket đó → tìm tương tự **trong index ngoài** (không gọi Jira) → AI đề xuất → ghi 1 comment.
3. **Đồng bộ tăng dần:** webhook cập nhật index khi ticket đổi; thêm 1 lần quét `updated >= -1d` mỗi đêm để bù event lỡ.

→ Jira chỉ chịu tải: 1 lần backfill + mỗi ticket mới ~1–2 call. Việc "tìm trong hàng trăm nghìn ticket" do index ngoài lo, không phải Jira API.

## ⚠️ 4.2 Quan trọng: JSM đã có sẵn phần lớn — đánh giá native TRƯỚC khi tự xây

Trong quá trình điều tra phát hiện: **Atlassian JSM đã có sẵn tính năng làm gần đúng use case này** (gợi cách xử lý ticket mới dựa trên ticket cũ), ngay trong mô hình quyền và bảo mật của Jira. Đáng chú ý Atlassian tách đúng hai thứ ta đã phân biệt:

| | Tính năng native |
|---|---|
| ❌ Tìm ticket giống (duplicate — KHÔNG muốn) | **Similar Requests** |
| ✅ Dựa ticket cũ → gợi cách xử lý (MUỐN) | **Draft Replies**, **Service Request Helper** (Rovo), **AI Suggestions Panel** |
| Phân loại / định tuyến / ưu tiên | **AI Triage** |

- **Draft Replies** khớp nhất: gợi phản hồi dựa trên cách agent đã xử lý ticket tương tự **đã resolved** — đúng kịch bản "VPN lỗi → ticket cũ restart service → đề xuất restart".
- Đều là **gợi ý cho agent, người vẫn quyết định** — khớp ràng buộc "human-in-control".
- **Giới hạn:** chỉ chạy khi có ticket tương tự **đã Resolved** (phụ thuộc dữ liệu); không cho con số tỉ lệ thành công tường minh; cần Premium/Enterprise + Rovo.

> **Khuyến nghị:** **đừng xây trước.** Bật native và đo trong 2–3 tuần — đây là phép thử rẻ nhất cho cả ý tưởng lẫn chất lượng dữ liệu. Chỉ xây thêm nếu native thiếu năng lực cụ thể (vd thống kê tỉ lệ thành công, hoặc tự động hóa có kiểm soát), và xây **mỏng trên nền native**. Chi tiết đánh giá + kế hoạch đo + khung quyết định mua-vs-xây: **[DANH_GIA_NATIVE_JSM_AI.md](DANH_GIA_NATIVE_JSM_AI.md)**.

## 5. Đã chuẩn bị sẵn (ngoài phạm vi báo cáo, để team AI dùng ngay)

- **Web demo** (`web_demo.py`): xem trực quan + gọi thử từng API.
- **Postman collection** (`Jira_AI.postman_collection.json`): 52 request, folder/tên theo đúng tài liệu Jira.
- **`API_GUIDE.md`**: giải thích chi tiết vai trò từng API cho AI.

## 6. Nếu công ty quyết định làm thật → Phase 2

Bộ tài liệu thiết kế enterprise (kiến trúc production, phản biện rủi ro, đánh giá độ sẵn sàng dữ liệu, build-vs-buy, MVP, PoV) đã được chuẩn bị ở **[phase2_enterprise/](phase2_enterprise/)** — chỉ đọc khi đã qua bước "có nên đầu tư không".
