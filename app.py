from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import os
import base64

NTFY_URL = os.environ.get("NTFY_RELAY_URL", "https://ntfy.0qk.de/grafana")
NTFY_USER = os.environ.get("NTFY_RELAY_USER", "grafana-bot")
NTFY_PASS = os.environ.get("NTFY_RELAY_PASS", "grafana-bot-2026")

def format_alert(payload):
    alerts = payload.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]
    resolved = [a for a in alerts if a.get("status") == "resolved"]
    common = payload.get("commonLabels", payload.get("groupLabels", {}))

    if firing:
        title = f"🚨 告警触发 · {len(firing)}"
        if resolved:
            title += f" | 恢复 {len(resolved)}"
    else:
        title = f"✅ 告警恢复 · {len(resolved)}"

    alertname = common.get("alertname", "")
    if alertname:
        title += f" · {alertname}"

    lines = []
    if alertname:
        lines.append(f"规则: {alertname}")
    folder = common.get("grafana_folder", "")
    if folder:
        lines.append(f"目录: {folder}")

    for a in alerts:
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        icon = "🔴" if a["status"] == "firing" else "🟢"
        summary = ann.get("summary", labels.get("alertname", ""))
        lines.append("")
        lines.append(f"{icon} {summary}")

        for key, label in [("nodename","节点"), ("name","容器"), ("container","容器"),
                           ("job","作业"), ("ip_address","IP"), ("instance","目标"), ("target","目标")]:
            v = labels.get(key)
            if v:
                lines.append(f"{label}: {v}")

        if ann.get("description"):
            lines.append(f"说明: {ann['description']}")
        if a.get("values"):
            lines.append(f"数值: {a['values']}")

        ts = a.get("startsAt", a.get("endsAt", ""))
        prefix = "开始" if a["status"] == "firing" else "恢复"
        if ts:
            lines.append(f"{prefix}: {ts[:16]}")

    return title, "\n".join(lines)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid json")
            return

        title, message = format_alert(payload)

        creds = base64.b64encode(f"{NTFY_USER}:{NTFY_PASS}".encode()).decode()
        req = urllib.request.Request(NTFY_URL, data=message.encode("utf-8"), method="POST")
        req.add_header("Title", title)
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Priority", "high" if payload.get("status") == "firing" else "default")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.send_response(resp.status)
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
