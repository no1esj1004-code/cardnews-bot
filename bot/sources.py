"""1단계: 여러 곳에서 '지금 뜨는 주제'를 모으고, 그 주제가 무엇인지 확인할 뉴스 맥락을 붙입니다.

수집원은 세 종류입니다.
  keyword  : 실시간 검색어 (구글 트렌드, 다음, 줌, 시그널, X) → 네이버 뉴스로 내용을 확인해 후보로
  headline : 연예 뉴스 묶음 (구글 뉴스) → 같은 사건을 다룬 여러 언론사 기사가 함께 와서 그대로 후보로
  signal   : 화제성 참고 신호 (유튜브 인기 동영상, 디시 실시간 베스트) → 후보가 아니라 참고 목록으로만

한 곳이 실패해도 나머지로 계속 진행하고, 결과는 수집원별로 한 줄씩 출력합니다.
웹 페이지를 직접 읽는 수집원은 먼저 robots.txt를 확인해 허용된 경우에만 읽습니다.
"""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from itertools import zip_longest
from urllib.parse import urlparse

import requests

import config
from bot import robots

TIMEOUT = 20
HEADERS = {"User-Agent": robots.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}
KST = timezone(timedelta(hours=9))
_TAG = re.compile(r"<[^>]+>")


class Skip(Exception):
    """수집원을 이번 회차에 쓰지 않는 사유 (키 없음, robots.txt 불허 등). 오류가 아닙니다."""


# ── 공통 유틸 ───────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", text or ""))).strip()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _local(tag: str) -> str:
    """'{namespace}approx_traffic' → 'approx_traffic'"""
    return tag.rsplit("}", 1)[-1]


def _is_recent(pub_date: str, hours: int) -> bool:
    try:
        return parsedate_to_datetime(pub_date) >= datetime.now(timezone.utc) - timedelta(hours=hours)
    except (TypeError, ValueError):
        return True  # 날짜를 못 읽으면 포함


def _get(url: str, check_robots: bool = False, **kwargs) -> requests.Response:
    if check_robots and not robots.allowed(url):
        raise Skip("robots.txt에서 자동 수집을 허용하지 않음")
    resp = requests.get(url, headers={**HEADERS, **kwargs.pop("headers", {})}, timeout=TIMEOUT, **kwargs)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp


def _trend(name: str, origin: str, volume: str = "", news: list | None = None, kind: str = "keyword") -> dict:
    return {"name": name, "origin": origin, "volume": volume, "news": news or [], "kind": kind}


def normalize(name: str) -> str:
    """중복 판단용 정규화: '#아이유_컴백' → '아이유컴백'"""
    return re.sub(r"[\s#_\-·.,!?~'\"“”‘’…\[\]()]+", "", name).lower()


def to_query(name: str) -> str:
    """검색어로 쓰기 좋게 변환: '#아이유_컴백' → '아이유 컴백'"""
    return re.sub(r"\s+", " ", re.sub(r"[#_,]", " ", name)).strip()


# ══ keyword 수집원 ══════════════════════════════════════════════════════
def fetch_google_trends() -> list[dict]:
    """구글 '지금 뜨는 검색어' 공개 RSS. 검색어마다 관련 기사 제목이 함께 옵니다. (키 불필요)"""
    resp = _get("https://trends.google.com/trending/rss", params={"geo": config.GOOGLE_TRENDS_GEO})
    trends = []
    for item in ET.fromstring(resp.content).iter("item"):
        fields = {_local(child.tag): (child.text or "").strip() for child in item}
        name = fields.get("title", "")
        if not name or not _is_recent(fields.get("pubDate", ""), 24):
            continue
        news = []
        for child in item:
            if _local(child.tag) != "news_item":
                continue
            sub = {_local(c.tag): (c.text or "").strip() for c in child}
            url, title = sub.get("news_item_url", ""), _clean(sub.get("news_item_title", ""))
            if url and title:
                news.append({"title": title, "summary": _clean(sub.get("news_item_snippet", "")),
                             "source": sub.get("news_item_source") or _domain(url), "domain": _domain(url),
                             "url": url, "published": ""})
        traffic = fields.get("approx_traffic", "")
        trends.append(_trend(name, "구글 트렌드", f"검색 {traffic}" if traffic else "", news))
    return trends


def fetch_daum_trends() -> list[dict]:
    """다음 첫 화면의 '실시간 트렌드'. 첫 화면 HTML 안에 JSON으로 들어 있습니다."""
    resp = _get("https://www.daum.net/", check_robots=True)
    resp.encoding = "utf-8"
    start = resp.text.find("REALTIME_TREND")
    if start < 0:
        raise RuntimeError("실시간 트렌드 영역을 찾지 못함 (페이지 형식 변경 가능성)")
    found: dict[str, int] = {}
    for raw, rank in re.findall(r'"keyword":"((?:[^"\\]|\\.)*)","rank":(\d+)', resp.text[start:]):
        try:
            keyword = json.loads(f'"{raw}"').strip()
        except ValueError:
            continue
        if keyword and keyword not in found:
            found[keyword] = int(rank)
    if not found:
        raise RuntimeError("검색어를 읽지 못함 (페이지 형식 변경 가능성)")
    return [_trend(k, "다음 실시간 트렌드") for k, _ in sorted(found.items(), key=lambda kv: kv[1])]


def fetch_zum_trends() -> list[dict]:
    """줌 첫 화면의 'AI 이슈트렌드' 카드."""
    resp = _get("https://zum.com/", check_robots=True)
    resp.encoding = "utf-8"
    keywords = list(dict.fromkeys(
        _clean(k) for k in re.findall(r'issue-word-list__card-keyword">(.*?)</span>', resp.text, re.S)))
    keywords = [k for k in keywords if k]
    if not keywords:
        raise RuntimeError("이슈 키워드를 읽지 못함 (페이지 형식 변경 가능성)")
    return [_trend(k, "줌 이슈트렌드") for k in keywords]


def fetch_signal_trends() -> list[dict]:
    """시그널(signal.bz) 실시간 검색어 상위 10개."""
    resp = _get("https://api.signal.bz/news/realtime", check_robots=True)
    items = sorted(resp.json().get("top10", []), key=lambda x: x.get("rank", 99))
    keywords = [str(i.get("keyword", "")).strip() for i in items]
    if not any(keywords):
        raise RuntimeError("검색어를 읽지 못함 (응답 형식 변경 가능성)")
    return [_trend(k, "시그널 실시간 검색어") for k in keywords if k]


def fetch_x_trends() -> list[dict]:
    """X(트위터) 대한민국 트렌드. 유료 API라 토큰이 있을 때만 씁니다."""
    if not config.X_BEARER_TOKEN:
        raise Skip("X_BEARER_TOKEN 없음 (유료, 선택)")
    resp = _get(f"https://api.x.com/2/trends/by/woeid/{config.X_WOEID}",
                headers={"Authorization": f"Bearer {config.X_BEARER_TOKEN}"},
                params={"max_trends": 50, "trend.fields": "trend_name,tweet_count"})
    trends = []
    for item in resp.json().get("data", []):
        name = (item.get("trend_name") or "").strip()
        if name:
            count = item.get("tweet_count")
            trends.append(_trend(name, "X 트렌드", f"게시물 {count:,}건" if count else ""))
    return trends


# ══ headline 수집원 ═════════════════════════════════════════════════════
_RELATED = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>(?:&nbsp;|\s)*<font[^>]*>(.*?)</font>', re.S)


def fetch_google_news(max_clusters: int = 10) -> list[dict]:
    """구글 뉴스 '엔터테인먼트' 섹션 RSS. 기사 하나에 같은 사건을 다룬 다른 언론사 기사 목록이 붙어 옵니다."""
    resp = _get("https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT",
                params={"hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    clusters = []
    for item in ET.fromstring(resp.content).iter("item"):
        fields = {_local(child.tag): (child.text or "").strip() for child in item}
        if not fields.get("title") or not _is_recent(fields.get("pubDate", ""), 24):
            continue
        source = fields.get("source", "")
        headline = fields["title"]
        if source and headline.endswith(f" - {source}"):
            headline = headline[: -len(source) - 3].strip()
        news, seen = [], set()
        related = _RELATED.findall(fields.get("description", "")) or [(fields.get("link", ""), headline, source)]
        for url, title, publisher in related:
            publisher, title = _clean(publisher), _clean(title)
            if not (publisher and title) or publisher in seen:
                continue
            seen.add(publisher)
            news.append({"title": title, "summary": "", "source": publisher, "domain": publisher,
                         "url": html.unescape(url), "published": ""})
        if len(news) >= config.MIN_SOURCES:   # 여러 언론사가 함께 다룬 것만 후보로
            clusters.append(_trend(headline, "구글 뉴스 연예", f"{len(news)}개 언론사 보도", news, kind="headline"))
        if len(clusters) >= max_clusters:
            break
    return clusters


# ══ signal 수집원 (참고용 제목 목록) ════════════════════════════════════
def fetch_youtube_titles(limit: int = 25) -> list[str]:
    """유튜브 한국 인기 동영상 제목. YouTube Data API 키(무료 할당량)가 필요합니다."""
    if not config.YOUTUBE_API_KEY:
        raise Skip("YOUTUBE_API_KEY 없음 (무료 발급 가능)")
    resp = _get("https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet,statistics", "chart": "mostPopular", "regionCode": "KR",
                        "hl": "ko", "maxResults": limit, "key": config.YOUTUBE_API_KEY})
    titles = []
    for item in resp.json().get("items", []):
        snippet = item.get("snippet", {})
        views = int(item.get("statistics", {}).get("viewCount", 0) or 0)
        title = _clean(snippet.get("title", ""))[:80]
        if title:
            titles.append(f"{title} — {snippet.get('channelTitle', '')} (조회 {views:,})")
    return titles


def fetch_dcinside_titles(limit: int = 25) -> list[str]:
    """디시인사이드 '실시간 베스트' 글 제목. 사실 근거가 아니라 화제성 참고용입니다."""
    resp = _get("https://gall.dcinside.com/board/lists/?id=dcbest", check_robots=True)
    resp.encoding = "utf-8"
    titles = []
    for row in resp.text.split('<tr class="ub-content')[1:]:
        if 'data-type="icon_btimebest"' not in row[:300]:
            continue  # 공지·설문 제외
        match = re.search(r'<a href="/board/view/\?id=dcbest[^"]*"[^>]*>(.*?)</a>', row, re.S)
        if match:
            title = _clean(match.group(1))[:80]
            if title:
                titles.append(title)
        if len(titles) >= limit:
            break
    if not titles:
        raise RuntimeError("글 제목을 읽지 못함 (페이지 형식 변경 또는 접속 차단 가능성)")
    return titles


# ── 수집원 목록 ─────────────────────────────────────────────────────────
SOURCES = {
    #  이름            (함수,                  종류,       표시 이름)
    "google":      (fetch_google_trends,   "keyword",  "구글 트렌드"),
    "daum":        (fetch_daum_trends,     "keyword",  "다음 실시간 트렌드"),
    "zum":         (fetch_zum_trends,      "keyword",  "줌 이슈트렌드"),
    "signal":      (fetch_signal_trends,   "keyword",  "시그널 실시간 검색어"),
    "x":           (fetch_x_trends,        "keyword",  "X 트렌드"),
    "google_news": (fetch_google_news,     "headline", "구글 뉴스 연예"),
    "youtube":     (fetch_youtube_titles,  "signal",   "유튜브 인기 동영상"),
    "dcinside":    (fetch_dcinside_titles, "signal",   "디시 실시간 베스트"),
}


def gather() -> tuple[dict[str, list], list[str]]:
    """설정된 수집원을 모두 실행합니다. 반환: ({이름: 결과 목록}, [수집원별 결과 한 줄씩])"""
    results: dict[str, list] = {}
    report = []
    for name in config.TREND_SOURCES:
        if name not in SOURCES:
            report.append(f"  ? {name}: 알 수 없는 수집원 ({', '.join(SOURCES)} 중에서 고르세요)")
            continue
        fetcher, _, label = SOURCES[name]
        try:
            results[name] = fetcher()
            report.append(f"  ✓ {label}: {len(results[name])}개")
        except Skip as exc:
            report.append(f"  - {label}: 건너뜀 ({exc})")
        except (RuntimeError, requests.RequestException, ET.ParseError, ValueError) as exc:
            report.append(f"  ✗ {label}: 실패 ({exc})")
    return results, report


# ══ 네이버 뉴스 (사실 확인) ═════════════════════════════════════════════
def _naver_search(query: str) -> list[dict]:
    resp = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        headers={"X-Naver-Client-Id": config.NAVER_CLIENT_ID,
                 "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET},
        params={"query": query, "display": 10, "sort": "sim"},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"네이버 뉴스 검색 실패 ({resp.status_code}): {resp.text[:200]}")
    return resp.json().get("items", [])


def fetch_news(query: str, max_items: int = 5, within_hours: int = 48) -> list[dict]:
    """키워드 관련 최근 뉴스 (언론사당 1건). 네이버 키가 없으면 빈 리스트."""
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        return []
    words = query.split()
    queries = [query] + ([" ".join(words[:2])] if len(words) > 2 else [])  # 긴 문구는 앞 두 단어로 재시도
    for q in queries:
        items, seen = [], set()
        for raw in _naver_search(q):
            if not _is_recent(raw.get("pubDate", ""), within_hours):
                continue
            try:
                published = parsedate_to_datetime(raw.get("pubDate", "")).astimezone(KST).strftime("%m/%d %H:%M")
            except (TypeError, ValueError):
                published = ""
            url = raw.get("originallink") or raw.get("link") or ""
            source = _domain(url)
            if not source or source in seen:
                continue
            seen.add(source)
            items.append({"title": _clean(raw.get("title")), "summary": _clean(raw.get("description")),
                          "source": source, "domain": source, "url": url, "published": published})
            if len(items) >= max_items:
                break
        if items:
            return items
    return []


def fetch_threads_posts(query: str, max_items: int = 5) -> list[str]:
    """(선택) Threads 공개 게시물 반응. THREADS_ACCESS_TOKEN이 없으면 빈 리스트."""
    if not config.THREADS_ACCESS_TOKEN:
        return []
    try:
        resp = requests.get(
            "https://graph.threads.net/v1.0/keyword_search",
            params={"q": query, "search_type": "TOP", "fields": "id,text,timestamp",
                    "access_token": config.THREADS_ACCESS_TOKEN},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        texts = [(p.get("text") or "").strip() for p in resp.json().get("data", [])]
        return [t[:200] for t in texts if t][:max_items]
    except requests.RequestException:
        return []


# ══ 후보 묶음 만들기 ════════════════════════════════════════════════════
def merge_news(primary: list[dict], extra: list[dict], max_items: int = 6) -> list[dict]:
    """같은 언론사(도메인)는 한 번만 남기고 합칩니다."""
    merged, seen = [], set()
    for item in primary + extra:
        if item["domain"] not in seen:
            seen.add(item["domain"])
            merged.append(item)
    return merged[:max_items]


def interleave(results: dict[str, list], kind: str) -> list[dict]:
    """수집원별 1위, 2위, 3위… 순으로 번갈아 섞고, 같은 검색어는 하나로 합칩니다(출처는 모두 기록)."""
    lists = [results[name] for name in results if SOURCES[name][1] == kind]
    merged: dict[str, dict] = {}
    for row in zip_longest(*lists):
        for trend in row:
            if trend is None:
                continue
            key = normalize(trend["name"])
            if not key:
                continue
            if key in merged:
                first = merged[key]
                if trend["origin"] not in first["origins"]:
                    first["origins"].append(trend["origin"])
                first["news"] = merge_news(first["news"], trend["news"])
            else:
                merged[key] = {**trend, "origins": [trend["origin"]]}
    return list(merged.values())


def collect(exclude_norms: set[str]) -> tuple[list[dict], dict[str, list[str]]]:
    """후보(뉴스 맥락 포함)와 참고 신호를 모읍니다. 반환: (후보 목록, {신호 이름: [제목…]})"""
    results, report = gather()
    print("수집 결과:", *report, sep="\n")
    usable = [n for n in results if SOURCES[n][1] != "signal" and results[n]]
    if not usable:
        raise RuntimeError("후보를 만들 수 있는 수집원이 하나도 성공하지 못했습니다.")
    has_naver = bool(config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET)
    if not has_naver:
        print("(네이버 검색 키 없음 → 기사 제목이 함께 오는 구글 트렌드·구글 뉴스만 후보가 됩니다)")

    candidates = []
    # 1) 실시간 검색어 → 네이버 뉴스로 확인
    for trend in interleave(results, "keyword"):
        if len(candidates) >= config.CANDIDATE_COUNT:
            break
        if normalize(trend["name"]) in exclude_norms:
            continue
        query = to_query(trend["name"])
        if len(query) < 2:
            continue
        try:
            naver_news = fetch_news(query)
        except (RuntimeError, requests.RequestException) as exc:
            print(f"  뉴스 조회 실패 [{query}]: {exc}")
            naver_news = []
        news = merge_news(naver_news, trend["news"])
        if news:  # 뉴스로 확인되지 않는 주제는 다루지 않습니다
            candidates.append({"trend": trend["name"], "origins": trend["origins"], "volume": trend["volume"],
                               "kind": "keyword", "news": news, "threads": fetch_threads_posts(query)})

    # 2) 연예 뉴스 묶음 → 그대로 후보
    headline_count = 0
    for trend in interleave(results, "headline"):
        if headline_count >= config.HEADLINE_COUNT:
            break
        if normalize(trend["name"]) in exclude_norms:
            continue
        candidates.append({"trend": trend["name"], "origins": trend["origins"], "volume": trend["volume"],
                           "kind": "headline", "news": trend["news"][:6], "threads": []})
        headline_count += 1

    signals = {SOURCES[n][2]: results[n] for n in results if SOURCES[n][1] == "signal" and results[n]}
    print(f"후보 {len(candidates)}개 (검색어 {len(candidates) - headline_count} + 뉴스 묶음 {headline_count}), "
          f"참고 신호 {sum(len(v) for v in signals.values())}건")
    return candidates, signals
