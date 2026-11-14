"""robots.txt 확인. 사이트가 자동 수집을 막아둔 경로는 읽지 않습니다.

파이썬 기본 파서는 `*`, `$` 패턴을 지원하지 않아(다음·줌의 "Allow: /$" 같은 규칙을 못 읽음)
구글 방식(가장 길게 일치하는 규칙 우선, 같으면 Allow 우선)으로 직접 판정합니다.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

BOT_NAME = "cardnews-bot"
USER_AGENT = f"Mozilla/5.0 (compatible; {BOT_NAME}/1.0)"   # 브라우저인 척하지 않고 봇임을 밝힙니다
_cache: dict[str, list[tuple[bool, str]] | None] = {}


def parse(text: str, bot_name: str = BOT_NAME) -> list[tuple[bool, str]]:
    """이 봇에 적용되는 규칙 목록 [(허용여부, 경로패턴), ...]을 돌려줍니다."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    reading_agents = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not reading_agents:               # 새 그룹 시작
                if agents:
                    groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            reading_agents = True
        elif key in ("allow", "disallow"):
            reading_agents = False
            if value:                             # "Disallow:" (빈 값)는 제한 없음
                rules.append((key == "allow", value))
        else:
            reading_agents = False
    if agents:
        groups.append((agents, rules))

    named = [r for a, r in groups if any(x != "*" and x in bot_name.lower() for x in a)]
    if named:
        return [rule for group in named for rule in group]
    return [rule for a, r in groups if "*" in a for rule in r]


def _matches(pattern: str, path: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def is_allowed(rules: list[tuple[bool, str]], path: str) -> bool:
    best_len, best_allow = -1, True
    for allow, pattern in rules:
        if _matches(pattern, path):
            length = len(pattern)
            if length > best_len or (length == best_len and allow):
                best_len, best_allow = length, allow
    return best_allow


def allowed(url: str) -> bool:
    """이 주소를 자동으로 읽어도 되는지. robots.txt를 확인할 수 없으면(서버 오류 등) 읽지 않습니다."""
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _cache:
        try:
            resp = requests.get(f"{host}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
            if resp.status_code == 200:
                resp.encoding = "utf-8"
                _cache[host] = parse(resp.text)
            elif 400 <= resp.status_code < 500:
                _cache[host] = []                 # robots.txt 없음 → 제한 없음
            else:
                _cache[host] = None               # 서버 오류 → 판단 불가, 수집 안 함
        except requests.RequestException:
            _cache[host] = None
    rules = _cache[host]
    if rules is None:
        return False
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return is_allowed(rules, path)
