"""
Render Cron Job 진입점.
render.yaml의 cron service가 매일 23:00 UTC(= 08:00 KST)에 이 스크립트를 실행한다.
"""
import os
import urllib.request
import json

SELF_URL = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
CRON_SECRET = os.getenv("CRON_SECRET", "")

url = f"{SELF_URL}/api/v2/report/generate-all"
headers = {"Content-Type": "application/json"}
if CRON_SECRET:
    headers["X-Cron-Secret"] = CRON_SECRET

req = urllib.request.Request(url, data=b"{}", method="POST", headers=headers)
with urllib.request.urlopen(req, timeout=300) as r:
    result = json.load(r)

print(f"[cron] 발송 완료: {result}")
