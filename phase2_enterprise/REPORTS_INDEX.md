# Phase 2 — Tài liệu thiết kế Enterprise

> ⚠️ **Đây KHÔNG phải là câu trả lời cho task gốc.** Task gốc chỉ là *"điều tra Jira API cho AI đọc/hiểu ticket + đề xuất hướng"* — câu trả lời đó nằm ở **[../BAO_CAO_DIEU_TRA.md](../BAO_CAO_DIEU_TRA.md)** (1–2 trang).
>
> Thư mục này là **phase tiếp theo**: *"giả sử công ty quyết định làm thật, thì làm thế nào cho đúng ở quy mô enterprise."* Chỉ đọc khi đã qua quyết định **"có nên đầu tư hay không"**.
>
> 👉 **Đọc trước hết:** [../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md) — JSM đã có sẵn ~80% use case (Draft Replies, Service Request Helper, AI Suggestions Panel). Đánh giá native (rẻ, 2–3 tuần) trước khi cân nhắc bất kỳ thứ gì trong thư mục này.

## Thứ tự đọc đề xuất (cho người ra quyết định)

Đọc từ "có đáng làm không" → "làm thế nào", không phải ngược lại:

| # | Tài liệu | Trả lời câu hỏi | Một dòng kết luận |
|---|---|---|---|
| 1 | [REPORT_POV_PLAN.md](REPORT_POV_PLAN.md) | **Ý tưởng có đáng đầu tư không?** | PoV offline 5 tuần, không rủi ro production; gate quyết định là "AI có hơn search thường không". |
| 2 | [REPORT_DATA_READINESS.md](REPORT_DATA_READINESS.md) | **Dữ liệu lịch sử có đủ tốt không?** | Điểm sẵn sàng 0–100; mấu chốt là "cách fix có được ghi lại không". |
| 3 | [REPORT_BUILD_VS_BUY.md](REPORT_BUILD_VS_BUY.md) | **Tự xây hay mua?** | Mua native (JSM AI + Rovo) thắng 85 vs 50; tự xây chỉ cho phần khác biệt. Đào sâu native: [../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md). |
| 4 | [REPORT_MVP_DESIGN.md](REPORT_MVP_DESIGN.md) | **MVP rủi ro thấp nhất ra sao?** | Suggest-only, 1 category, 12 tuần, người luôn kiểm soát. |
| 5 | [REPORT_AI_TICKET_ARCHITECTURE.md](REPORT_AI_TICKET_ARCHITECTURE.md) | **Kiến trúc production đầy đủ?** | 6 lớp; Jira = nguồn sự thật + API hành động; CBR + hybrid retrieval. |
| 6 | [REPORT_CRITICAL_REVIEW.md](REPORT_CRITICAL_REVIEW.md) | **Có gì sai/rủi ro?** | Phản biện độc lập: causation của "87%", buy-vs-build, security là launch-blocker. |

## Lưu ý

- Các report **do người dùng yêu cầu lần lượt** trong quá trình brainstorm — không phải scope gốc.
- Chúng nhất quán với nhau và liên kết chéo; đọc theo thứ tự trên là mạch lạc nhất.
- Tinh thần xuyên suốt: **reliability > automation** — chứng minh giá trị rẻ trước (PoV), tự động hóa từng bước có kiểm soát sau.
