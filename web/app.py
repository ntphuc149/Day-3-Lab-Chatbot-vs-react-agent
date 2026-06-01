import sys
import os
import json
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from src.agent.admission_agent import AdmissionReActAgent
from src.core.openai_provider import OpenAIProvider

load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

# ------------------------------------------------------------------
# Session store: { session_id: { context: {}, history: [] } }
# ------------------------------------------------------------------
_sessions: dict = {}

# ------------------------------------------------------------------
# Agent (lazy init)
# ------------------------------------------------------------------
_agent: AdmissionReActAgent = None

def get_agent() -> AdmissionReActAgent:
    global _agent
    if _agent is None:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("DEFAULT_MODEL", "gpt-4o")
        llm = OpenAIProvider(model_name=model, api_key=api_key)
        _agent = AdmissionReActAgent(llm=llm, max_steps=6)
    return _agent


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _load_schools():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "diem_chuan.json")
    with open(data_path, encoding="utf-8") as f:
        records = json.load(f)
    seen = {}
    for r in records:
        ma = r["ma_truong"]
        if ma not in seen and r.get("phuong_thuc") == "THPT":
            seen[ma] = r["ten_truong"]
    return [{"ma": k, "ten": v} for k, v in sorted(seen.items(), key=lambda x: x[1])]


def _load_to_hop():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "to_hop_mon.json")
    with open(data_path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/schools", methods=["GET"])
def get_schools():
    return jsonify(_load_schools())


@app.route("/api/to_hop", methods=["GET"])
def get_to_hop():
    return jsonify(_load_to_hop())


@app.route("/api/session/new", methods=["POST"])
def new_session():
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"context": {}, "history": []}
    return jsonify({"session_id": session_id})


@app.route("/api/session/<session_id>/reset", methods=["POST"])
def reset_session(session_id: str):
    _sessions[session_id] = {"context": {}, "history": []}
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json()
    if not body:
        return jsonify({"error": "Request body trống"}), 400

    session_id = body.get("session_id", "").strip()
    message = body.get("message", "").strip()

    if not message:
        return jsonify({"error": "Tin nhắn trống"}), 400

    # Tạo session mới nếu chưa có
    if not session_id or session_id not in _sessions:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = {"context": {}, "history": []}

    session = _sessions[session_id]

    try:
        agent = get_agent()
        reply = agent.chat(message, session)
        return jsonify({
            "session_id": session_id,
            "reply": reply,
            "context": session["context"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
