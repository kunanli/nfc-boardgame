"""NFC 桌遊服務端（裁判）—— 純標準庫 HTTP 服務。

模擬真實硬體：讀卡機把晶片 UID 以 HTTP POST 送來，服務端判定並回傳結果。

啟動：
    python3 server.py            # 監聽 http://127.0.0.1:8080

API：
    POST /tap    body: {"uid": "04A1B2C3"}   # 刷一張卡
    POST /start  body: {}                     # 主持人結束組隊、開始冒險
    POST /reset  body: {}                     # 重開一局
    GET  /state                               # 查詢目前戰況
    GET  /cards                               # 列出已登錄的卡片

範例（另開終端）：
    curl -s -XPOST localhost:8080/tap   -d '{"uid":"04A1B2C3"}'
    curl -s -XPOST localhost:8080/start -d '{}'
    curl -s -XPOST localhost:8080/tap   -d '{"uid":"04D0E0F1"}'
    curl -s localhost:8080/state
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from game.cards import CardDB
from game.engine import Game

DB = CardDB.load()
GAME = Game(DB)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path == "/state":
            self._send(200, GAME.state())
        elif self.path == "/cards":
            self._send(200, {"cards": DB._cards})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        global GAME
        data = self._read_json()
        if self.path == "/tap":
            uid = data.get("uid", "")
            r = GAME.tap(uid)
            self._send(200 if r.ok else 400, {
                "ok": r.ok, "event": r.event, "message": r.message,
                "phase": r.phase, "detail": r.detail,
            })
        elif self.path == "/start":
            r = GAME.start_adventure()
            self._send(200 if r.ok else 400, {
                "ok": r.ok, "event": r.event, "message": r.message, "phase": r.phase,
            })
        elif self.path == "/reset":
            GAME = Game(DB)
            self._send(200, {"ok": True, "message": "新的一局已開始（組隊階段）。"})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):  # 靜音預設存取紀錄
        pass


def main(host: str = "127.0.0.1", port: int = 8080) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"NFC 桌遊服務端啟動：http://{host}:{port}")
    print("刷卡：POST /tap {\"uid\": ...}  開始：POST /start  戰況：GET /state")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服務端關閉。")
        srv.shutdown()


if __name__ == "__main__":
    main()
