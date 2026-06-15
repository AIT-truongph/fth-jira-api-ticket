# -*- coding: utf-8 -*-
# Sinh API_GUIDE.md - giai thich chi tiet vai tro tung API khi dung cho AI.
# Noi dung tung API lay tu catalog_data.py (luon dong bo voi web + Postman);
# phan dan nhap / vi du chuoi goi duoc viet tay o duoi.
# Chay: python generate_api_guide.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from catalog_data import CATALOG

OUT = Path(__file__).parent / "API_GUIDE.md"

# Dan nhap chi tiet cho tung nhom (giai thich vai tro cua CA GIAI DOAN trong flow AI)
GROUP_INTRO = {
    "1. Trigger — Webhook (Jira chủ động gọi mình)":
        "Đây là **điểm bắt đầu** của toàn bộ hệ thống. Thay vì cứ vài giây lại hỏi Jira "
        "\"có ticket nào mới không\" (tốn tài nguyên, chậm), ta đăng ký webhook một lần để "
        "Jira **tự gọi sang** mỗi khi có thay đổi. Webhook không mang đủ dữ liệu để AI làm việc — "
        "nó chỉ là *tiếng chuông báo* kèm khóa ticket (issue.key). Vai trò của giai đoạn này với AI: "
        "khởi động đúng lúc, đúng ticket, và lọc sẵn rác (qua JQL filter) để AI không bị gọi dậy "
        "bởi những thay đổi không liên quan.",
    "2. Đọc hiểu ticket (input chính cho AI)":
        "Sau khi webhook báo, đây là giai đoạn **thu thập toàn bộ dữ liệu** để AI thực sự hiểu "
        "ticket đang nói về cái gì. Một ticket không chỉ là tiêu đề + mô tả: nó còn có comment "
        "(nơi chứa thảo luận và manh mối), lịch sử thay đổi (đã qua tay ai, bị trả lại mấy lần), "
        "file đính kèm (log, ảnh lỗi), và hàng loạt custom field. Vai trò của giai đoạn này với AI: "
        "biến dữ liệu thô, rời rạc, định dạng máy (ADF, customfield_xxxxx) thành một bức tranh "
        "sạch sẽ, đầy đủ ngữ cảnh mà mô hình ngôn ngữ đọc được.",
    "3. Tìm ticket tương tự đã giải quyết":
        "Đây là giai đoạn tạo ra **giá trị cốt lõi**: thay vì để AI phán đoán từ con số 0, ta tìm "
        "những ticket *đã từng xảy ra và đã được giải quyết* để AI học từ cách team đã xử lý. "
        "Jira chỉ hỗ trợ tìm theo từ khóa (không hiểu ngữ nghĩa), nên giai đoạn này là sự phối hợp: "
        "Jira lo phần lọc nhanh ra ứng viên, AI lo phần đọc kỹ và xếp hạng mức độ giống nhau. "
        "Vai trò với AI: cung cấp *tiền lệ* — \"bug y hệt thế này lần trước fix bằng cách tăng "
        "connection pool\".",
    "4. Phán đoán & hành động (AI quyết → service làm)":
        "Sau khi hiểu ticket và có tiền lệ, AI đưa ra đề xuất. Nhưng AI **không được tự do làm gì "
        "tùy thích** — mỗi project có workflow, quyền hạn, danh sách người riêng. Giai đoạn này "
        "cung cấp cho AI *khung ràng buộc* (được chuyển sang trạng thái nào, gán cho ai, bot có "
        "quyền gì) trước khi quyết định, và các API để *thực thi* quyết định đó. Vai trò với AI: "
        "biến phán đoán thành hành động hợp lệ, an toàn, có thể kiểm soát.",
    "5. Danh mục ngữ cảnh (cache 1 lần khi khởi động)":
        "Đây là các bảng tra cứu **ít thay đổi** (mức priority, loại resolution, danh sách label, "
        "version...). Chúng không gắn với một ticket cụ thể mà mô tả \"luật chơi\" của cả project. "
        "Nên gọi một lần lúc khởi động và cache lại. Vai trò với AI: cung cấp tập giá trị hợp lệ "
        "để khi AI đề xuất (vd đổi priority sang \"High\"), giá trị đó chắc chắn tồn tại và đúng "
        "chuẩn của project.",
    "6. Hai họ API ngoài Platform (cùng site, cùng auth, tài liệu riêng)":
        "Jira Cloud có 3 họ API tách biệt. Phần lõi (mọi thứ ở trên) thuộc họ Platform. Hai họ còn "
        "lại chỉ cần đến trong tình huống cụ thể: **Agile** khi cần ngữ cảnh sprint/board, **JSM** "
        "khi ticket là yêu cầu hỗ trợ của khách hàng. Vai trò với AI: bổ sung ngữ cảnh chuyên biệt "
        "mà họ Platform không có.",
}

# Vi du chuoi goi that (tu trace thuc te khi build context cho SCRUM-7)
FLOW_EXAMPLE = """\
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
"""

METHOD_BADGE = {"GET": "🟢 GET", "POST": "🔵 POST", "PUT": "🟠 PUT", "DELETE": "🔴 DELETE"}


def main():
    lines = []
    lines.append("# Vai trò từng API Jira khi dùng cho AI xử lý ticket\n")
    lines.append(
        "> Tài liệu này giải thích **mỗi API đóng vai trò gì** trong hệ thống AI nhận webhook → "
        "đọc hiểu ticket → tìm ticket tương tự → phán đoán hành động.\n>\n"
        "> Sinh tự động từ `catalog_data.py` bằng `python generate_api_guide.py` — luôn khớp với "
        "web demo và Postman collection. Tổng cộng **%d API**, chia 6 giai đoạn theo luồng xử lý.\n"
        % sum(len(g["items"]) for g in CATALOG)
    )

    # Muc luc (anchor theo thuat toan GitHub: bo dau cau, space -> '-')
    import re as _re
    def gh_anchor(s):
        s = s.lower()
        s = _re.sub(r"[^\w\s-]", "", s)  # giu chu (ke ca tieng Viet), so, space, '-'
        return s.replace(" ", "-")
    lines.append("## Mục lục\n")
    for g in CATALOG:
        lines.append(f"- [{g['group']}](#{gh_anchor(g['group'])}) — {len(g['items'])} API")
    lines.append("")
    lines.append(FLOW_EXAMPLE)

    # Tung nhom
    for g in CATALOG:
        lines.append(f"## {g['group']}\n")
        intro = GROUP_INTRO.get(g["group"])
        if intro:
            lines.append(intro + "\n")
        for it in g["items"]:
            badge = METHOD_BADGE.get(it["method"], it["method"])
            lines.append(f"### {it['name']}\n")
            lines.append(f"`{badge}` `{it['path'].split('?')[0]}`\n")
            lines.append(f"**Vai trò cho AI:** {it['ai']}\n")
            if it.get("how"):
                lines.append(f"**Cách dùng / lưu ý:** {it['how']}\n")
        lines.append("---\n")

    lines.append(
        "## Ghi nhớ tổng quát\n\n"
        "1. **Webhook chỉ là chuông báo** — luôn gọi lại `GET /issue` để có dữ liệu tươi và đầy đủ.\n"
        "2. **Service làm sạch dữ liệu trước khi đưa AI** — chuyển ADF → text, dịch customfield_xxxxx "
        "→ tên thật. AI không nên phải tự xử lý định dạng máy.\n"
        "3. **AI đề xuất, không tự tung tự tác** — mọi hành động phải nằm trong khung "
        "`transitions` + `assignable_users` + `permissions` mà API trả về.\n"
        "4. **Tìm tương tự là keyword, không phải ngữ nghĩa** — Jira lọc thô, AI xếp hạng tinh. "
        "Cần ngữ nghĩa thật thì phải có vector DB riêng (ngoài phạm vi Jira API).\n"
        "5. **Hành động mặc định nên là comment** — an toàn nhất; các hành động mạnh hơn "
        "(chuyển trạng thái, gán người) nên có người duyệt cho tới khi tin tưởng AI.\n"
    )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Da sinh {OUT.name}: {sum(len(g['items']) for g in CATALOG)} API, {len(OUT.read_text(encoding='utf-8').splitlines())} dong")


if __name__ == "__main__":
    main()
