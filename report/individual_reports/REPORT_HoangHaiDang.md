# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Hoàng Hải Đăng
- **Student ID**: [2A202600916]
- **Date**: 13/02/2005

---

## I. Technical Contribution

Trong phần lab này, em tập trung xây dựng một **ReAct Agent tư vấn tuyển sinh đại học** thay cho chatbot trả lời trực tiếp. Hệ thống nhận tổ hợp xét tuyển, điểm thi THPT và danh sách trường quan tâm, sau đó dùng các tool nội bộ để tra cứu dữ liệu điểm chuẩn và đưa ra tư vấn nguyện vọng bằng tiếng Việt.

### Modules Implemented

- `src/tools/admission_tools.py`: cài đặt các tool tra cứu tuyển sinh:
  - `search_eligible_programs(to_hop, diem_thi, phuong_thuc="THPT")`: tìm ngành/trường có điểm chuẩn phù hợp với điểm thi.
- `web/index.html`: xây dựng giao diện nhập tổ hợp, điểm thi, chọn trường và hiển thị kết quả tư vấn.

### Code Highlights

Ở `src/tools/admission_tools.py`, tool `search_eligible_programs` duyệt dữ liệu điểm chuẩn, kiểm tra phương thức xét tuyển, tổ hợp môn và điều kiện điểm:

```python
if r.get("phuong_thuc") != phuong_thuc:
    continue
if to_hop not in r.get("to_hop", []):
    continue
if diem_thi >= diem_chuan:
    results.append(...)
```

Kết quả được trả về ở dạng JSON có `status`, `total`, `to_hop`, `diem_thi`, `results`, giúp agent đọc Observation một cách rõ ràng và có căn cứ.

### Documentation: Interaction with ReAct Loop

Luồng hoạt động của hệ thống:

1. Người dùng nhập thông tin trên giao diện web: tổ hợp xét tuyển, điểm thi và trường quan tâm.
2. Flask API `/api/advise` kiểm tra dữ liệu đầu vào, sau đó tạo prompt tự nhiên cho agent.
3. `AdmissionReActAgent` gọi LLM với system prompt có mô tả tool và format bắt buộc.
4. LLM sinh `Thought` và `Action`, ví dụ:

```text
Action: filter_programs_by_schools({"to_hop": "A00", "diem_thi": 26.5, "danh_sach_truong": ["BKA", "NEU"]})
```

5. Agent parse action, chuyển tham số JSON vào tool tương ứng.
6. Tool trả về Observation từ dữ liệu điểm chuẩn.
7. Agent dùng Observation để tạo câu trả lời cuối cùng, phân tích khả năng đậu và gợi ý sắp xếp nguyện vọng.

---

## II. Debugging Case Study

### Problem Description

Một lỗi dễ gặp khi chạy ReAct Agent là LLM sinh action không đúng định dạng, ví dụ:

```text
Action: search_eligible_programs(A00, 26.5)
```

Trong khi parser của hệ thống yêu cầu tham số phải là JSON hợp lệ:

```text
Action: search_eligible_programs({"to_hop": "A00", "diem_thi": 26.5})
```

Khi action không đúng định dạng, agent không thể parse JSON hoặc không nhận ra action hợp lệ, dẫn đến không gọi được tool.

### Log Source

Các event liên quan:

- `PARSE_ERROR`: không tìm thấy action đúng format.
- `JSON_ERROR`: action có tên tool nhưng phần tham số không phải JSON hợp lệ.
- `TOOL_NOT_FOUND`: LLM gọi tool không tồn tại.
- `TOOL_ERROR`: thiếu tham số bắt buộc hoặc lỗi khi thực thi tool.

Ví dụ payload lỗi JSON mà hệ thống sẽ ghi:

```json
{
  "event": "JSON_ERROR",
  "data": {
    "tool": "search_eligible_programs",
    "raw_args": "A00, 26.5",
    "error": "Expecting value..."
  }
}
```

### Diagnosis

Nguyên nhân chính là LLM có xu hướng viết action theo kiểu lời gọi hàm thông thường thay vì JSON nghiêm ngặt. Điều này thường đến từ:

- Prompt chưa nhấn mạnh đủ mạnh rằng tham số phải là JSON hợp lệ.
- Ví dụ action trong system prompt chưa đủ cụ thể.
- Model nhỏ hoặc local model dễ bỏ qua format hơn so với model mạnh.

### Solution

Em xử lý bằng các cách sau:

- Bổ sung format bắt buộc trong system prompt: `Action: <tên_tool>(<tham số JSON hợp lệ>)`.
- Thêm ví dụ action đúng cho từng tool trong `get_system_prompt()`.
- Dùng `json.loads(raw_args)` để kiểm tra chặt chẽ thay vì tự tách chuỗi thủ công.
- Khi lỗi xảy ra, agent ghi log và đưa Observation phản hồi lại LLM để model tự sửa ở bước tiếp theo.
- Giới hạn `max_steps=6` và có `_force_final_answer()` để tránh agent lặp vô hạn.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning

So với chatbot trả lời trực tiếp, ReAct Agent đáng tin hơn trong bài toán cần dữ liệu cụ thể. Chatbot thường có thể trả lời nghe hợp lý nhưng dễ bịa điểm chuẩn hoặc tên ngành. Với ReAct, phần `Thought` buộc model phải xác định cần tra cứu gì trước, sau đó dùng `Action` để lấy dữ liệu từ tool. Nhờ vậy câu trả lời cuối dựa trên Observation thay vì trí nhớ mơ hồ của model.

Ví dụ, khi người dùng nhập tổ hợp A00 và 26.5 điểm, agent có thể chọn tool `search_eligible_programs`, nhận danh sách ngành đủ điều kiện, rồi mới phân tích ngành nào an toàn, ngành nào sát điểm.

### 2. Reliability

Agent có thể hoạt động kém hơn chatbot trong một số trường hợp:

- Câu hỏi quá đơn giản, không cần tool, nhưng agent vẫn phải đi qua nhiều bước nên chậm hơn.
- Nếu LLM sinh sai format action, agent mất thêm bước để sửa lỗi.
- Nếu dữ liệu trong `diem_chuan.json` thiếu ngành hoặc thiếu trường, agent không thể suy luận ngoài dữ liệu.
- Nếu số bước `max_steps` quá thấp, agent có thể chưa kịp gọi đủ tool trước khi phải trả lời.

Tuy vậy, với bài toán tư vấn tuyển sinh, độ tin cậy dữ liệu quan trọng hơn tốc độ trả lời, nên ReAct phù hợp hơn chatbot thường.

### 3. Observation

Observation là phần giúp agent "nhìn thấy" kết quả thực tế từ môi trường. Sau mỗi lần gọi tool, agent nhận JSON chứa danh sách ngành, điểm chuẩn, chênh lệch điểm và trạng thái tìm kiếm. Dữ liệu này ảnh hưởng trực tiếp đến bước tiếp theo:

- Nếu `status = "ok"`, agent phân tích danh sách ngành phù hợp.
- Nếu `status = "not_found"`, agent có thể khuyên người dùng mở rộng danh sách trường hoặc cân nhắc tổ hợp khác.
- Nếu có chênh lệch điểm lớn, agent gợi ý nhóm nguyện vọng an toàn.
- Nếu điểm sát chuẩn, agent đánh dấu rủi ro và khuyên đặt ở nhóm nguyện vọng thử sức.

---

## IV. Future Improvements (5 Points)

### Scalability

- Chuyển tool call sang dạng async để nhiều request web không bị chờ tuần tự.
- Tách dữ liệu tuyển sinh sang database thay vì đọc JSON file mỗi lần gọi tool.
- Chuẩn hóa schema cho ngành, trường, tổ hợp, phương thức xét tuyển và năm tuyển sinh.
- Bổ sung cache cho các truy vấn phổ biến như danh sách trường, tổ hợp môn và điểm chuẩn.

### Safety

- Thêm bước kiểm chứng để agent chỉ được trả lời bằng dữ liệu có trong Observation.
- Thêm guardrail cho điểm thi, tổ hợp, phương thức xét tuyển và mã trường.
- Thêm cảnh báo rằng điểm chuẩn năm trước chỉ dùng để tham khảo, không đảm bảo kết quả trúng tuyển.
- Có thể thêm Supervisor LLM để kiểm tra xem câu trả lời cuối có bịa số liệu ngoài tool hay không.

### Performance

- Giảm token bằng cách rút gọn Observation, chỉ trả về top ngành phù hợp thay vì toàn bộ danh sách.
- Lưu metrics theo phiên để so sánh latency, token và số bước giữa chatbot thường và ReAct Agent.
- Dùng vector search hoặc SQL query nếu dữ liệu tuyển sinh mở rộng nhiều năm và nhiều trường.
- Bổ sung test tự động cho các tool chính, đặc biệt là trường hợp không tìm thấy ngành, thiếu tham số và lọc theo trường.

---

## Summary

Qua lab này, em đã chuyển bài toán từ chatbot trả lời trực tiếp sang ReAct Agent có khả năng tra cứu dữ liệu, quan sát kết quả và suy luận theo từng bước. Phần quan trọng nhất là agent không chỉ "nói hay", mà có cơ chế gọi tool, ghi log, đo metrics và tạo câu trả lời dựa trên dữ liệu điểm chuẩn thật trong project.
