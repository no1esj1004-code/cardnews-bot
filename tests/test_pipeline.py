"""외부 API를 가짜로 바꿔 전체 흐름을 점검합니다.  실행: python tests/test_pipeline.py"""
import base64
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update({
    "X_BEARER_TOKEN": "x", "NAVER_CLIENT_ID": "n", "NAVER_CLIENT_SECRET": "n",
    "ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "", "DRY_RUN": "true",
    "IG_USER_ID": "123", "IG_ACCESS_TOKEN": "t", "QUIET_HOURS": "", "THREADS_ACCESS_TOKEN": "",
    "TREND_SOURCES": "google,x", "YOUTUBE_API_KEY": "",
})

from PIL import Image  # noqa: E402

import config  # noqa: E402

tmp = Path(tempfile.mkdtemp())
config.OUTPUT_DIR, config.STATE_DIR = tmp / "output", tmp / "state"
config.ASSETS_DIR = tmp / "assets"
config.MASCOT_FILE, config.MASCOT_WAVE_FILE = config.ASSETS_DIR / "mascot.png", config.ASSETS_DIR / "mascot_wave.png"
config.MASCOT_SOURCE_FILE = config.ASSETS_DIR / "mascot_source.jpg"

from bot import editor, publish, safety, sources, state  # noqa: E402

state.POSTED_FILE, state.PENDING_FILE = config.STATE_DIR / "posted.json", config.STATE_DIR / "pending.json"
import main  # noqa: E402

from datetime import datetime, timezone  # noqa: E402
from email.utils import format_datetime  # noqa: E402

NOW = format_datetime(datetime.now(timezone.utc))
GOOD_PLAN = {
    "decision": "post", "candidate_index": 0, "topic": "가상 밴드 새 앨범 발매",
    "cover": {"kicker": "지금 뜨는 음악", "headline": "가상 밴드, 3년 만의 새 앨범", "sub": "타이틀곡 공개 직후 화제"},
    "cards": [{"title": f"제목 {i}", "body": "본문 내용이에요. " * 3, "image_prompt": f"scene {i}"} for i in range(3)],
    "caption": "가상 밴드가 돌아왔어요 🎸 여러분의 최애 수록곡은?", "hashtags": ["#가상밴드", "새 앨범"],
    "image_prompt": "a stage with warm lights", "visual_style": "Soft 3D clay render", "source_indexes": [0, 1],
}


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body or {}, headers or {}, json.dumps(body or {})

    def json(self):
        return self._body

    def close(self):
        pass


GOOGLE_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel><title>Daily Search Trends</title>
<item><title>가상밴드 컴백</title><ht:approx_traffic>20000+</ht:approx_traffic><pubDate>{NOW}</pubDate>
  <ht:news_item><ht:news_item_title>가상밴드, 3년 만에 &amp;quot;컴백&amp;quot;</ht:news_item_title>
    <ht:news_item_url>https://news-c.kr/9</ht:news_item_url><ht:news_item_source>뉴스C</ht:news_item_source></ht:news_item>
  <ht:news_item><ht:news_item_title>네이버와 같은 언론사</ht:news_item_title>
    <ht:news_item_url>https://www.news-a.kr/7</ht:news_item_url><ht:news_item_source>뉴스A</ht:news_item_source></ht:news_item>
</item>
<item><title>지난주 검색어</title><pubDate>Mon, 01 Jan 2024 10:00:00 +0900</pubDate></item>
</channel></rss>""".encode("utf-8")
google_status = 200


def fake_get(url, **kw):
    if "trends.google.com" in url:
        assert kw["params"]["geo"] == "KR"
        resp = Resp(status=google_status)
        resp.content = GOOGLE_RSS
        return resp
    if "api.x.com" in url:
        assert kw["headers"]["Authorization"] == "Bearer x"
        return Resp(body={"data": [{"trend_name": "#가상밴드_컴백", "tweet_count": 52000},
                                   {"trend_name": "뉴스없는키워드"}]})
    if "cafearticle.json" in url or "blog.json" in url:
        return Resp(body={"items": []})
    if "openapi.naver.com" in url:
        if "가상밴드" not in kw["params"]["query"]:
            return Resp(body={"items": []})
        return Resp(body={"items": [
            {"title": "<b>가상밴드</b> 새 앨범 &quot;공개&quot;", "description": "3년 만의 정규 앨범",
             "originallink": "https://www.news-a.kr/1", "pubDate": NOW},
            {"title": "가상밴드 타이틀곡 화제", "description": "공개 직후 차트 진입",
             "originallink": "https://news-b.com/2", "pubDate": NOW},
            {"title": "같은 언론사 중복", "description": "", "originallink": "https://news-b.com/3", "pubDate": NOW},
            {"title": "오래된 기사", "description": "", "originallink": "https://old.com/1",
             "pubDate": "Mon, 01 Jan 2024 10:00:00 +0900"},
        ]})
    if "raw.example" in url:
        return Resp(headers={"content-type": "image/jpeg"})
    if "content_publishing_limit" in url:
        return Resp(body={"data": [{"quota_usage": 3, "config": {"quota_total": 100}}]})
    if "graph.instagram.com" in url:
        fields = kw["params"].get("fields")
        return Resp(body={"status_code": "FINISHED"} if fields == "status_code" else {"permalink": "https://instagram.com/p/x"})
    raise AssertionError("예상 못 한 GET: " + url)


ig_posts = []
image_calls = []


def fake_post(url, **kw):
    if "anthropic.com" in url:
        body = kw["json"]
        assert body["tool_choice"]["name"] == "submit_cardnews" and "후보 0: 가상밴드 컴백  [실시간 검색어 | 출처: 구글 트렌드, X 트렌드 | 검색 20000+]" in body["messages"][0]["content"]
        return Resp(body={"content": [{"type": "tool_use", "input": json.loads(json.dumps(fake_post.plan))}]})
    if "api.openai.com" in url:
        body = dict(kw.get("json") or kw["data"])
        body["_endpoint"] = url.rsplit("/", 1)[-1]
        body["_files"] = [name for name, _ in kw.get("files", [])]
        image_calls.append(body)
        if "scene 1" in body["prompt"]:
            return Resp(status=500)          # 한 장은 실패시켜 대체 디자인을 확인
        w, h = (int(x) for x in body["size"].split("x"))
        buf = io.BytesIO()
        Image.new("RGB", (w // 8, h // 8), (200, 80, 120)).save(buf, "PNG")
        return Resp(body={"data": [{"b64_json": base64.b64encode(buf.getvalue()).decode()}]})
    if "graph.instagram.com" in url:
        ig_posts.append((url.rsplit("/", 1)[-1], kw["data"]))
        return Resp(body={"id": f"id{len(ig_posts)}"})
    raise AssertionError("예상 못 한 POST: " + url)


fake_post.plan = GOOD_PLAN

with mock.patch("requests.get", fake_get), mock.patch("requests.post", fake_post), mock.patch("time.sleep"):
    # 1) 정상 흐름 (DRY_RUN)
    main.build()
    pending = state.load_pending()
    assert pending and len(pending["files"]) == 5, pending
    assert all((config.OUTPUT_DIR / f).exists() for f in pending["files"])
    assert "출처: news-a.kr, news-b.com" in pending["caption"] and "#가상밴드 #새앨범" in pending["caption"]
    assert "이미지는 AI로" not in pending["caption"]  # 이미지 키가 없으면 AI 이미지 문구도 없어야 함
    main.publish_pending()
    assert state.load_pending() is None and state.load_posted()[-1]["status"] == "dry_run" and not ig_posts
    print("1. 정상 흐름(DRY_RUN) 통과")

    # 1-1) 수집원 병합: 구글+X 같은 검색어는 하나로(출처 둘 다 기록), 오래된 검색어 제외, 같은 언론사는 한 번만
    cands, signals = sources.collect(set())
    assert len(cands) == 1 and cands[0]["origins"] == ["구글 트렌드", "X 트렌드"] and signals == {}, cands
    assert [n["domain"] for n in cands[0]["news"]] == ["news-a.kr", "news-b.com", "news-c.kr"], cands[0]["news"]
    assert cands[0]["news"][2]["title"] == '가상밴드, 3년 만에 "컴백"'
    # 1-2) 네이버 키 없이도 구글이 준 기사로 후보 구성
    config.NAVER_CLIENT_ID = ""
    cands, _ = sources.collect(set())
    assert [n["source"] for n in cands[0]["news"]] == ["뉴스C", "뉴스A"]
    config.NAVER_CLIENT_ID = "n"
    # 1-3) 구글이 실패해도 X로 계속, 둘 다 없으면 오류
    google_status = 503
    cands, _ = sources.collect(set())
    assert cands[0]["trend"] == "#가상밴드_컴백" and cands[0]["origins"] == ["X 트렌드"]
    config.X_BEARER_TOKEN = ""
    try:
        sources.collect(set())
        raise AssertionError("오류가 나야 합니다")
    except RuntimeError:
        pass
    config.X_BEARER_TOKEN, google_status = "x", 200
    print("1-1~3. 무료 수집원(구글 트렌드) 병합·대체 동작 통과")

    # 2) 같은 트렌드는 다시 다루지 않음
    main.build()
    assert state.load_pending() is None
    print("2. 중복 주제 제외 통과")

    # 3) 금지 키워드 → rejected 기록
    state.save_posted([])
    fake_post.plan = {**GOOD_PLAN, "cards": [{"title": "열애설 확산", "body": "본문"}] * 3}
    main.build()
    assert state.load_pending() is None and state.load_posted()[-1]["status"] == "rejected"
    print("3. 금지 키워드 차단 통과:", state.load_posted()[-1]["note"])

    # 4) 근거 언론사 1곳 → 차단
    state.save_posted([])
    fake_post.plan = {**GOOD_PLAN, "source_indexes": [0]}
    main.build()
    assert state.load_posted()[-1]["status"] == "rejected"
    print("4. 근거 부족 차단 통과:", state.load_posted()[-1]["note"])

    # 5) skip / 형식 오류
    state.save_posted([])
    fake_post.plan = {"decision": "skip", "skip_reason": "해당 분야 없음"}
    main.build()
    fake_post.plan = {"decision": "post", "candidate_index": 9}
    main.build()
    assert state.load_pending() is None and state.load_posted() == []
    print("5. skip·형식 오류 처리 통과")

    # 6) 실제 게시 흐름 (인스타 API 호출 순서와 파라미터)
    fake_post.plan = GOOD_PLAN
    config.DRY_RUN, config.PUBLIC_BASE_URL = False, "https://raw.example/media"
    main.build()
    main.publish_pending()
    kinds = [k for k, _ in ig_posts]
    assert kinds == ["media"] * 6 + ["media_publish"], kinds
    assert ig_posts[0][1]["image_url"].startswith("https://raw.example/media/") and ig_posts[0][1]["is_carousel_item"] == "true"
    assert "is_ai_generated" not in ig_posts[0][1]
    carousel = ig_posts[5][1]
    assert carousel["media_type"] == "CAROUSEL" and carousel["children"] == "id1,id2,id3,id4,id5" and carousel["is_ai_generated"] == "true"
    assert ig_posts[6][1]["creation_id"] == "id6"
    last = state.load_posted()[-1]
    assert last["status"] == "posted" and last["permalink"] and state.posted_count() == 1
    print("6. 게시 흐름 통과")

    # 6-1) 카드마다 AI 이미지: 표지 1장(세로) + 본문 3장(가로), 화풍 공통 적용, 한 장 실패해도 진행
    state.save_posted([])
    config.DRY_RUN, config.OPENAI_API_KEY, config.MASCOT = True, "sk-test", False
    main.build()
    assert len(image_calls) == 4, len(image_calls)
    sizes = sorted(c["size"] for c in image_calls)
    assert sizes == ["1024x1536", "1536x1024", "1536x1024", "1536x1024"], sizes
    assert all("Soft 3D clay render" in c["prompt"] and "no real persons" in c["prompt"] and c["quality"] == "medium"
               for c in image_calls)
    pending = state.load_pending()
    assert len(pending["files"]) == 5 and "이미지는 AI로 생성했습니다" in pending["caption"]
    # 표지만 이미지를 넣는 설정
    image_calls.clear()
    state.save_posted([])
    config.CARD_IMAGES = False
    main.build()
    assert len(image_calls) == 1 and image_calls[0]["size"] == "1024x1536"
    config.CARD_IMAGES, config.OPENAI_API_KEY, config.DRY_RUN = True, "", False
    state.clear_pending()
    state.save_posted([{"at": datetime.now(timezone.utc).isoformat(), "status": "posted", "topic": "t", "trend_norm": "x"}])
    print("6-1. 카드별 AI 이미지 생성 통과")

    # 6-2) 마스코트 모드
    from bot import images
    config.MASCOT, config.OPENAI_API_KEY, config.DRY_RUN = True, "sk-test", True
    #  (a) 기준 그림이 없으면 글 묘사만으로 생성
    image_calls.clear()
    state.save_posted([])
    main.build()
    assert len(image_calls) == 4 and all(c["_endpoint"] == "generations" for c in image_calls)
    assert all("seal-point Siamese cat" in c["prompt"] and "ringed in pale blue" in c["prompt"]
               and "cel shading" in c["prompt"] and "no real persons" in c["prompt"] for c in image_calls)
    assert not any("Soft 3D clay render" in c["prompt"] for c in image_calls)       # 마스코트 모드는 화풍 고정
    #  (b) 마스코트 만들기: 기준 그림 1장(글로) + 인사 그림 1장(기준 그림 참조)
    image_calls.clear()
    assert images.create_mascot() and config.MASCOT_FILE.exists() and config.MASCOT_WAVE_FILE.exists()
    assert [c["_endpoint"] for c in image_calls] == ["generations", "edits"]
    assert "four times" in image_calls[0]["prompt"] and image_calls[1]["_files"] == ["image[]"]
    #  (b-2) 모델 사진이 있으면 그 사진을 참조해서 기준 그림을 만듦
    image_calls.clear()
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 1100), (200, 180, 160)).save(config.MASCOT_SOURCE_FILE, "JPEG")
    assert images.create_mascot()
    assert [c["_endpoint"] for c in image_calls] == ["edits", "edits"] and image_calls[0]["_files"] == ["image[]"]
    assert "attached photo shows the real cat" in image_calls[0]["prompt"] and "four times" in image_calls[0]["prompt"]
    #  (c) 기준 그림이 있으면 매 카드가 그 그림을 참조 (같은 캐릭터 유지)
    image_calls.clear()
    state.save_posted([])
    main.build()
    assert len(image_calls) == 4 and all(c["_endpoint"] == "edits" and c["_files"] == ["image[]"] for c in image_calls)
    assert all("character reference sheet" in c["prompt"] and "input_fidelity" not in c for c in image_calls)
    assert sorted(c["size"] for c in image_calls) == ["1024x1536", "1536x1024", "1536x1024", "1536x1024"]
    pending = state.load_pending()
    assert len(pending["files"]) == 5 and all((config.OUTPUT_DIR / f).exists() for f in pending["files"])
    config.OPENAI_API_KEY, config.DRY_RUN = "", False
    state.clear_pending()
    state.save_posted([{"at": datetime.now(timezone.utc).isoformat(), "status": "posted", "topic": "t", "trend_norm": "x"}])
    print("6-2. 마스코트 모드(기준 그림 참조) 통과")

    # 7) 하루 한도
    config.MAX_POSTS_PER_DAY = 1
    state.save_posted([e for e in state.load_posted()])
    main.build()
    assert state.load_pending() is None
    print("7. 하루 게시 한도 통과")

# 쉬는 시간대 계산
with mock.patch.object(state, "datetime") as dt:
    for spec, hour, expected in [("1-6", 3, True), ("1-6", 7, False), ("23-6", 23, True), ("23-6", 2, True), ("23-6", 12, False)]:
        dt.now.return_value = datetime(2026, 1, 1, hour)
        config.QUIET_HOURS = spec
        assert state.in_quiet_hours() is expected, (spec, hour)
print("8. 쉬는 시간대 계산 통과")
print("\n모든 점검 통과")
