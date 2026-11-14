"""5단계: 인스타그램에 캐러셀(여러 장) 게시물로 올립니다. (Instagram API with Instagram Login)"""
from __future__ import annotations

import time

import requests

import config

TIMEOUT = 60


def _base() -> str:
    version = f"/{config.IG_API_VERSION}" if config.IG_API_VERSION else ""
    return f"https://graph.instagram.com{version}"


def _call(method: str, path: str, **params) -> dict:
    params["access_token"] = config.IG_ACCESS_TOKEN
    url = f"{_base()}/{path}"
    resp = requests.get(url, params=params, timeout=TIMEOUT) if method == "GET" \
        else requests.post(url, data=params, timeout=TIMEOUT)
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:300]}
    if resp.status_code != 200 or "error" in body:
        raise RuntimeError(f"Instagram API 오류 [{method} {path}] {resp.status_code}: {body}")
    return body


def wait_until_public(urls: list[str], timeout: int = 180) -> None:
    """이미지 주소가 외부에서 열릴 때까지 기다립니다 (인스타 서버가 이 주소에서 이미지를 가져갑니다)."""
    deadline = time.time() + timeout
    pending = list(urls)
    while pending and time.time() < deadline:
        still = []
        for url in pending:
            try:
                resp = requests.get(url, timeout=20, stream=True)
                ok = resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/")
                resp.close()
            except requests.RequestException:
                ok = False
            if not ok:
                still.append(url)
        pending = still
        if pending:
            time.sleep(8)
    if pending:
        raise RuntimeError(f"이미지 주소가 열리지 않습니다: {pending[0]}")


def _wait_finished(container_id: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _call("GET", container_id, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"미디어 컨테이너 처리 실패: {status}")
        time.sleep(10)
    raise RuntimeError("미디어 컨테이너 처리 시간 초과")


def remaining_quota() -> int | None:
    """24시간 게시 한도 중 남은 횟수. 조회 실패 시 None."""
    try:
        data = _call("GET", f"{config.IG_USER_ID}/content_publishing_limit",
                     fields="quota_usage,config")["data"][0]
        return int(data["config"]["quota_total"]) - int(data["quota_usage"])
    except Exception:
        return None


def publish_carousel(image_urls: list[str], caption: str) -> str:
    """캐러셀 게시. 반환: 인스타 미디어 ID"""
    if not (config.IG_USER_ID and config.IG_ACCESS_TOKEN):
        raise RuntimeError("IG_USER_ID / IG_ACCESS_TOKEN이 설정되지 않았습니다.")
    if not 2 <= len(image_urls) <= 20:
        raise RuntimeError(f"캐러셀은 2~20장이어야 합니다 (현재 {len(image_urls)}장)")

    wait_until_public(image_urls)

    children = []
    for url in image_urls:
        child = _call("POST", f"{config.IG_USER_ID}/media", image_url=url, is_carousel_item="true")
        children.append(child["id"])
    for child_id in children:
        _wait_finished(child_id)

    # AI 생성 라벨(is_ai_generated)은 캐러셀 컨테이너에만 붙입니다. 낱장에 붙이면 오류가 납니다.
    carousel = _call(
        "POST", f"{config.IG_USER_ID}/media",
        media_type="CAROUSEL", children=",".join(children), caption=caption, is_ai_generated="true",
    )
    _wait_finished(carousel["id"])
    published = _call("POST", f"{config.IG_USER_ID}/media_publish", creation_id=carousel["id"])
    return published["id"]


def permalink(media_id: str) -> str:
    try:
        return _call("GET", media_id, fields="permalink").get("permalink", "")
    except RuntimeError:
        return ""
