"""카드뉴스 자동화 실행 파일.

    python main.py sample    API 키 없이 샘플 카드만 렌더링 (디자인 확인용)
    python main.py sources   수집원별로 지금 무엇이 수집되는지 점검 (게시·AI 호출 없음)
    python main.py mascot    채널 마스코트 기준 그림 만들기 (처음 한 번, 마음에 안 들면 다시 실행)
    python main.py build     트렌드 수집 → 선별·원고 → 이미지 → 카드 렌더링
    python main.py publish   build가 만든 카드를 인스타그램에 게시 (DRY_RUN이면 기록만)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import config
from bot import editor, images, publish, render, safety, sources, state

KST = timezone(timedelta(hours=9))


def _set_output(name: str, value: str) -> None:
    """GitHub Actions의 다음 단계에 값을 넘깁니다."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def build() -> None:
    state.clear_pending()
    if state.in_quiet_hours():
        print(f"쉬는 시간대({config.QUIET_HOURS}시)입니다. 이번 회차는 건너뜁니다.")
        return
    if state.posted_count(24) >= config.MAX_POSTS_PER_DAY:
        print(f"최근 24시간 게시 수가 한도({config.MAX_POSTS_PER_DAY})에 도달했습니다.")
        return

    history = state.recent(config.DEDUPE_HOURS)
    exclude = {e["trend_norm"] for e in history if e.get("trend_norm")}
    candidates, signals = sources.collect(exclude)
    if not candidates:
        print("새로 다룰 후보가 없습니다.")
        return

    recent_topics = [e["topic"] for e in history if e.get("status") in ("posted", "dry_run")]
    plan = editor.plan_cardnews(candidates, recent_topics, signals)
    if plan["decision"] != "post":
        print(f"이번 회차 건너뜀: {plan['skip_reason']}")
        return

    candidate = candidates[plan["candidate_index"]]
    trend_norm = sources.normalize(candidate["trend"])
    print(f"선정: [{candidate['trend']}] {plan['topic']}")

    ok, reason = safety.check_plan(plan, candidate, config.MIN_SOURCES)
    if not ok:
        print(f"안전장치에 걸려 게시하지 않습니다: {reason}")
        state.record(plan["topic"], trend_norm, "rejected", note=reason)  # 같은 주제 재시도 방지
        return

    used = [i for i in plan["source_indexes"] if 0 <= i < len(candidate["news"])]
    source_names = list(dict.fromkeys(candidate["news"][i]["source"] for i in used))

    print("AI 이미지 생성 중…")
    cover, card_images = images.generate_for_plan(plan)
    has_ai_image = cover is not None or any(img is not None for img in card_images)

    run_id = datetime.now(KST).strftime("%Y%m%d-%H%M")
    out_dir = config.OUTPUT_DIR / run_id
    paths = render.render_cards(plan, source_names, cover, out_dir, card_images)
    caption = editor.build_caption(plan, source_names, has_ai_image=has_ai_image)
    (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    print(f"카드 {len(paths)}장 생성: {out_dir}")

    state.save_pending({
        "run_id": run_id,
        "topic": plan["topic"],
        "trend_norm": trend_norm,
        "caption": caption,
        "files": [f"{run_id}/{p.name}" for p in paths],
    })
    _set_output("has_post", "true")


def publish_pending() -> None:
    pending = state.load_pending()
    if not pending:
        print("게시할 카드가 없습니다.")
        return
    try:
        if config.DRY_RUN:
            print("DRY_RUN=true → 인스타그램에 올리지 않고 기록만 남깁니다.\n")
            print(pending["caption"])
            state.record(pending["topic"], pending["trend_norm"], "dry_run")
            return
        if not config.PUBLIC_BASE_URL:
            raise RuntimeError("PUBLIC_BASE_URL이 없습니다. 이미지가 공개 주소에 올라가 있어야 게시할 수 있습니다.")
        quota = publish.remaining_quota()
        if quota is not None and quota <= 0:
            raise RuntimeError("인스타그램 24시간 게시 한도를 모두 사용했습니다.")
        urls = [f"{config.PUBLIC_BASE_URL}/{f}" for f in pending["files"]]
        media_id = publish.publish_carousel(urls, pending["caption"])
        link = publish.permalink(media_id)
        state.record(pending["topic"], pending["trend_norm"], "posted", media_id, link)
        print(f"게시 완료: {link or media_id}")
    finally:
        state.clear_pending()


def check_sources() -> None:
    """각 수집원이 실제로 동작하는지 눈으로 확인합니다."""
    results, report = sources.gather()
    print("수집 결과:", *report, sep="\n")
    for name, items in results.items():
        print(f"\n[{sources.SOURCES[name][2]}]")
        for item in items[:10]:
            if isinstance(item, dict):
                extra = f"  ({item['volume']})" if item["volume"] else ""
                print(f"  · {item['name']}{extra}")
            else:
                print(f"  · {item}")


def make_mascot() -> None:
    if not images.create_mascot():
        sys.exit(1)
    print("완료. assets/ 폴더의 그림을 확인하고, 마음에 들지 않으면 다시 실행하세요.")


def sample() -> None:
    """실제 뉴스가 아닌 가상의 예시 원고로 카드 디자인만 확인합니다."""
    plan = {
        "topic": "[샘플] 가상의 드라마 '달빛 편의점' OST 역주행",
        "cover": {
            "kicker": "지금 뜨는 음악",
            "headline": "종영 드라마 OST가 갑자기 차트 1위?",
            "sub": "숏폼 챌린지 하나가 만든 역주행 (디자인 확인용 샘플)",
        },
        "cards": [
            {"title": "무슨 일이에요?", "body": "두 달 전에 끝난 가상의 드라마 '달빛 편의점' OST가 주말 사이 음원 차트 정상에 올랐더라고요. (디자인 확인용 예시예요)"},
            {"title": "왜 갑자기 떴을까", "body": "저도 궁금해서 찾아봤어요. 후렴구에 맞춰 편의점 간식을 소개하는 숏폼 챌린지가 퍼지면서 원곡을 찾는 사람이 크게 늘었대요."},
            {"title": "반응은 이래요", "body": "\"드라마는 안 봤는데 노래는 안다\"는 반응이 많아요. 정주행을 시작했다는 댓글도 이어지고 있어요."},
            {"title": "앞으로 볼 포인트", "body": "제작진이 스페셜 라이브 영상을 예고했어요. 역주행이 다음 주 차트까지 이어질지 같이 지켜봐요."},
        ],
    }
    # 실제 운영에서는 이 자리에 AI가 카드 내용에 맞춰 만든 이미지가 들어갑니다.
    if config.MASCOT:
        from bot import render_mascot
        cover = render_mascot.placeholder_cat(1024, 1536, 0, "샘플용 임시 그림")
        pictures = [render_mascot.placeholder_cat(1536, 1024, i, "샘플용 임시 그림") for i in range(1, len(plan["cards"]) + 1)]
        closing = render_mascot.placeholder_cat(1024, 1024, 1)
    else:
        closing = None
        cover = render.placeholder_picture("표지", "표지 AI 이미지 자리").resize((1024, 1536))
        pictures = [render.placeholder_picture(card["title"], f"{i}번 카드 AI 이미지 자리")
                    for i, card in enumerate(plan["cards"], start=1)]
    paths = render.render_cards(plan, ["example-news.kr", "sample-daily.com"], cover,
                                config.OUTPUT_DIR / "sample", pictures, closing)
    print("샘플 카드 생성:", *paths, sep="\n  ")


if __name__ == "__main__":
    commands = {"build": build, "publish": publish_pending, "sample": sample, "sources": check_sources, "mascot": make_mascot}
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in commands:
        print(__doc__)
        sys.exit(1)
    commands[command]()
