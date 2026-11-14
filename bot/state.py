"""게시 이력 관리: 같은 주제를 반복해서 올리지 않고, 하루 게시 수를 제한합니다."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import config

POSTED_FILE = config.STATE_DIR / "posted.json"
PENDING_FILE = config.STATE_DIR / "pending.json"
KEEP_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_posted() -> list[dict]:
    if not POSTED_FILE.exists():
        return []
    try:
        return json.loads(POSTED_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_posted(entries: list[dict]) -> None:
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).isoformat()
    entries = [e for e in entries if e.get("at", "") >= cutoff]
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def recent(hours: int) -> list[dict]:
    cutoff = (_now() - timedelta(hours=hours)).isoformat()
    return [e for e in load_posted() if e.get("at", "") >= cutoff]


def record(topic: str, trend_norm: str, status: str, media_id: str = "", link: str = "", note: str = "") -> None:
    """status: "posted"(게시됨) | "dry_run"(시험 생성) | "rejected"(안전장치에 걸려 제외)"""
    entries = load_posted()
    entries.append({
        "at": _now().isoformat(), "status": status, "topic": topic, "trend_norm": trend_norm,
        "media_id": media_id, "permalink": link, "note": note,
    })
    save_posted(entries)


def posted_count(hours: int = 24) -> int:
    return sum(1 for e in recent(hours) if e.get("status") == "posted")


def in_quiet_hours() -> bool:
    """QUIET_HOURS="1-6" → KST 01:00~06:59 동안 True. "23-6"처럼 자정을 넘겨도 됩니다."""
    spec = config.QUIET_HOURS.strip()
    if not spec:
        return False
    try:
        start, end = (int(x) for x in spec.split("-"))
    except ValueError:
        print(f"QUIET_HOURS 형식 오류({spec}) → 무시합니다. 예: 1-6")
        return False
    hour = datetime.now(timezone(timedelta(hours=9))).hour
    return start <= hour <= end if start <= end else (hour >= start or hour <= end)


def save_pending(data: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_pending() -> dict | None:
    if not PENDING_FILE.exists():
        return None
    return json.loads(PENDING_FILE.read_text(encoding="utf-8"))


def clear_pending() -> None:
    PENDING_FILE.unlink(missing_ok=True)
