# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Lê Dương Hiếu
- **Student ID**: 2A202600635
- **Date**: 18/01/2005

---

## I. Technical Contribution (15 Points)

*Describe your specific contribution to the codebase (e.g., implemented a specific tool, fixed the parser, etc.).*

- **Modules Implemented**: `src/tools/admission_tools.py`
- **Code Highlights**: 
  Xây dựng các công cụ hỗ trợ tư vấn tuyển sinh đại học bao gồm:
  - `get_subject_combination`: Tra cứu danh sách môn thi của tổ hợp xét tuyển.
  - `search_eligible_programs`: Lọc danh sách các ngành/trường có điểm chuẩn năm trước <= điểm thi của học sinh.
  - `filter_programs_by_schools`: Tìm kiếm ngành phù hợp theo danh sách các trường được học sinh chỉ định cụ thể.
- **Documentation**: Các công cụ này được thiết kế để kết nối trực tiếp với dữ liệu JSON (`diem_chuan.json`, `to_hop_mon.json`). ReAct Agent sẽ sử dụng mô tả (description) của từng tool trong `ADMISSION_TOOLS` list để quyết định chọn tool tương ứng khi người dùng hỏi về điểm chuẩn, tổ hợp hay khả năng đậu vào các trường.

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event you encountered during the lab using the logging system.*

- **Problem Description**: Agent truyền sai định dạng tham số khi gọi tool `search_eligible_programs` hoặc `filter_programs_by_schools`, ví dụ truyền chuỗi thay vì dict, hoặc thiếu tham số `phuong_thuc`.
- **Log Source**: Trace error trong file log ghi nhận `TypeError` hoặc kết quả trả về `Không tìm thấy...` không chính xác do parse JSON argument lỗi.
- **Diagnosis**: LLM đôi khi bị "ảo giác" (hallucinate) các tham số không có trong mô tả tool hoặc truyền tham số dưới dạng plain text thay vì JSON object.
- **Solution**: Cập nhật lại logic parse argument trong `ADMISSION_TOOLS` bằng việc thêm lambda func để xử lý linh hoạt: `lambda args: filter_programs_by_schools(**args) if isinstance(args, dict) else ...`. Điều này giúp bypass các lỗi khi agent truyền tham số không chuẩn dạng dictionary.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

*Reflect on the reasoning capability difference.*

1.  **Reasoning**: Khối `Thought` giúp Agent phân tích yêu cầu phức tạp (ví dụ: "Tôi thi khối A01 được 26 điểm, liệu có đậu CNTT trường Bưu chính không?"). Agent sẽ tự tư duy: "Đầu tiên mình cần biết điểm chuẩn năm ngoái của trường Bưu chính cho ngành CNTT khối A01 là bao nhiêu" thay vì đoán mò như Chatbot.
2.  **Reliability**: Agent có thể hoạt động *kém hơn* Chatbot trong những câu hỏi giao tiếp thông thường (chitchat). Việc phải chạy qua vòng lặp Thought-Action tốn nhiều thời gian và token hơn, đôi khi gây ra độ trễ lớn (latency) không cần thiết.
3.  **Observation**: Kết quả trả về từ file JSON đóng vai trò là "sự thật" (ground truth). Nếu kết quả trả về là rỗng (không tìm thấy trường), Agent sẽ tự động chuyển hướng câu trả lời hoặc đề xuất tổ hợp khác dựa vào Observation đó.

---

## IV. Future Improvements (5 Points)

*How would you scale this for a production-level AI agent system?*

- **Scalability**: Chuyển dữ liệu điểm chuẩn từ file tĩnh (JSON) sang cơ sở dữ liệu quan hệ (PostgreSQL) hoặc NoSQL (MongoDB) để hỗ trợ truy vấn nhanh cho hàng triệu thí sinh cùng lúc.
- **Safety**: Xây dựng một Input Guardrail để chống prompt injection và đảm bảo Agent chỉ trả lời các vấn đề xoay quanh kỳ thi tuyển sinh/đại học, từ chối trả lời các chủ đề nhạy cảm.
- **Performance**: Sử dụng Semantic Search (Vector Database) kết hợp với RAG để Agent không chỉ tra cứu điểm mà còn tư vấn được chi tiết về học phí, thông tin đào tạo của từng ngành.

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.
