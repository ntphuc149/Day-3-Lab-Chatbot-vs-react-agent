# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: [Nguyễn Huyền San]
- **Student ID**: [2A202600835]
- **Date**: [01/06/2026]

---

## I. Technical Contribution (15 Points)

*-Tích hợp và tối ưu hóa React agent 
-Xây dựng backend api
-Xử lý Dữ liệu và Xây dựng API Helper
-Thiết kế Endpoint Tư vấn và Xử lý Prompt Động*

- **Modules Implementated**: [`web/app.py]
- **Code Highlights**: [Cơ chế Lazy Loading cho Local LLM để tối ưu tài nguyên server
def get_agent() -> AdmissionReActAgent:
    global _agent
    if _agent is None:
        model_path = os.getenv("LOCAL_MODEL_PATH", "./models/Phi-3-mini-4k-instruct-q4.gguf")
        llm = LocalProvider(model_path=model_path)
        _agent = AdmissionReActAgent(llm=llm, max_steps=6)
    return _agent
Logic thiết kế Prompt động (Dynamic Prompt Engineering) xử lý theo ngữ cảnh người dùng
if danh_sach_truong:
    # Ràng buộc không gian tìm kiếm (Search space)
    user_query = f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm... Hãy lọc tại các trường: {ten_truong_list}."
else:
    # Mở rộng không gian tìm kiếm (Open exploration)
    user_query = f"Tôi thi tổ hợp {to_hop} được {diem_thi} điểm... Hãy tìm tất cả ngành/trường phù hợp..."
]
- **Documentation**: [đóng vai trò là Controller, tiếp nhận HTTP Request từ frontend, làm sạch và xác thực dữ liệu (Input Validation). Sau đó, module sẽ định tuyến câu hỏi và khởi tạo môi trường thực thi cho AdmissionReActAgent. Trong quá trình Agent chạy vòng lặp suy luận (Thought-Action-Observation), API sẽ chờ cho đến khi Agent kích hoạt cờ Final Answer hoặc chạm ngưỡng max_steps=6 (để tránh infinite loop), sau đó đóng gói phản hồi thành JSON và trả về cho client. Các API Helper (/api/schools, /api/to_hop) giúp Frontend ràng buộc format đầu vào, giảm thiểu lỗi hallucination (ảo giác) của LLM khi tìm kiếm chuỗi sai cú pháp.]

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event you encountered during the lab using the logging system.*

- **Problem Description**: [Agent rơi vào vòng lặp vô hạn (Infinite Loop) hoặc ném lỗi Parser Exception do LLM sinh ra text không đúng định dạng Action và Action Input. Cụ thể, thay vì gọi công cụ, mô hình cố gắng trả lời luôn (sinh ra Final Answer ngay ở bước đầu) nhưng thiếu căn cứ điểm chuẩn.]
- **Log Source**: [
[2026-06-01 14:15:22] DEBUG: Agent Thought: Thí sinh được 24 điểm khối A00, muốn vào ĐH Bách Khoa. Mình nghĩ ngành này điểm chuẩn cao.
[2026-06-01 14:15:24] ERROR: OutputParserException: Could not parse LLM output: `Tôi khuyên bạn không nên đăng ký vào Bách Khoa vì điểm thi của bạn khá thấp so với mặt bằng chung.`
]
- **Diagnosis**: [Vấn đề xuất phát từ việc sử dụng mô hình nội bộ đã được lượng tử hóa (Quantized Model: Phi-3-mini-instruct-q4). Quá trình lượng tử hóa (Quantization) làm giảm độ chính xác trong việc tuân thủ các chỉ thị định dạng khắt khe (strict format following). Mô hình bị "quên" việc phải trích xuất Action và tự ý suy diễn (hallucinate) kết quả dựa trên trọng số kiến thức nội tại thay vì dùng Tool để tra cứu.]
- **Solution**: [Cập nhật lại System Prompt, áp dụng kỹ thuật Few-shot Prompting (cung cấp sẵn 1-2 mẫu hội thoại mẫu có chứa Thought/Action/Observation hợp lệ).]

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

*Reflect on the reasoning capability difference.*

1.  **Reasoning**: Việc bắt buộc sinh ra khối Thought (Chain of Thought) giúp Agent có tư duy rẽ nhánh rõ ràng. Thay vì một Chatbot thông thường sinh văn bản tuyến tính (dẫn đến ảo giác số liệu điểm chuẩn), ReAct Agent biết chia nhỏ bài toán: "Với mức điểm X -> Cần tìm điểm chuẩn trường Y -> So sánh 2 số liệu -> Đưa ra chiến lược an toàn hay rủi ro". Suy luận có tính "chậm lại để tính toán" (System 2 thinking)
2.  **Reliability**:Agent thực tế lại hoạt động tệ hơn Chatbot khi đối mặt với các câu lệnh mơ hồ hoặc dữ liệu bị "Miss-match". Ví dụ, nếu user nhập "Bách Khoa" nhưng trong Database là "Đại học Bách Khoa Hà Nội", Tool tìm kiếm có thể trả về None. Khi đó, ReAct Agent bị kẹt và bối rối, trong khi Chatbot truyền thống vẫn sẽ dùng kiến thức nền để khéo léo đưa ra lời khuyên chung chung hợp lý. Mức độ dung lỗi (Fault tolerance) của Agent thấp hơn.
3.  **Observation**: Môi trường phản hồi đóng vai trò như một mỏ neo thực tế (Grounding fact). Khi Agent nhận được Observation mang số liệu điểm chuẩn chính xác từ JSON, luồng suy luận của nó lập tức thay đổi. Nó từ bỏ phỏng đoán ban đầu và cập nhật lại chiến thuật, tạo ra những lời khuyên bám sát thực tế tuyển sinh mà mô hình ngôn ngữ đơn thuần không thể làm được.

---

## IV. Future Improvements (5 Points)

*How would you scale this for a production-level AI agent system?*

- **Scalability**: [Triển khai kiến trúc Message Broker / Async Queue (như Celery + Redis, Kafka) cho Endpoint API /api/advise. Vì Local LLM xử lý (inference) rất tốn thời gian và block thread, việc đưa vào hàng đợi giúp server có thể chịu tải đồng thời nhiều thí sinh mà không bị crash. Cập nhật UI sang cơ chế WebSockets hoặc Long Polling để stream từng bước suy luận (Thought) về Frontend theo thời gian thực.]
- **Safety**: [Xây dựng một Supervisor Agent (hoặc một bộ Rule-based Guardrails mạnh). Supervisor sẽ đánh giá output cuối cùng của ReAct Agent trước khi trả về cho user, đảm bảo không có nội dung phân biệt đối xử, xúi giục bỏ học, hoặc đưa ra các bảo đảm sai lệch 100% đỗ (tránh rủi ro tư vấn sai lệch ảnh hưởng tương lai thí sinh).]
- **Performance**: [Nâng cấp Tool tra cứu bằng cách tích hợp Vector Database (Qdrant, Milvus, hoặc Chroma) kết hợp RAG (Retrieval-Augmented Generation). Thay vì tìm kiếm chuỗi exact-match từ file JSON, Agent có thể Semantic Search (tìm kiếm theo ngữ nghĩa). Ví dụ: "Tìm các ngành liên quan đến chế tạo robot", Vector DB sẽ linh hoạt trả về cơ điện tử, tự động hóa, giúp Agent có nguồn tài liệu phong phú và xử lý các ca tư vấn phức tạp hơn.]

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.
