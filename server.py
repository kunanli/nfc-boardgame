"""NFC 桌遊服務端（裁判）—— 純標準庫 HTTP 服務，手機瀏覽器友善。

模擬真實硬體：NFC 貼片裡寫一個網址，iPhone 碰一下就打開 -> 服務端判定 -> 回傳結果頁。
完全不用寫 App、不用寫程式。

啟動：
    python3 server.py                 # 監聽 0.0.0.0:8080，區網其他裝置可連

主要網址（手機用瀏覽器就能開）：
    GET  /                 遊戲儀表板（大螢幕投影用，自動刷新）
    GET  /setup            設定頁：列出每張卡「要寫進 NFC 貼片的網址」
    GET  /tap?uid=XXXX     刷一張卡（NFC 貼片就是寫這個網址）
    GET  /start            開始冒險
    GET  /reset            重開一局

程式用（curl / App）：
    POST /tap {"uid": ...} / POST /start / POST /reset / GET /state / GET /cards
"""
from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from game.cards import CardDB
from game.engine import Game, Phase, TapResult

DB = CardDB.load()
GAME = Game(DB)

PAGE = """<!doctype html><html lang="zh-Hant"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NFC 桌遊</title>{refresh}
<style>
  body{{font-family:-apple-system,"PingFang TC",sans-serif;background:#12141c;color:#e8e8ee;
       margin:0;padding:20px;max-width:640px;margin:0 auto}}
  .msg{{font-size:20px;line-height:1.5;background:#1e2130;border-radius:14px;padding:18px;margin:12px 0}}
  .ok{{border-left:6px solid #46c68a}} .no{{border-left:6px solid #e5585b}}
  .turn{{font-size:15px;color:#9aa4c0;margin:4px 0 16px}}
  table{{width:100%;border-collapse:collapse;margin-top:8px}}
  th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #2a2e40}}
  th{{color:#9aa4c0;font-weight:500;font-size:13px}}
  .gold{{color:#f4c542;font-weight:600}} .crown{{color:#f4c542}}
  a.btn{{display:inline-block;background:#3355dd;color:#fff;text-decoration:none;
         padding:10px 18px;border-radius:10px;margin:4px 6px 4px 0;font-size:15px}}
  h1{{font-size:22px}} h2{{font-size:16px;color:#9aa4c0;margin-top:24px}}
  code{{background:#0c0e15;padding:2px 6px;border-radius:5px;word-break:break-all}}
  .card{{background:#1e2130;border-radius:10px;padding:12px;margin:8px 0}}
</style></head><body>{body}</body></html>"""


def render(body: str, refresh: bool = False) -> bytes:
    r = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return PAGE.format(body=body, refresh=r).encode("utf-8")


def leaderboard_html(st: dict) -> str:
    if not st["leaderboard"]:
        return "<p class='turn'>還沒有玩家加入。</p>"
    rows = ""
    for i, row in enumerate(st["leaderboard"], 1):
        crown = " 👑" if row["name"] == st["winner"] else ""
        rows += (f"<tr><td>{i}</td><td>{row['name']}{crown}</td>"
                 f"<td class='gold'>{row['gold']}</td><td>{row['kos']}</td></tr>")
    return ("<table><tr><th>#</th><th>玩家</th><th>金幣</th><th>撤退</th></tr>"
            + rows + "</table>")


def dashboard_html() -> str:
    st = GAME.state()
    phase_zh = {"lobby": "組隊中", "adventure": "冒險中", "over": "遊戲結束"}[st["phase"]]
    b = f"<h1>⚔️ 組隊冒險・搶尾刀奪寶</h1><div class='msg'>階段：<b>{phase_zh}</b>"
    if st["winner"]:
        b += f"<br>🏆 冠軍：<b class='crown'>{st['winner']}</b>"
    elif st["turn"]:
        b += f"<br>輪到：<b>{st['turn']}</b>"
    if st["current_monster"]:
        m = st["current_monster"]
        boss = "（最終王）" if m["boss"] else ""
        b += f"<br>桌上怪物：<b>{m['name']}</b>{boss} HP {m['hp']}／攻擊 {m['atk']}／賞金 {m['reward']}"
    b += "</div>"
    b += "<h2>排行榜</h2>" + leaderboard_html(st)
    if st["slain"]:
        b += "<h2>擊殺紀錄</h2><table><tr><th>怪物</th><th>尾刀者</th></tr>"
        for s in st["slain"]:
            b += f"<tr><td>{s['monster']}</td><td>{s['killer']}</td></tr>"
        b += "</table>"
    b += ("<h2>操作</h2><a class='btn' href='/start'>開始冒險</a>"
          "<a class='btn' href='/reset'>重開一局</a>"
          "<a class='btn' href='/setup'>卡片設定</a>")
    return b


def result_html(r) -> str:
    st = GAME.state()
    cls = "ok" if r.ok else "no"
    mark = "✓" if r.ok else "✗"
    b = f"<h1>⚔️ 判定結果</h1><div class='msg {cls}'>{mark} {r.message}</div>"
    if st["turn"] and st["phase"] == "adventure":
        b += f"<div class='turn'>接下來輪到 <b>{st['turn']}</b>，拿手機碰下一張卡。</div>"
    if st["winner"]:
        b += f"<div class='turn'>🏆 冠軍：<b class='crown'>{st['winner']}</b></div>"
    b += "<h2>排行榜</h2>" + leaderboard_html(st)
    b += "<div style='margin-top:16px'><a class='btn' href='/'>回儀表板</a></div>"
    return b


def setup_html(base: str) -> str:
    b = ("<h1>🏷️ 卡片設定</h1><div class='msg'>用 iPhone 的 <b>NFC Tools</b> App"
         "（或捷徑），把下面每一條網址寫進對應那張卡的 NFC 貼片。寫好後，手機碰卡就會自動開這個網址。</div>")
    kinds = {"hero": "英雄卡", "monster": "怪物卡", "item": "道具卡"}
    for uid, c in DB._cards.items():
        if not isinstance(c, dict) or "type" not in c:
            continue
        kind = kinds.get(c["type"], c["type"])
        url = f"{base}/tap?uid={uid}"
        b += (f"<div class='card'><b>{c.get('name', uid)}</b>（{kind}）<br>"
              f"<code>{url}</code></div>")
    b += "<div style='margin-top:16px'><a class='btn' href='/'>回儀表板</a></div>"
    return b


class Handler(BaseHTTPRequestHandler):
    def _html(self, code: int, body: str, refresh: bool = False) -> None:
        data = render(body, refresh)
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _base(self) -> str:
        host = self.headers.get("Host", "localhost:8080")
        return f"http://{host}"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        global GAME
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)

        if path == "/":
            self._html(200, dashboard_html(), refresh=True)
        elif path == "/setup":
            self._html(200, setup_html(self._base()))
        elif path == "/tap":
            uid = (qs.get("uid") or [""])[0]
            r = GAME.tap(uid)
            self._html(200, result_html(r))
        elif path == "/start":
            r = GAME.start_adventure()
            self._html(200, result_html(r))
        elif path == "/reset":
            GAME = Game(DB)
            self._html(200, result_html(TapResult(
                ok=True, event="reset", message="新的一局已開始（組隊階段）。",
                phase=GAME.phase.value)))
        elif path == "/state":
            self._json(200, GAME.state())
        elif path == "/cards":
            self._json(200, {"cards": DB._cards})
        else:
            self._html(404, "<h1>404</h1><a class='btn' href='/'>回儀表板</a>")

    def do_POST(self):
        global GAME
        data = self._read_json()
        if self.path == "/tap":
            r = GAME.tap(data.get("uid", ""))
            self._json(200 if r.ok else 400,
                       {"ok": r.ok, "event": r.event, "message": r.message,
                        "phase": r.phase, "detail": r.detail})
        elif self.path == "/start":
            r = GAME.start_adventure()
            self._json(200 if r.ok else 400,
                       {"ok": r.ok, "event": r.event, "message": r.message, "phase": r.phase})
        elif self.path == "/reset":
            GAME = Game(DB)
            self._json(200, {"ok": True, "message": "新的一局已開始（組隊階段）。"})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


def lan_ip() -> str:
    """猜測本機在區網的 IP，方便把網址寫進 NFC 貼片。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main(host: str = "0.0.0.0", port: int = 8080) -> None:
    ip = lan_ip()
    srv = ThreadingHTTPServer((host, port), Handler)
    print("NFC 桌遊服務端已啟動")
    print(f"  這台電腦看：   http://localhost:{port}")
    print(f"  手機同 WiFi 看：http://{ip}:{port}")
    print(f"  卡片設定頁：   http://{ip}:{port}/setup")
    print("按 Ctrl+C 結束。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服務端關閉。")
        srv.shutdown()


if __name__ == "__main__":
    main()
