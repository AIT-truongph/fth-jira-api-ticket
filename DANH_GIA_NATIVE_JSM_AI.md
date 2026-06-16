# Đánh giá Native JSM AI — trước khi cân nhắc tự xây

**Góc nhìn:** Jira architect ~10 năm. **Mục đích:** trả lời câu hỏi tiền-đầu-tư — *use case "AI xử lý ticket mới dựa vào ticket cũ → đề xuất hành động" có cần tự xây không, hay JSM đã làm sẵn?*

**Kết luận một dòng:** **Phần lớn use case đã có sẵn trong JSM. Không nên xây gì trước khi bật thử native và đo.** Việc tự xây (nếu có) chỉ nên nhắm vào vài khoảng trống cụ thể native không làm — và chỉ sau khi native chứng minh dữ liệu của bạn đủ tốt.

---

## 1. Bản đồ yêu cầu → tính năng native

| Yêu cầu của bạn | Tính năng JSM native | Mức đáp ứng |
|---|---|---|
| Đọc & hiểu ticket mới | **AI Summaries**, **Sentiment Analysis** | ✅ Đủ |
| Tìm ticket cũ tương tự | **Similar Requests** (NLP) — *(đây là duplicate-detection bạn KHÔNG muốn)* | ✅ (nhưng không phải mục tiêu) |
| Dựa ticket cũ → gợi cách xử lý | **Draft Replies** (gợi reply từ ticket tương tự **đã resolved**); **Service Request Helper** (Rovo) — *"compose responses using insights from previous requests, recommend next steps"* | ✅ Gần đúng mục tiêu |
| Đề xuất hành động (assign / escalate / troubleshooting) | **AI Suggestions Panel** — *"assignees, escalation paths, troubleshooting steps"* | ✅ Đủ (suggest-only) |
| Định tuyến / phân loại / ưu tiên | **AI Triage / Service Triage Assistant** (request type, urgency, priority) | ✅ Đủ |
| Mention đúng SME | **Predictive Agent Assignment & @mentions** | ✅ Một phần |
| Tự động đóng / thực thi không người | (Automation + Rovo agent, nhưng hạn chế) | ⚠️ Một phần / yếu |
| Con số tỉ lệ thành công tường minh ("87% restart service") | — | ❌ Không có |

→ **Cột "mức đáp ứng" cho thấy native phủ ~80% use case ở mức gợi ý cho agent (đúng tinh thần human-in-control).**

## 2. Tính năng cốt lõi & cách hoạt động (đã kiểm chứng qua docs Atlassian)

- **Draft Replies** — *khớp nhất với kịch bản của bạn.* AI soạn phản hồi dựa trên *"responses added by agents while resolving similar work items in the past"*. Tức là: ticket "VPN không kết nối" → lấy cách agent đã trả lời các ticket VPN tương tự **đã resolved** → gợi ý reply (vd "thử restart VPN Agent service"). Agent chèn/sửa/đổi giọng văn rồi gửi.
- **Service Request Helper (Rovo Agent)** — trợ lý cho agent: tìm SME, soạn phản hồi từ request trước, tóm tắt, **gợi bước tiếp theo**.
- **AI Suggestions Panel** — gợi assignee, đường escalate, bước khắc phục.
- **AI Triage** — phân loại request type, độ khẩn, ưu tiên (phần routing).

## 3. Giới hạn quan trọng (đánh giá thật, không tô hồng)

1. **Phụ thuộc tuyệt đối vào dữ liệu lịch sử.** Draft Replies **không sinh gợi ý nếu không có ticket tương tự ở trạng thái Resolved**; nếu ticket tương tự đang ở trạng thái khác → cũng không có. → Đây chính là điều [Data Readiness](phase2_enterprise/REPORT_DATA_READINESS.md) cảnh báo: *cách fix có được ghi lại trên ticket đã resolved không.* Công cụ tốt vẫn vô dụng nếu dữ liệu mỏng.
2. **Suggest-only, không tự động.** Đúng ràng buộc "human-in-control" của bạn hiện tại — nhưng nếu sau này muốn **autonomous execution có confidence gating**, native chưa làm turnkey (chỉ qua Automation, hạn chế).
3. **Không có thống kê tỉ lệ thành công.** Native gợi *cách làm*, không đưa con số *"80/100 ticket fix bằng restart, 87% thành công"*. Nếu bạn cần chỉ số định lượng này để ra quyết định → đó là khoảng trống.
4. **Grounding thiên về KB + reply cũ**, không phải "khai thác case có cấu trúc" trên toàn bộ lịch sử. Chất lượng phụ thuộc KB (Confluence) được duy trì tốt đến đâu.
5. **Hộp đen.** Không tự tinh chỉnh được retrieval/logic; phụ thuộc roadmap & credit-pricing của Atlassian.

## 4. Điều kiện, chi phí, bảo mật

- **Plan:** Rovo đầy đủ (Search/Chat/Agents/Studio) cần Standard/Premium/Enterprise; các tính năng AI agent cho agent thường ở **Premium/Enterprise** (~$47–51/agent/tháng). Bật **mặc định** trên Premium/Enterprise, admin có thể opt-out. Rovo agent ở **portal/help-center** đã mở cho mọi tài khoản.
- **Chi phí AI:** theo **credit** (biến thiên theo mức dùng).
- **Bảo mật (điểm mạnh lớn so với tự xây):** Atlassian hỗ trợ **Data Residency** và **zero-day retention** (không lưu/không log dữ liệu lâu dài). → Tự xây sẽ phải tự giải quyết PII egress, DPA, ACL — native cho sẵn (đúng các rủi ro [Critical Review §5](phase2_enterprise/REPORT_CRITICAL_REVIEW.md) nêu).
- **Permission model:** native chạy trong mô hình quyền của Jira (tôn trọng internal/public, issue-level security) — thứ tự xây rất khó làm đúng.

## 5. Khoảng trống native KHÔNG làm (chỗ *có thể* cân nhắc tự xây — sau)

- Thống kê **tỉ lệ thành công theo hành động** ("action X: n lần, 87% thành công").
- **Tự động thực thi** có ngưỡng tin cậy + kiểm soát (autonomous, nhưng bạn đang chủ động *không* muốn ở giai đoạn này).
- **Semantic search tùy biến** trên toàn bộ ticket history với logic xếp hạng riêng (native thiên KB + reply cũ).
- **Analytics/dashboard** về resolution patterns để cải tiến quy trình.

→ Đây đều là phần **tăng thêm**, không phải phần lõi. Phần lõi native đã có.

## 6. Kế hoạch đánh giá native — rẻ, ~2–3 tuần, KHÔNG xây gì

1. **Tuần 0:** dùng một site **Premium/Enterprise** (hoặc trial); bật Rovo + các tính năng agent. Chọn **1 category nhiều ticket đã resolved** (vd VPN/Access/Password — nơi cách fix thường được ghi lại).
2. **Tuần 1–2:** cho 3–5 agent dùng thật **Draft Replies + AI Suggestions Panel + Service Request Helper** trên category đó. Song song chạy **Data Readiness Pass A** để biết bao nhiêu ticket có gợi ý được sinh ra.
3. **Đo:**
   - **Coverage** — % ticket mới có draft/gợi ý được sinh (nếu thấp → vấn đề dữ liệu).
   - **Tỉ lệ hữu ích** — % gợi ý agent đánh giá tốt (👍/👎).
   - **Tỉ lệ dùng** — % gợi ý được chèn/sửa rồi gửi.
   - **Thời gian xử lý** so với baseline không dùng.
4. **Chi phí:** chỉ là plan + thời gian agent — **không tốn ngày dev nào.**

## 7. Khung quyết định Mua (native) vs Xây

| Kết quả đánh giá native | Quyết định |
|---|---|
| Coverage & tỉ lệ hữu ích **đạt** | 🟢 **Dùng native — không xây.** Đầu tư vào duy trì KB + kỷ luật ghi cách fix để native tốt hơn. |
| Native tốt nhưng **thiếu** phần cụ thể (vd cần thống kê tỉ lệ thành công / autonomous) | 🟡 **Native lo 80%, xây mỏng phần delta** trên nền native (theo [Build-vs-Buy](phase2_enterprise/REPORT_BUILD_VS_BUY.md)). |
| Native **không sinh đủ gợi ý vì dữ liệu mỏng** | 🔴 Vấn đề là **dữ liệu, không phải công cụ.** Tự xây cũng sẽ thất bại. Ưu tiên cải thiện dữ liệu/KB trước, rồi đánh giá lại. |

## 8. Khuyến nghị (senior)

> **Đừng xây trước. Bật native, đo trong 2–3 tuần.** Atlassian đã làm sẵn phần lõi "gợi cách xử lý dựa trên ticket cũ" (Draft Replies, Service Request Helper, AI Suggestions Panel) — ngay trong mô hình quyền và bảo mật của Jira, không cần đẩy dữ liệu ra ngoài. Phép thử rẻ nhất cho cả ý tưởng *và* chất lượng dữ liệu chính là dùng thử công cụ có sẵn. Chỉ khi native chạy tốt nhưng thiếu một năng lực cụ thể (thống kê tỉ lệ thành công, hoặc tự động hóa có kiểm soát) thì mới xây thêm — và xây **mỏng, trên nền native**, không xây lại từ đầu.

---

### Nguồn
- [AI feature guide — Jira Service Management (Atlassian)](https://www.atlassian.com/software/jira/service-management/product-guide/tips-and-tricks/artificial-intelligence)
- [Atlassian Support — Draft Replies (điều kiện cần ticket tương tự đã Resolved)](https://support.atlassian.com/jira/kb/atlassian-intelligence-draft-replies-not-working-for-jira-service-management-cloud/)
- [Rovo plans & enablement](https://bestagenthub.com/tools/atlassian-rovo) · [Rovo agents](https://support.atlassian.com/rovo/docs/agents/) · [Knowledge sources for agents](https://support.atlassian.com/rovo/docs/knowledge-sources-for-agents/)
- Liên quan: [Build vs Buy](phase2_enterprise/REPORT_BUILD_VS_BUY.md) · [Data Readiness](phase2_enterprise/REPORT_DATA_READINESS.md)
