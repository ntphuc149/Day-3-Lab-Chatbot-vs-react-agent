# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Vũ Đăng Khiêm
- **Student ID**: 2A202600727
- **Date**: 14/08/2005

---

## I. Technical Contribution (15 Points)

*Describe your specific contribution to the codebase (e.g., implemented a specific tool, fixed the parser, etc.).*

- **Modules Implementated**: 
  - Giao diện người dùng: `web/index.html` (Thiết kế và xây dựng giao diện web).
  - Thu thập dữ liệu: Crawl/Chuẩn bị dữ liệu điểm chuẩn (ví dụ `data/diem_chuan.json`, `data/to_hop_mon.json`).
- **Code Highlights**: 
  - Xây dựng giao diện frontend hoàn chỉnh, thân thiện với tính năng chat, hiển thị hội thoại và trạng thái "đang gõ" (typing indicator).
  - Thực hiện thu thập, xử lý các dữ liệu tuyển sinh thực tế để cung cấp thông tin chính xác nhất cho Agent hoạt động.
- **Documentation**: Thu thập dữ liệu làm nguồn kiến thức cho Agent phân tích, thiết kế giao diện (UI) kết nối với API backend để người dùng tương tác dễ dàng với hệ thống ReAct Agent.

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event you encountered during the lab using the logging system.*

- **Problem Description**: Giao diện UI liên tục báo lỗi "Không kết nối được server" khi cố gắng tạo session mới hoặc gửi tin nhắn cho Agent, mặc dù server backend Python đã báo "Running on http://127.0.0.1:5000".
- **Log Source**: Browser Console Error: `Fetch API cannot load http://localhost:5000/api/session/new. Failed to fetch (ERR_CONNECTION_REFUSED)`.
- **Diagnosis**: Lỗi xuất phát từ chính sách bảo mật CORS (Cross-Origin Resource Sharing) của trình duyệt khi frontend (chạy trực tiếp từ file HTML trên máy) cố gọi API của backend Flask (chạy ở cổng 5000) với domain/port khác biệt, hoặc do server không lắng nghe tất cả các interface.
- **Solution**: Sửa lỗi bằng cách thêm thư viện `flask-cors` vào backend (`CORS(app)`) và đảm bảo trong `web/index.html` gọi đúng địa chỉ IP (sử dụng `http://127.0.0.1:5000` hoặc `http://localhost:5000` tùy theo cách server bind host).

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

*Reflect on the reasoning capability difference.*

1.  **Reasoning**: Tư duy theo từng bước (Thought) giúp Agent phân tích kỹ lưỡng các câu hỏi phức tạp của người dùng (như khối thi, điểm, sở thích) thay vì trả lời theo khuôn mẫu của Chatbot.
2.  **Reliability**: Việc Agent sử dụng dữ liệu thực tế thu thập được giúp thông tin đưa ra rất chính xác, tuy nhiên có thể chậm hơn Chatbot bình thường do phải thực thi các tools để tra cứu dữ liệu.
3.  **Observation**: Dữ liệu từ môi trường và các tools giúp định hướng Agent đưa ra lời khuyên thực tế nhất thay vì thông tin ảo (hallucination).

---

## IV. Future Improvements (5 Points)

*How would you scale this for a production-level AI agent system?*

- **Scalability**: Nâng cấp hệ thống thu thập dữ liệu tự động cập nhật hàng tuần hoặc hàng ngày; lưu trữ bằng Database thay vì file json.
- **Safety**: Thêm các quy tắc kiểm duyệt (filters) trên giao diện HTML và Backend để tránh người dùng lạm dụng chatbot.
- **Performance**: Tối ưu tốc độ phản hồi trên giao diện web bằng cách sử dụng WebSocket để stream tin nhắn thay vì đợi xử lý xong mới trả về toàn bộ (long polling).

---
