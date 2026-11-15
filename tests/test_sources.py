"""수집원 파서와 robots.txt 판정 점검. 2026-11-15에 각 사이트에서 실제로 받은 응답 형식을 줄여서 씁니다.

실행: python tests/test_sources.py
"""
import os
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update({"YOUTUBE_API_KEY": "yt", "X_BEARER_TOKEN": "", "NAVER_CLIENT_ID": "n", "NAVER_CLIENT_SECRET": "n",
                   "THREADS_ACCESS_TOKEN": "", "TREND_SOURCES": ""})

import config  # noqa: E402
from bot import robots, sources  # noqa: E402

NOW = format_datetime(datetime.now(timezone.utc))

# ── robots.txt (실제 내용) ──────────────────────────────────────────────
ROBOTS = {
    "https://www.daum.net": "User-agent: GoogleOther\nDisallow: /\nAllow :  /.well-known/privacy-sandbox-attestations.json\n\n"
                            "User-agent: *\nDisallow: /\nAllow : /$\nAllow : /ads.txt\nAllow : /app-ads.txt",
    "https://zum.com": "User-agent: *\nDisallow: /\nAllow: /$\nAllow: /ads.txt \nAllow: /app-ads.txt\n\n"
                       "User-agent: ias_crawler\nDisallow:\n\nUser-agent: Mediapartners-Google\nAllow: /",
    "https://www.nate.com": "User-agent: *\nDisallow: /\nAllow : /$\nAllow : /ads.txt\n",
    "https://pann.nate.com": "User-agent: *\nDisallow: /\n\nUser-agent: Twitterbot\nUser-agent: Googlebot\nDisallow: /main\n"
                             "Disallow: /*reply\n\nUser-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /",
    "https://gall.dcinside.com": "User-agent: GPTBot\nDisallow: /\nUser-agent: ClaudeBot\nDisallow: /\n"
                                 "# ----- 그 외 모든 봇 -----\nUser-agent: *\nAllow: /\nDisallow: /kcaptcha/image_v3/\n"
                                 "Disallow: /board/lists/?id=47\nDisallow: /board/view/?id=47\n"
                                 "Disallow: /board/lists/?id=m_entertainer1\r\nSitemap: https://gall.dcinside.com/_seo/main_gall.xml",
    "https://signal.bz": "User-agent: *\nAllow: /\nUser-agent: *\nDisallow: /private*/",
}


def rules(host):
    return robots.parse(ROBOTS[host])


assert robots.is_allowed(rules("https://www.daum.net"), "/")                  # 첫 화면만 허용
assert not robots.is_allowed(rules("https://www.daum.net"), "/news")
assert robots.is_allowed(rules("https://zum.com"), "/") and not robots.is_allowed(rules("https://zum.com"), "/issue")
assert not robots.is_allowed(rules("https://www.nate.com"), "/js/data/jsonLiveKeywordDataV1.js")   # 네이트 키워드 파일은 불허
assert not robots.is_allowed(rules("https://pann.nate.com"), "/talk/ranking")                       # 네이트판 불허
dc = rules("https://gall.dcinside.com")
assert robots.is_allowed(dc, "/board/lists/?id=dcbest")
assert not robots.is_allowed(dc, "/board/lists/?id=47") and not robots.is_allowed(dc, "/board/lists/?id=m_entertainer1")
assert robots.is_allowed(rules("https://signal.bz"), "/") and not robots.is_allowed(rules("https://signal.bz"), "/private1/x")
assert robots.is_allowed([], "/anything")                                      # robots.txt 없음
assert not robots.is_allowed(robots.parse("User-agent: cardnews-bot\nDisallow: /\n\nUser-agent: *\nAllow: /"), "/")  # 이름으로 막으면 따름
print("1. robots.txt 판정 통과")

# ── 응답 견본 ───────────────────────────────────────────────────────────
GOOGLE_TRENDS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
<channel><title>Daily Search Trends</title>
<item><title>데블스 플랜</title><ht:approx_traffic>500+</ht:approx_traffic><description/>
  <link>https://trends.google.com/trending/rss?geo=KR</link><pubDate>{NOW}</pubDate>
  <ht:picture>https://example.com/p.jpg</ht:picture><ht:picture_source>뉴시스</ht:picture_source>
  <ht:news_item><ht:news_item_title>&quot;반전의 연속&quot;…데블스 플랜 새 시즌</ht:news_item_title><ht:news_item_snippet/>
    <ht:news_item_url>https://www.newsis.com/view/1</ht:news_item_url><ht:news_item_source>뉴시스</ht:news_item_source></ht:news_item>
</item>
<item><title>지난주 검색어</title><pubDate>Mon, 01 Jan 2024 10:00:00 -0800</pubDate></item>
</channel></rss>"""

GOOGLE_NEWS = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>엔터테인먼트</title>
<item><title>케데헌 '골든', 英 차트 73주째 톱 100 - 연합뉴스</title><link>https://news.google.com/rss/articles/AAA?oc=5</link>
<pubDate>{NOW}</pubDate><description>&lt;ol&gt;&lt;li&gt;&lt;a href="https://news.google.com/rss/articles/AAA?oc=5" target="_blank"&gt;케데헌 '골든', 英 차트 73주째 톱 100&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;연합뉴스&lt;/font&gt;&lt;/li&gt;&lt;li&gt;&lt;a href="https://news.google.com/rss/articles/BBB?oc=5" target="_blank"&gt;'골든' 장기 흥행 이어간다&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;스타뉴스&lt;/font&gt;&lt;/li&gt;&lt;/ol&gt;</description>
<source url="https://www.yna.co.kr">연합뉴스</source></item>
<item><title>단독 보도 하나뿐인 기사 - 국제뉴스</title><link>https://news.google.com/rss/articles/CCC</link><pubDate>{NOW}</pubDate>
<description>&lt;a href="https://news.google.com/rss/articles/CCC" target="_blank"&gt;단독 보도 하나뿐인 기사&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;국제뉴스&lt;/font&gt;</description>
<source url="https://www.gukjenews.com">국제뉴스</source></item>
</channel></rss>"""

DAUM = ('<html><script>{"name":"실시간 트렌드 - 상단","code":4860,"uiType":"REALTIME_TREND_TOP","attributes":{"serviceTitle":"실시간 트렌드"},'
        '"contents":{"data":{"updatedAt":"2026-11-15T00:57:56.486+09:00","keywords":['
        '{"keyword":"엑스러브 북미 투어 규모 확장","rank":3,"displayRank":2,"status":"0","tiara":{"x":1}},'
        '{"keyword":"창사특집 나의 이방인","rank":8,"displayRank":3,"status":"-4"},'
        '{"keyword":"문무 \\"드라마\\"","rank":1,"displayRank":1,"status":"1"}]}}},'
        '{"uiType":"REALTIME_TREND_MIDDLE","contents":{"data":{"keywords":[{"keyword":"창사특집 나의 이방인","rank":8,"displayRank":3}]}}}</script></html>')

ZUM = ('<div class="swiper-container issue-word-list issue-word-list--cards"><span class="issue-word-list__title">AI 이슈트렌드</span>'
       '<span class="issue-word-list__card-copy"><span class="issue-word-list__card-keyword">멜론뮤직어워드 레드카펫</span>'
       '<strong class="issue-word-list__card-title">올해 시상식 레드카펫 현장</strong></span>'
       '<span class="issue-word-list__card-copy"><span class="issue-word-list__card-keyword">문무 첫 방송 &amp; 반응</span>'
       '<strong class="issue-word-list__card-title">대하드라마 첫 방송</strong></span>'
       '<span class="issue-word-list__card-keyword">멜론뮤직어워드 레드카펫</span></div>')

SIGNAL = {"now": 1794676361010, "top10": [
    {"rank": 2, "keyword": "장혁 연기, 문무 첫 방송", "state": "n", "summary": "https://summary.signal.bz/x"},
    {"rank": 1, "keyword": "멜론뮤직어워드 레드카펫", "state": "n"}]}

DC = ('<table><tr class="ub-content" ><td class="gall_num">설문</td><td class="gall_tit ub-word"><a href="/board/view/?id=dcbest&no=1">설문 글</a></td></tr>'
      '<tr class="ub-content us-post" data-no="2" data-type="icon_notice"><td class="gall_tit ub-word"><a href="/board/view/?id=dcbest&amp;no=2">이용 안내</a></td></tr>'
      '<tr class="ub-content us-post thum" data-no="478725" data-type="icon_btimebest">\n<td class="gall_num">478725</td>\n<td class="gall_tit ub-word">\t\n'
      '<a href="/board/view/?id=dcbest&amp;no=478725&amp;_dcbest=1&amp;page=1" view-msg="">\n<div class="thumimg"><img src="https://x/y" alt="썸네일"></div>\n'
      '<em class="icon_img icon_btimebest"></em><strong>[싱갤]</strong> 싱글벙글 추억의 아동만화</a>\n'
      '<a class="reply_numbox" href="https://gall.dcinside.com/board/view/?id=dcbest&amp;no=478725&amp;t=cv"><span class="reply_num">[31]</span></a></td></tr></table>')

YOUTUBE = {"items": [{"snippet": {"title": "가상밴드 &amp; 친구들 'Comeback' MV", "channelTitle": "가상밴드 Official", "categoryId": "10"},
                      "statistics": {"viewCount": "1234567"}}]}

NAVER_CALLS = []


class Resp:
    def __init__(self, status=200, text="", body=None):
        self.status_code, self.text, self._body = status, text, body
        self.content, self.encoding = text.encode("utf-8"), "utf-8"

    def json(self):
        return self._body


def fake_get(url, **kw):
    assert "cardnews-bot" in kw.get("headers", {}).get("User-Agent", "cardnews-bot") or "naver" in url
    for host, text in ROBOTS.items():
        if url == host + "/robots.txt":
            return Resp(text=text)
    if url == "https://api.signal.bz/robots.txt":
        return Resp(status=404)
    if "trends.google.com" in url:
        return Resp(text=GOOGLE_TRENDS)
    if "news.google.com" in url:
        assert kw["params"] == {"hl": "ko", "gl": "KR", "ceid": "KR:ko"}
        return Resp(text=GOOGLE_NEWS)
    if url == "https://www.daum.net/":
        return Resp(text=DAUM)
    if url == "https://zum.com/":
        return Resp(text=ZUM)
    if url == "https://api.signal.bz/news/realtime":
        return Resp(body=SIGNAL)
    if url.startswith("https://gall.dcinside.com/board/lists/"):
        return Resp(text=DC)
    if "googleapis.com/youtube" in url:
        assert kw["params"]["chart"] == "mostPopular" and kw["params"]["regionCode"] == "KR"
        return Resp(body=YOUTUBE)
    if "cafearticle.json" in url or "blog.json" in url:
        if kw["params"]["query"] != "데블스 플랜":
            return Resp(body={"items": []})
        assert kw["params"]["sort"] == "date"
        if "cafearticle" in url:
            return Resp(body={"items": [{"title": "<b>데블스 플랜</b> 보신 분?", "description": "어제 회차 반전 대박", "cafename": "예능 수다방"}]})
        return Resp(body={"items": [{"title": "데블스 플랜 후기", "description": "정주행 완료", "bloggername": "일상기록", "postdate": "20261115"}]})
    if "openapi.naver.com" in url:
        query = kw["params"]["query"]
        NAVER_CALLS.append(query)
        if query in ("데블스 플랜", "문무 드라마", "멜론뮤직어워드 레드카펫", "장혁 연기"):   # 마지막은 '앞 두 단어' 재검색
            return Resp(body={"items": [
                {"title": f"<b>{query}</b> 화제", "description": "요약", "originallink": "https://www.news-a.kr/1", "pubDate": NOW},
                {"title": f"{query} 반응", "description": "요약", "originallink": "https://news-b.com/2", "pubDate": NOW}]})
        return Resp(body={"items": []})
    raise AssertionError("예상 못 한 GET: " + url)


config.TREND_SOURCES = list(sources.SOURCES)
with mock.patch("requests.get", fake_get):
    results, report = sources.gather()
    print(*report, sep="\n")

    assert [t["name"] for t in results["google"]] == ["데블스 플랜"]
    assert results["google"][0]["news"][0] == {"title": '"반전의 연속"…데블스 플랜 새 시즌', "summary": "", "source": "뉴시스",
                                               "domain": "newsis.com", "url": "https://www.newsis.com/view/1", "published": ""}
    assert [t["name"] for t in results["daum"]] == ['문무 "드라마"', "엑스러브 북미 투어 규모 확장", "창사특집 나의 이방인"]   # 순위순, 중복 제거
    assert [t["name"] for t in results["zum"]] == ["멜론뮤직어워드 레드카펫", "문무 첫 방송 & 반응"]
    assert [t["name"] for t in results["signal"]] == ["멜론뮤직어워드 레드카펫", "장혁 연기, 문무 첫 방송"]
    news = results["google_news"]
    assert len(news) == 1 and news[0]["name"] == "케데헌 '골든', 英 차트 73주째 톱 100" and news[0]["kind"] == "headline"
    assert [n["source"] for n in news[0]["news"]] == ["연합뉴스", "스타뉴스"]       # 한 곳만 보도한 기사는 제외됨
    assert results["youtube"] == ["가상밴드 & 친구들 'Comeback' MV — 가상밴드 Official (조회 1,234,567)"]
    assert results["dcinside"] == ["[싱갤] 싱글벙글 추억의 아동만화"]                # 공지·설문 제외
    assert "x" not in results and any("X 트렌드: 건너뜀" in line for line in report)
    print("2. 수집원 8종 파싱 통과")

    candidates, signals = sources.collect(set())
    names = [c["trend"] for c in candidates]
    # 수집원별 1위부터 번갈아 섞임, 줌·시그널에 함께 나온 검색어는 하나로 합쳐지고 출처가 둘 다 남음
    merged = next(c for c in candidates if c["trend"] == "멜론뮤직어워드 레드카펫")
    assert merged["origins"] == ["줌 이슈트렌드", "시그널 실시간 검색어"], merged["origins"]
    assert names[0] == "데블스 플랜" and names[-1] == "케데헌 '골든', 英 차트 73주째 톱 100", names
    assert "엑스러브 북미 투어 규모 확장" not in names                               # 뉴스로 확인 안 된 검색어는 탈락
    assert "장혁 연기, 문무 첫 방송" in names and "장혁 연기" in NAVER_CALLS          # 긴 문구는 앞 두 단어로 재검색
    google = next(c for c in candidates if c["trend"] == "데블스 플랜")
    assert [n["domain"] for n in google["news"]] == ["news-a.kr", "news-b.com", "newsis.com"]
    assert set(signals) == {"유튜브 인기 동영상", "디시 실시간 베스트"}
    assert google["buzz"] == ["[카페 · 예능 수다방] 데블스 플랜 보신 분? — 어제 회차 반전 대박", "[블로그 · 일상기록] 데블스 플랜 후기 — 정주행 완료"]
    print("3. 후보 병합 통과:", names)

    # 이미 다룬 주제 제외
    done = {sources.normalize("데블스 플랜"), sources.normalize("케데헌 '골든', 英 차트 73주째 톱 100")}
    names = [c["trend"] for c in sources.collect(done)[0]]
    assert "데블스 플랜" not in names and not any("케데헌" in n for n in names)
    print("4. 다룬 주제 제외 통과")

    # robots.txt가 막으면 읽지 않음 / robots.txt 서버 오류면 읽지 않음
    robots._cache.clear()
    ROBOTS["https://www.daum.net"] = "User-agent: *\nDisallow: /"
    del ROBOTS["https://zum.com"]

    def fake_get_broken(url, **kw):
        if url == "https://zum.com/robots.txt":
            return Resp(status=503)
        return fake_get(url, **kw)

    with mock.patch("requests.get", fake_get_broken):
        results, report = sources.gather()
    assert "daum" not in results and "zum" not in results and "signal" in results
    assert sum("robots.txt" in line for line in report) == 2, report
    print("5. robots.txt 불허·확인 불가 시 건너뜀 통과")

# 프롬프트에 후보·신호가 들어가는 모양
from bot import editor  # noqa: E402

text = editor._format_candidates(candidates) + editor._format_signals(signals)
assert "## 후보 0: 데블스 플랜  [실시간 검색어 | 출처: 구글 트렌드 | 검색 500+]" in text
assert "[뉴스 묶음 | 출처: 구글 뉴스 연예 | 2개 언론사 보도]" in text and "(제목만 제공됨)" in text
assert "- 반응 [카페 · 예능 수다방] 데블스 플랜 보신 분?" in text
assert "# 참고 신호" in text and "## 디시 실시간 베스트\n- [싱갤] 싱글벙글 추억의 아동만화" in text
print("6. 프롬프트 구성 통과")
print("\n모든 점검 통과")
