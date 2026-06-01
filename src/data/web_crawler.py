import os
import json
import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from dotenv import load_dotenv

# Load môi trường (.env) để lấy API Key
load_dotenv()

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DIEM_CHUAN_PATH = os.path.join(DATA_DIR, "diem_chuan.json")

def fetch_text_from_url(url: str) -> str:
    """Tải trang web và lấy văn bản thô (loại bỏ HTML, JS, CSS)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Xóa script, style
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.extract()
            
        text = soup.get_text(separator="\n")
        # Dọn dẹp khoảng trắng
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text[:15000] # Giới hạn độ dài tránh vượt quá token của LLM
    except Exception as e:
        print(f"Lỗi khi cào dữ liệu từ {url}: {e}")
        return ""

def search_and_extract_scores(query: str, llm_provider) -> list:
    """
    1. Tìm kiếm web với DuckDuckGo
    2. Cào bài báo đầu tiên
    3. Dùng LLM bóc tách dữ liệu ra dạng JSON
    """
    print(f"🔍 Đang tìm kiếm trên web: '{query}'...")
    
    # 1. Tìm kiếm
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
    except Exception as e:
        print(f"Lỗi tìm kiếm: {e}")
        return []

    if not results:
        print("❌ Không tìm thấy kết quả web nào.")
        return []

    url = results[0]["href"]
    print(f"🌐 Đã tìm thấy link: {url}")
    print(f"📄 Đang cào dữ liệu bài báo...")
    
    # 2. Cào văn bản
    text = fetch_text_from_url(url)
    if not text:
        return []

    print(f"🤖 Đang gửi cho AI đọc và bóc tách dữ liệu...")
    
    # 3. Yêu cầu LLM bóc tách
    system_prompt = """
    Bạn là một chuyên gia xử lý dữ liệu tuyển sinh.
    Hãy đọc văn bản người dùng cung cấp và bóc tách tất cả thông tin điểm chuẩn đại học.
    Trả về MỘT MẢNG (Array) chứa các object JSON tuân thủ CHÍNH XÁC cấu trúc sau, KHÔNG thêm chữ nào khác ngoài JSON:
    [
      {
        "ma_truong": "Mã trường (ví dụ: BKA, NEU)",
        "ten_truong": "Tên đầy đủ của trường",
        "ten_nganh": "Tên ngành học",
        "phuong_thuc": "THPT hoặc HOC_BA hoặc DGNL_HN...",
        "to_hop": ["A00", "A01"],
        "diem_chuan_2024": 28.5 (dạng số float),
        "thang_diem": 30 (hoặc 100, 150... tùy phương thức)
      }
    ]
    Nếu không tìm thấy bất kỳ điểm số nào, hãy trả về mảng rỗng [].
    """
    
    try:
        response = llm_provider.generate(prompt=text, system_prompt=system_prompt)
        content = response.get("content", "").strip()
        
        # Tìm phần JSON trong câu trả lời của AI
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            data = json.loads(json_str)
            return data
        else:
            print("❌ AI không trả về đúng định dạng JSON.")
            print("Nội dung AI trả về:\n", content)
            return []
            
    except Exception as e:
        print(f"Lỗi khi nhờ AI bóc tách: {e}")
        return []

def append_to_diem_chuan(new_data: list):
    """Lưu dữ liệu bóc tách được vào file JSON chính."""
    if not new_data:
        print("⚠️ Không có dữ liệu mới để thêm.")
        return
        
    try:
        if os.path.exists(DIEM_CHUAN_PATH):
            with open(DIEM_CHUAN_PATH, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        else:
            current_data = []
            
        # Nối dữ liệu
        current_data.extend(new_data)
        
        with open(DIEM_CHUAN_PATH, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        print(f"✅ Đã thêm {len(new_data)} bản ghi vào diem_chuan.json!")
    except Exception as e:
        print(f"Lỗi khi lưu file: {e}")

if __name__ == "__main__":
    # Test chạy thử (Yêu cầu phải có OPENAI_API_KEY trong file .env)
    from src.core.openai_provider import OpenAIProvider
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("⚠️ LỖI: Cần có OPENAI_API_KEY trong file .env để chạy crawler!")
    else:
        llm = OpenAIProvider(api_key=api_key)
        
        truong_can_tim = input("Nhập thông tin điểm chuẩn cần tìm (vd: 'Điểm chuẩn ĐH Thương Mại 2024'): ")
        ket_qua = search_and_extract_scores(truong_can_tim, llm)
        
        if ket_qua:
            print("\n📊 Kết quả AI bóc tách được:")
            print(json.dumps(ket_qua, ensure_ascii=False, indent=2))
            
            luu = input("Bạn có muốn lưu vào file diem_chuan.json không? (y/n): ")
            if luu.lower() == 'y':
                append_to_diem_chuan(ket_qua)
