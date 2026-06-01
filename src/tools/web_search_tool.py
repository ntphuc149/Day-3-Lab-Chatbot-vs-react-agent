from duckduckgo_search import DDGS

def web_search(query: str, max_results: int = 3) -> str:
    """
    Tìm kiếm thông tin trên web sử dụng DuckDuckGo.
    Hữu ích để tìm kiếm điểm chuẩn, thông tin tuyển sinh mới nhất mà không có sẵn trong CSDL.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            
        if not results:
            return "Không tìm thấy kết quả nào."
            
        output = []
        for i, r in enumerate(results):
            output.append(f"{i+1}. {r['title']}\nURL: {r['href']}\nTrích dẫn: {r['body']}\n")
            
        return "\n".join(output)
    except Exception as e:
        return f"Lỗi khi tìm kiếm web: {e}"

# Khai báo tool cho ReAct Agent
WEB_SEARCH_TOOLS = [
    {
        "name": "web_search",
        "description": "Tìm kiếm thông tin trên mạng Internet (Google/DuckDuckGo). "
                       "Dùng công cụ này khi bạn cần tìm điểm chuẩn hoặc thông tin tuyển sinh mới nhất "
                       "mã không có trong cơ sở dữ liệu nội bộ. Args: query (câu hỏi cần tìm kiếm).",
        "function": web_search
    }
]

if __name__ == "__main__":
    print(web_search("Điểm chuẩn đại học Ngoại thương 2024"))
