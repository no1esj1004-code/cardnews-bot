"""2단계: Claude가 후보 중 하나를 고르고(또는 이번 회차를 건너뛰고) 카드뉴스 원고를 씁니다."""
from __future__ import annotations

import json

import requests

import config

SYSTEM_PROMPT = """당신은 한국 인스타그램 카드뉴스 채널 '{channel}'의 에디터입니다.
매시간 여러 곳(구글·다음·줌·시그널의 실시간 검색어, 구글 뉴스 연예 섹션 등)에서 모은 후보와 관련 뉴스 요약을 받아, 카드뉴스로 만들 주제 하나를 고르고 원고를 씁니다.
사람의 검수 없이 그대로 게시되므로, 조금이라도 애매하면 게시하지 않는 쪽(skip)을 선택하세요.

[다루는 범위]
{scope} 분야만 다룹니다. 예: 드라마·영화·예능·음악·아이돌 활동 소식, 공연·전시, 유행하는 밈과 챌린지, 화제의 콘텐츠.

[고르는 기준]
- 같은 이야기가 여러 후보나 여러 출처에 걸쳐 나타나면 그만큼 화제인 것이니 우선합니다. 이때는 뉴스 근거가 가장 충실한 후보의 번호를 고릅니다.
- 후보에 붙은 '반응'(네이버 카페·블로그에 방금 올라온 글)은 사람들이 이 주제를 어떻게 이야기하는지 보여줍니다. 반응이 활발한 후보를 우선하고, "반응" 카드에서 전반적인 분위기를 자기 말로 전하는 데 씁니다. 특정 글을 인용하거나 글쓴이·카페 이름을 밝히지 않고, 거기 적힌 주장을 사실로 옮기지 않습니다.
- '참고 신호'(유튜브 인기 동영상, 커뮤니티 인기글 제목)는 무엇이 화제인지 가늠하는 용도로만 씁니다. 확인되지 않은 내용이므로 원고에는 절대 옮기지 않고, 고른 후보의 뉴스에 있는 사실만 씁니다.

[절대 다루지 않는 것 → 해당 후보는 제외, 남는 후보가 없으면 skip]
- 정치·선거·시사 갈등, 사건·사고·재난, 범죄·수사·소송
- 사망·부고, 질병·건강 문제
- 열애·결별·이혼 등 사생활, 확인되지 않은 루머·폭로·논란·의혹 제기
- 미성년자의 신상이나 사생활이 중심인 이야기
- 특정인을 조롱·비난하는 내용, 팬덤 간 싸움
- 뉴스 요약만으로는 무슨 일인지 분명하지 않은 것, 서로 다른 언론사 {min_sources}곳 이상에서 확인되지 않는 것

[원고 원칙]
- 제공된 뉴스 요약에 있는 사실만 씁니다. 추측·과장·없는 숫자·없는 인용을 만들지 않습니다.
- 기사 제목만 제공된 후보는 제목에서 확인되는 사실만으로 쓸 수 있을 때만 고릅니다. 제목만으로 내용이 불분명하면 제외합니다.
- 기사 문장을 그대로 옮기지 말고 자기 말로 짧게 다시 씁니다.
{voice_rules}
- 표지 헤드라인은 22자 이내, 카드 제목은 18자 이내, 카드 본문은 90자 이내 2~3문장.
- 본문 카드는 3~4장: 무슨 일인지 → 왜 화제인지 → 반응/맥락 → (선택) 앞으로 볼 포인트.
- 캡션은 2~3문장 요약 + 댓글을 유도하는 가벼운 질문 하나. 해시태그는 5~8개.

{image_rules}

[이미 최근에 다룬 주제]
아래 목록과 같은 이야기는 키워드가 달라도 다시 고르지 않습니다.
{recent}
"""

VOICE_DEFAULT = "- 말투는 친근한 해요체, 과한 유행어·낚시성 제목 금지. 이모지는 캡션에서만 1~2개."

VOICE_MASCOT = """- 이 채널은 마스코트인 샴고양이가 독자에게 소식을 설명해 주는 형식입니다. 카드 본문은 고양이가 옆에서 말해 주듯 친근한 해요체로 씁니다.
  (예: "이번 주에 다들 이 노래 얘기만 하더라고요.", "저도 궁금해서 찾아봤어요.")
- 고양이의 감상은 가볍게 한두 마디만 넣고, 사실 전달이 중심입니다. 없는 사실을 귀엽게 지어내지 않습니다.
- '~냥', '~다옹' 같은 말끝 장난, 과한 유행어, 낚시성 제목은 쓰지 않습니다. 이모지는 캡션에서만 1~2개."""

IMAGE_RULES_DEFAULT = """[이미지 프롬프트 규칙]
- 표지에 1장(image_prompt), 본문 카드마다 1장씩(cards[].image_prompt) 이미지가 들어갑니다. 각각 영어 한두 문장으로 묘사합니다.
- 카드 이미지는 그 카드가 말하는 내용을 보여줘야 합니다. 카드마다 서로 다른 장면으로, 같은 그림의 반복이 되지 않게 합니다.
  (예: "무슨 일?" → 새 앨범이 놓인 턴테이블 / "왜 화제?" → 불빛으로 가득 찬 공연장 객석 / "반응" → 알림이 쏟아지는 스마트폰 화면)
- visual_style에는 이 게시물의 모든 이미지에 공통으로 적용할 화풍을 영어 한 문장으로 적습니다. 주제 분위기에 맞게 고르되 한 게시물 안에서는 통일합니다.
  (예: "Soft 3D clay render with pastel studio lighting" / "Retro risograph print with grainy texture and limited colors")
- 실존 인물(연예인 포함)의 얼굴·모습·이름, 실제 작품의 캐릭터·포스터·로고·상표는 절대 묘사하지 않습니다.
- 대신 주제를 나타내는 사물·공간·빛·색으로 표현합니다. 사람이 필요하면 얼굴이 보이지 않는 뒷모습이나 실루엣, 손만 등장시킵니다.
- 글자·숫자가 들어가지 않는 이미지여야 합니다."""

IMAGE_RULES_MASCOT = """[이미지 프롬프트 규칙]
- 표지에 1장(image_prompt), 본문 카드마다 1장씩(cards[].image_prompt) 그림이 들어갑니다. 모든 그림의 주인공은 채널 마스코트인 샴고양이입니다.
- 각 프롬프트는 "The cat ..."으로 시작하는 영어 한두 문장으로, 고양이가 그 카드 내용을 설명하거나 몸으로 보여주는 장면을 묘사합니다. 무엇을 하고 있는지, 어떤 표정인지, 어떤 소품과 장소인지를 적습니다.
  (예: "무슨 일?" → The cat wearing oversized headphones, eyes wide with surprise, next to a spinning record player in a cozy room
       "왜 화제?" → The cat excitedly pointing a paw at a tall stack of vinyl records that reaches the ceiling
       "반응" → The cat holding a smartphone overflowing with floating heart bubbles, looking delighted
       "볼 포인트" → The cat peeking through binoculars from a hilltop at a tiny festival stage far away)
- 카드마다 서로 다른 동작·소품·장소로, 같은 그림의 반복이 되지 않게 합니다. 표지는 주제를 한눈에 보여주는 가장 상징적인 장면으로 합니다.
- 고양이의 생김새(털 색, 눈 색 등)와 화풍은 적지 않습니다. 시스템이 항상 같은 묘사를 붙입니다. visual_style은 비워 둡니다.
- 고양이 외의 캐릭터는 등장시키지 않습니다. 실존 인물(연예인 포함)의 얼굴·모습·이름, 실제 작품의 캐릭터·장면·포스터·로고·상표는 절대 묘사하지 않습니다.
  사람이 꼭 필요하면 멀리 있는 작은 실루엣 정도로만 표현합니다. 주제는 소품과 장소로 드러냅니다.
- 글자·숫자가 들어가지 않는 그림이어야 합니다."""

TOOL = {
    "name": "submit_cardnews",
    "description": "이번 회차의 결정(게시 또는 건너뛰기)과 카드뉴스 원고를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["post", "skip"]},
            "skip_reason": {"type": "string", "description": "skip일 때 이유 한 줄"},
            "candidate_index": {"type": "integer", "description": "고른 후보의 번호 (0부터)"},
            "topic": {"type": "string", "description": "주제를 한 줄로 (예: '○○ 3년 만의 정규 앨범 발매')"},
            "cover": {
                "type": "object",
                "properties": {
                    "kicker": {"type": "string", "description": "표지 상단 짧은 라벨 (예: '지금 뜨는 음악')"},
                    "headline": {"type": "string"},
                    "sub": {"type": "string", "description": "헤드라인 아래 한 줄 설명 (30자 이내)"},
                },
                "required": ["kicker", "headline", "sub"],
            },
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "image_prompt": {"type": "string", "description": "이 카드 내용을 보여주는 그림 묘사 (영어, 규칙 참고)"},
                    },
                    "required": ["title", "body", "image_prompt"],
                },
            },
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "image_prompt": {"type": "string", "description": "표지 이미지 묘사 (영어)"},
            "visual_style": {"type": "string", "description": "모든 이미지에 공통으로 쓸 화풍 (영어 한 문장)"},
            "source_indexes": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "원고의 근거로 쓴 뉴스 번호들 (고른 후보의 news 배열 기준, 0부터)",
            },
        },
        "required": ["decision"],
    },
}


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates):
        kind = "뉴스 묶음" if c.get("kind") == "headline" else "실시간 검색어"
        meta = [kind, "출처: " + ", ".join(c["origins"])] + ([c["volume"]] if c.get("volume") else [])
        lines.append(f"## 후보 {i}: {c['trend']}  [{' | '.join(meta)}]")
        for j, n in enumerate(c["news"]):
            meta = ", ".join(x for x in (n["source"], n["published"]) if x)
            body = f"{n['title']} — {n['summary']}" if n["summary"] else f"{n['title']} (제목만 제공됨)"
            lines.append(f"- 뉴스 {j} [{meta}] {body}")
        for b in c.get("buzz", []):
            lines.append(f"- 반응 {b}")
        for t in c.get("threads", []):
            lines.append(f"- Threads 반응: {t}")
        lines.append("")
    return "\n".join(lines)


def _format_signals(signals: dict[str, list[str]]) -> str:
    if not signals:
        return ""
    lines = ["", "# 참고 신호 (화제성 판단용. 확인되지 않은 내용이므로 원고의 근거로 쓰지 않습니다)"]
    for name, titles in signals.items():
        lines.append(f"## {name}")
        lines += [f"- {t}" for t in titles[:25]]
    return "\n".join(lines)


def plan_cardnews(candidates: list[dict], recent_topics: list[str],
                  signals: dict[str, list[str]] | None = None) -> dict:
    """Claude에게 선별과 원고 작성을 맡깁니다. 반환: submit_cardnews 입력 dict"""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    system = SYSTEM_PROMPT.format(
        channel=config.CHANNEL_NAME,
        scope=config.TOPIC_SCOPE,
        min_sources=config.MIN_SOURCES,
        voice_rules=VOICE_MASCOT if config.MASCOT else VOICE_DEFAULT,
        image_rules=IMAGE_RULES_MASCOT if config.MASCOT else IMAGE_RULES_DEFAULT,
        recent="\n".join(f"- {t}" for t in recent_topics) or "- (없음)",
    )
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": config.CLAUDE_MODEL,
            "max_tokens": 3000,
            "system": system,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": "submit_cardnews"},
            "messages": [{
                "role": "user",
                "content": "이번 시간의 후보입니다. 기준에 맞는 주제가 있으면 하나만 골라 원고를 쓰고, "
                           "없으면 skip 하세요.\n\n" + _format_candidates(candidates) + _format_signals(signals or {}),
            }],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Claude API 오류 ({resp.status_code}): {resp.text[:400]}")
    for block in resp.json().get("content", []):
        if block.get("type") == "tool_use":
            return validate_plan(block["input"], len(candidates))
    raise RuntimeError("Claude 응답에 원고가 없습니다: " + json.dumps(resp.json(), ensure_ascii=False)[:400])


def validate_plan(plan: dict, candidate_count: int) -> dict:
    """형식이 어긋난 원고는 skip으로 바꿉니다 (잘못된 카드가 올라가는 것보다 한 회 쉬는 편이 낫습니다)."""
    if plan.get("decision") != "post":
        return {"decision": "skip", "skip_reason": plan.get("skip_reason") or "기준에 맞는 주제 없음"}
    try:
        index = int(plan["candidate_index"])
        assert 0 <= index < candidate_count
        cover = plan["cover"]
        assert cover["headline"].strip() and plan["topic"].strip() and plan["caption"].strip()
        assert plan["image_prompt"].strip()
        cards = [c for c in plan["cards"] if c["title"].strip() and c["body"].strip()]
        assert cards
    except (KeyError, TypeError, ValueError, AssertionError):
        return {"decision": "skip", "skip_reason": "원고 형식 오류"}
    plan["candidate_index"] = index
    plan["cards"] = cards
    plan["cover"].setdefault("kicker", "지금 뜨는 이슈")
    plan["cover"].setdefault("sub", "")
    plan["visual_style"] = str(plan.get("visual_style") or "").strip()
    for card in cards:
        card["image_prompt"] = str(card.get("image_prompt") or "").strip()
    plan["hashtags"] = [h.lstrip("#").replace(" ", "") for h in plan.get("hashtags", []) if h.strip()][:8]
    plan["source_indexes"] = [int(i) for i in plan.get("source_indexes", []) if isinstance(i, (int, float))]
    return plan


def build_caption(plan: dict, sources: list[str], has_ai_image: bool = True) -> str:
    """인스타 캡션 조립: 요약 + 출처 + AI 고지 + 해시태그"""
    parts = [plan["caption"].strip(), ""]
    if sources:
        parts.append("출처: " + ", ".join(sources))
    parts.append("이 게시물은 AI가 공개된 보도를 요약해 만들었" + ("고, 이미지는 AI로 생성했습니다." if has_ai_image else "습니다."))
    if plan["hashtags"]:
        parts += ["", " ".join("#" + h for h in plan["hashtags"])]
    return "\n".join(parts)[:2200]
