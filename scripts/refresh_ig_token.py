"""인스타그램 장기 토큰(60일)을 갱신해 새 토큰만 표준출력으로 내보냅니다.

발급 후 24시간이 지났고 아직 만료되지 않은 토큰만 갱신할 수 있습니다.
"""
import os
import sys

import requests

token = os.environ.get("IG_ACCESS_TOKEN", "")
if not token:
    sys.exit("IG_ACCESS_TOKEN 환경변수가 없습니다.")

resp = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": token},
    timeout=30,
)
data = resp.json()
if resp.status_code != 200 or "access_token" not in data:
    sys.exit(f"토큰 갱신 실패 ({resp.status_code}): {data.get('error', data)}")

print(f"유효기간: 약 {int(data.get('expires_in', 0)) // 86400}일", file=sys.stderr)
print(data["access_token"])
