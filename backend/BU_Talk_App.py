#!/usr/bin/env python3
# =============================================================================
# K1 Flask Server — Minimal Test Version
# AI Innovation Center @ Hillsborough College | In partnership with URG Americas
# =============================================================================
# Run: python app.py
# Test: http://localhost:5000/health
# =============================================================================

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3.2"

@app.route("/")
def index():
    return "<h2>K1 Flask Server — AI Innovation Center</h2><p><a href='/health'>Health Check</a></p>"

@app.route("/health")
def health():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        return jsonify({"server": "ok", "ollama": "ok", "models": models})
    except:
        return jsonify({"server": "ok", "ollama": "unreachable", "models": []})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "No message"}), 400
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": MODEL,
            "messages": [{"role": "user", "content": message}],
            "stream": False
        }, timeout=60)
        reply = r.json()["message"]["content"]
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("=" * 50)
    print("K1 Flask Server")
    print("AI Innovation Center · Hillsborough College")
    print("http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)