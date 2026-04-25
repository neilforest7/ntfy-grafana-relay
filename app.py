from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import http.client
import os
import base64
import ssl
from urllib.parse import urlparse
from email.header import Header

NTFY_URL = os.environ.get("NTFY_RELAY_URL", "https://ntfy.0qk.de/grafana")
NTFY_USER = os.environ.get("NTFY_RELAY_USER", "grafana-bot")
NTFY_PASS = os.environ.get("NTFY_RELAY_PASS", "grafana-bot-2026")

PARSED = urlparse(NTFY_URL)

def format_alert(payload):
    alerts = payload.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]
    resolved = [a for a in alerts if a.get("status") == "resolved"]
    common = payload.get("commonLabels", payload.get("groupLabels", {}))

    if firing:
        title = "告警触发 %d" % len(firing)
        if resolved:
            title += " | 恢复 %d" % len(resolved)
    else:
        title = "告警恢复 %d" % len(resolved)

    alertname = common.get("alertname", "")
    if alertname:
        title += " - %s" % alertname

    lines = []
    if alertname:
        lines.append("规则: %s" % alertname)
    folder = common.get("grafana_folder", "")
    if folder:
        lines.append("目录: %s" % folder)

    for a in alerts:
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        icon = ">>>" if a["status"] == "firing" else "<<<"
        summary = ann.get("summary", labels.get("alertname", ""))
        lines.append("")
        lines.append("%s %s" % (icon, summary))

        for key, label in [("nodename","节点"), ("name","容器"), ("container","容器"),
                           ("job","作业"), ("ip_address","IP"), ("instance","目标"), ("target","目标")]:
            v = labels.get(key)
            if v:
                lines.append("%s: %s" % (label, v))

        if ann.get("description"):
            lines.append("说明: %s" % ann["description"])
        if a.get("values"):
            lines.append("数值: %s" % a["values"])

        ts = a.get("startsAt", a.get("endsAt", ""))
        prefix = "开始" if a["status"] == "firing" else "恢复"
        if ts:
            lines.append("%s: %s" % (prefix, ts[:16]))

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

        creds = base64.b64encode(("%s:%s" % (NTFY_USER, NTFY_PASS)).encode()).decode()
        encoded_title = Header(title, "utf-8").encode()

        conn = http.client.HTTPSConnection(PARSED.hostname, timeout=10, context=ssl.create_default_context())
        headers = {
            "Title": encoded_title,
            "Authorization": "Basic %s" % creds,
            "Priority": "high" if payload.get("status") == "firing" else "default",
            "Content-Type": "text/plain; charset=utf-8",
        }
        conn.request("POST", PARSED.path, body=message.encode("utf-8"), headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read()
        self.send_response(resp.status)
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
