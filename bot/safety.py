"""완전 자동 게시를 위한 안전장치. AI의 판단과 별개로, 코드에서 한 번 더 걸러냅니다."""
from __future__ import annotations

# 이 단어가 주제·카드 문구·캡션 어디든 들어가면 그 회차는 게시하지 않습니다.
# 채널 성격에 맞게 자유롭게 추가/삭제하세요.
BLOCKED_KEYWORDS = [
    # 사망·사고·건강
    "사망", "별세", "숨진", "숨져", "부고", "극단적", "자살", "투병", "암 진단", "참사", "추락사",
    # 범죄·수사·소송
    "성범죄", "성폭행", "성추행", "성희롱", "불법촬영", "마약", "음주운전", "뺑소니", "폭행",
    "구속", "기소", "체포", "압수수색", "혐의", "피의자", "피해자", "고소", "고발", "소송", "학폭",
    # 사생활 루머
    "열애", "결별", "이혼", "불륜", "외도", "임신", "사생활", "루머", "찌라시", "지라시", "폭로",
    # 정치
    "대통령", "국회", "탄핵", "총선", "대선", "여당", "야당", "국민의힘", "더불어민주당", "의원",
]


def find_blocked(*texts: str) -> list[str]:
    joined = " ".join(t for t in texts if t)
    return sorted({word for word in BLOCKED_KEYWORDS if word in joined})


def check_plan(plan: dict, candidate: dict, min_sources: int) -> tuple[bool, str]:
    """AI가 만든 카드 기획을 게시해도 되는지 판정. (통과 여부, 사유)"""
    texts = [plan.get("topic", ""), plan["cover"]["headline"], plan["cover"].get("sub", ""),
             plan.get("caption", "")]
    for card in plan["cards"]:
        texts += [card["title"], card["body"]]
    # 원본 기사 제목도 함께 검사: 민감한 사건을 순화해서 다루는 경우를 막습니다.
    texts += [n["title"] for n in candidate["news"]]

    blocked = find_blocked(*texts)
    if blocked:
        return False, f"금지 키워드 포함: {', '.join(blocked)}"

    used = {i for i in plan.get("source_indexes", []) if 0 <= i < len(candidate["news"])}
    sources = {candidate["news"][i].get("domain") or candidate["news"][i]["source"] for i in used}
    if len(sources) < min_sources:
        return False, f"근거 언론사 부족 ({len(sources)}곳 < {min_sources}곳)"

    if not (3 <= len(plan["cards"]) <= 5):
        return False, f"본문 카드 수 이상 ({len(plan['cards'])}장)"
    return True, "ok"
