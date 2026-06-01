import json
import os
from typing import List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DIEM_CHUAN_PATH = os.path.join(DATA_DIR, "diem_chuan.json")
TO_HOP_PATH = os.path.join(DATA_DIR, "to_hop_mon.json")


def _load_diem_chuan() -> List[Dict]:
    with open(DIEM_CHUAN_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_to_hop() -> Dict:
    with open(TO_HOP_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_subject_combination(ma_to_hop: str) -> str:
    """
    Tra cứu các môn thi trong một tổ hợp xét tuyển.
    Args:
        ma_to_hop: Mã tổ hợp (vd: A00, D01, B00)
    Returns:
        Chuỗi mô tả các môn thi của tổ hợp đó.
    """
    to_hop_data = _load_to_hop()
    ma_to_hop = ma_to_hop.strip().upper()
    if ma_to_hop in to_hop_data:
        mon_thi = ", ".join(to_hop_data[ma_to_hop])
        return f"Tổ hợp {ma_to_hop} gồm các môn: {mon_thi}."
    return f"Không tìm thấy tổ hợp '{ma_to_hop}'. Các tổ hợp hợp lệ: {', '.join(to_hop_data.keys())}."


def search_eligible_programs(to_hop: str, diem_thi: float, phuong_thuc: str = "THPT") -> str:
    """
    Tìm tất cả ngành/trường có điểm chuẩn năm trước thấp hơn hoặc bằng điểm thi của người dùng.
    Args:
        to_hop: Mã tổ hợp xét tuyển (vd: A00, D01)
        diem_thi: Điểm thi THPT của người dùng (thang điểm 30)
        phuong_thuc: Phương thức xét tuyển, mặc định là THPT
    Returns:
        Danh sách các ngành phù hợp dạng chuỗi JSON.
    """
    records = _load_diem_chuan()
    to_hop = to_hop.strip().upper()
    results = []

    for r in records:
        if r.get("phuong_thuc") != phuong_thuc:
            continue
        if to_hop not in r.get("to_hop", []):
            continue
        diem_chuan = r.get("diem_chuan_2024", 999)
        if diem_thi >= diem_chuan:
            results.append({
                "truong": r["ten_truong"],
                "ma_truong": r["ma_truong"],
                "nganh": r["ten_nganh"],
                "diem_chuan_2024": diem_chuan,
                "chenh_lech": round(diem_thi - diem_chuan, 2)
            })

    if not results:
        return json.dumps({
            "status": "not_found",
            "message": f"Không tìm thấy ngành nào phù hợp với tổ hợp {to_hop} và điểm {diem_thi}.",
            "results": []
        }, ensure_ascii=False)

    results.sort(key=lambda x: x["chenh_lech"], reverse=True)
    return json.dumps({
        "status": "ok",
        "total": len(results),
        "to_hop": to_hop,
        "diem_thi": diem_thi,
        "results": results
    }, ensure_ascii=False)
def filter_programs_by_schools(to_hop: str, diem_thi: float, danh_sach_truong: List[str], phuong_thuc: str = "THPT") -> str:
    """
    Lọc các ngành phù hợp theo danh sách trường mà người dùng quan tâm.
    Args:
        to_hop: Mã tổ hợp xét tuyển
        diem_thi: Điểm thi THPT của người dùng
        danh_sach_truong: Danh sách mã trường hoặc tên trường cần lọc
        phuong_thuc: Phương thức xét tuyển, mặc định là THPT
    Returns:
        Danh sách ngành đã lọc theo trường, dạng chuỗi JSON.
    """
    records = _load_diem_chuan()
    to_hop = to_hop.strip().upper()
    truong_filter = [t.strip().upper() for t in danh_sach_truong]
    results = []

    for r in records:
        if r.get("phuong_thuc") != phuong_thuc:
            continue
        if to_hop not in r.get("to_hop", []):
            continue
        # Khớp theo mã trường hoặc tên trường (không phân biệt hoa/thường)
        ma = r["ma_truong"].upper()
        ten = r["ten_truong"].upper()
        match = any(f in ma or f in ten for f in truong_filter)
        if not match:
            continue
        diem_chuan = r.get("diem_chuan_2024", 999)
        results.append({
            "truong": r["ten_truong"],
            "ma_truong": r["ma_truong"],
            "nganh": r["ten_nganh"],
            "diem_chuan_2024": diem_chuan,
            "kha_nang": "Đậu" if diem_thi >= diem_chuan else "Rủi ro cao",
            "chenh_lech": round(diem_thi - diem_chuan, 2)
        })

    if not results:
        return json.dumps({
            "status": "not_found",
            "message": f"Không tìm thấy ngành nào trong danh sách trường đã chọn với tổ hợp {to_hop}.",
            "results": []
        }, ensure_ascii=False)

    results.sort(key=lambda x: x["chenh_lech"], reverse=True)
    return json.dumps({
        "status": "ok",
        "total": len(results),
        "to_hop": to_hop,
        "diem_thi": diem_thi,
        "results": results
    }, ensure_ascii=False)


def suggest_top_programs(to_hop: str, diem_thi: float, top_n: int = 5,
                         nganh_quan_tam: List[str] = None, phuong_thuc: str = "THPT") -> str:
    """
    Gợi ý top N ngành/trường phù hợp nhất khi người dùng chưa có trường cụ thể.
    Ưu tiên: (1) an toàn vừa phải (chênh lệch 0.5–3 điểm), (2) khớp ngành quan tâm nếu có.
    Args:
        to_hop: Mã tổ hợp xét tuyển
        diem_thi: Điểm thi THPT của người dùng
        top_n: Số lượng gợi ý trả về (mặc định 5)
        nganh_quan_tam: Danh sách từ khóa ngành quan tâm để ưu tiên, [] nếu không có
        phuong_thuc: Phương thức xét tuyển, mặc định là THPT
    Returns:
        Top N ngành gợi ý dạng chuỗi JSON.
    """
    records = _load_diem_chuan()
    to_hop = to_hop.strip().upper()
    nganh_keywords = [n.strip().lower() for n in (nganh_quan_tam or [])]
    candidates = []

    for r in records:
        if r.get("phuong_thuc") != phuong_thuc:
            continue
        if to_hop not in r.get("to_hop", []):
            continue
        diem_chuan = r.get("diem_chuan_2024", 999)
        chenh_lech = round(diem_thi - diem_chuan, 2)
        if chenh_lech < 0:
            continue

        # Tính điểm ưu tiên: thích khoảng an toàn vừa (0.5–3đ), không quá dễ
        safety_score = chenh_lech if chenh_lech <= 3 else max(0, 6 - chenh_lech)

        # Cộng thêm điểm nếu khớp ngành quan tâm
        nganh_lower = r["ten_nganh"].lower()
        nganh_bonus = 5 if any(k in nganh_lower for k in nganh_keywords) else 0

        candidates.append({
            "truong": r["ten_truong"],
            "ma_truong": r["ma_truong"],
            "nganh": r["ten_nganh"],
            "diem_chuan_2024": diem_chuan,
            "chenh_lech": chenh_lech,
            "kha_nang": "An toàn" if chenh_lech >= 1 else "Vừa đủ",
            "_score": safety_score + nganh_bonus,
        })

    if not candidates:
        return json.dumps({
            "status": "not_found",
            "message": f"Không tìm thấy ngành nào phù hợp với tổ hợp {to_hop} và điểm {diem_thi}.",
            "results": []
        }, ensure_ascii=False)

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    top = candidates[:top_n]
    for r in top:
        del r["_score"]

    return json.dumps({
        "status": "ok",
        "total_eligible": len(candidates),
        "top_n": top_n,
        "to_hop": to_hop,
        "diem_thi": diem_thi,
        "note": "Đây là gợi ý khi chưa có trường cụ thể. Ưu tiên ngành an toàn và khớp sở thích.",
        "results": top
    }, ensure_ascii=False)


# Tool registry dùng cho ReAct agent
ADMISSION_TOOLS = [
    {
        "name": "get_subject_combination",
        "description": "Tra cứu các môn thi trong một tổ hợp xét tuyển. Dùng khi cần biết tổ hợp gồm những môn gì. Input: ma_to_hop (string, vd: 'A00').",
        "func": get_subject_combination,
    },
    {
        "name": "search_eligible_programs",
        "description": "Tìm tất cả ngành/trường có điểm chuẩn năm trước thấp hơn hoặc bằng điểm thi của người dùng. Input: to_hop (string), diem_thi (float), phuong_thuc (string, mặc định 'THPT').",
        "func": lambda args: search_eligible_programs(**args) if isinstance(args, dict) else search_eligible_programs(*args.split(",")),
    },
    {
        "name": "filter_programs_by_schools",
        "description": "Lọc các ngành phù hợp theo danh sách trường mà người dùng quan tâm. Input: to_hop (string), diem_thi (float), danh_sach_truong (list of string), phuong_thuc (string, mặc định 'THPT').",
        "func": lambda args: filter_programs_by_schools(**args) if isinstance(args, dict) else "Cần truyền dict arguments.",
    },
    {
        "name": "suggest_top_programs",
        "description": "Gợi ý top 5 ngành/trường phù hợp nhất khi người dùng CHƯA có trường cụ thể. Ưu tiên ngành an toàn và khớp sở thích. Input: to_hop (string), diem_thi (float), nganh_quan_tam (list of string, [] nếu không có), top_n (int, mặc định 5).",
        "func": lambda args: suggest_top_programs(**args) if isinstance(args, dict) else "Cần truyền dict arguments.",
    },
]
