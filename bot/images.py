"""3단계: AI 이미지 생성. 표지 1장 + 본문 카드마다 1장.

마스코트 모드(기본)에서는 채널 캐릭터가 카드 내용을 설명·연기하는 그림을 만듭니다.
매번 같은 캐릭터로 보이도록, 미리 만들어 둔 기준 그림(assets/mascot.png)을 참조 이미지로 함께 보냅니다.

한 장이 실패해도 게시는 계속합니다. 실패한 카드는 이미지 없는 디자인으로 대체됩니다.
"""
from __future__ import annotations

import base64
import io
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

import config

API = "https://api.openai.com/v1/images"

# ── 마스코트 설정: 캐릭터를 바꾸고 싶으면 여기 두 문장을 고친 뒤 `python main.py mascot` 을 다시 실행 ──
MASCOT_DESCRIPTION = (
    "an original mascot character: a young seal-point Siamese cat with a round apple-shaped head, "
    "a fluffy cream-white chest and body, a dark chocolate-brown mask covering the whole face, "
    "dark brown ears, dark brown legs and a long dark brown tail, a small dark nose, "
    "and very large round eyes with huge dark pupils ringed in pale blue"
)
MASCOT_STYLE = (
    "Hand-drawn 2D anime film illustration: clean dark ink outlines, flat cel shading with one soft shadow tone and "
    "a gentle painted texture, fluffy fur drawn as pointed tufts, very large round glossy eyes with bright white "
    "highlights, warm cozy light, softly painted background in muted natural colors."
)
# 기준 그림(캐릭터 시트)에 쓰는 채색 방식 — 위 화풍과 맞춰 둡니다
MASCOT_SHEET_STYLE = ("Clean dark ink outlines, flat cel shading with one soft shadow tone, fluffy fur drawn as pointed tufts, "
                      "very large round glossy eyes with bright white highlights.")

# ── 공통 규칙 ──
RULES = (" No people's faces, no real persons, no celebrities, no existing cartoon or film characters, "
         "no text, no letters, no numbers, no logos, no watermarks.")
COVER_HINT = " Vertical composition; keep the main subject in the upper two thirds and leave the bottom third calm."
BODY_HINT = " Wide horizontal composition, one clear subject, uncluttered background."
DEFAULT_STYLE = "Editorial illustration, bold cinematic lighting, rich saturated colors."


def build_prompt(subject: str, style: str, cover: bool, with_reference: bool = False) -> str:
    subject = subject.strip().rstrip(".")
    hint = COVER_HINT if cover else BODY_HINT
    if not config.MASCOT:
        style = (style or DEFAULT_STYLE).strip().rstrip(".") + "."
        return f"{subject}. {style}{hint}{RULES}"
    if with_reference:
        lead = ("The attached image is the character reference sheet. Draw exactly the same character "
                "(same fur colors, markings, eye look and proportions) in a brand-new scene. "
                f"The character is {MASCOT_DESCRIPTION}.")
    else:
        lead = f"The main character is {MASCOT_DESCRIPTION}."
    return (f"{lead} Scene: {subject}. The cat is expressive and clearly the star of the picture, "
            f"and it is the only character. {MASCOT_STYLE}{hint}{RULES}")


def _decode(resp: requests.Response) -> Image.Image | None:
    if resp.status_code != 200:
        print(f"  (이미지 생성 실패 {resp.status_code}: {resp.text[:200]})")
        return None
    data = resp.json()["data"][0]
    raw = base64.b64decode(data["b64_json"]) if data.get("b64_json") else requests.get(data["url"], timeout=60).content
    return Image.open(io.BytesIO(raw)).convert("RGB")


def generate_image(prompt: str, size: str, reference: bytes | None = None, quality: str = "") -> Image.Image | None:
    """reference가 있으면 그 그림을 참조해서(같은 캐릭터로) 그리고, 없으면 글만으로 그립니다."""
    if not config.OPENAI_API_KEY:
        return None
    fields = {"model": config.IMAGE_MODEL, "prompt": prompt, "size": size, "n": 1}
    if quality or config.IMAGE_QUALITY:
        fields["quality"] = quality or config.IMAGE_QUALITY
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    try:
        if reference:
            resp = requests.post(f"{API}/edits", headers=headers, timeout=300,
                                 data={k: str(v) for k, v in fields.items()},
                                 files=[("image[]", ("mascot.png", reference, "image/png"))])
        else:
            resp = requests.post(f"{API}/generations", headers=headers, json=fields, timeout=300)
        return _decode(resp)
    except Exception as exc:  # 이미지가 없어도 게시는 계속합니다
        print(f"  (이미지 생성 오류: {exc})")
        return None


def _as_png(path, max_side: int = 1024) -> bytes:
    """그림을 참조용으로 줄여서(비용 절감) PNG 바이트로 돌려줍니다."""
    picture = Image.open(path).convert("RGB")
    picture.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    picture.save(buf, "PNG")
    return buf.getvalue()


def load_reference() -> bytes | None:
    """마스코트 기준 그림 (매 카드가 이 그림을 참조합니다)."""
    if not (config.MASCOT and config.MASCOT_FILE.exists()):
        return None
    return _as_png(config.MASCOT_FILE)


def generate_for_plan(plan: dict) -> tuple[Image.Image | None, list[Image.Image | None]]:
    """표지와 본문 카드 이미지를 동시에 생성합니다. 반환: (표지, [카드별 이미지 또는 None])"""
    cards = plan["cards"]
    if not config.OPENAI_API_KEY:
        print("  (OPENAI_API_KEY 없음 → 이미지 없이 기본 디자인으로 만듭니다)")
        return None, [None] * len(cards)

    reference = load_reference()
    if config.MASCOT and reference is None:
        print("  (마스코트 기준 그림이 없습니다 → 글 묘사만으로 그려서 카드마다 생김새가 조금씩 달라질 수 있습니다. "
              "`python main.py mascot` 으로 먼저 만들어 두세요)")
    style = plan.get("visual_style", "")
    ref = reference is not None
    jobs = [(build_prompt(plan["image_prompt"], style, True, ref), config.IMAGE_SIZE, reference)]
    card_slots = []
    if config.CARD_IMAGES:
        for index, card in enumerate(cards):
            if card.get("image_prompt", "").strip():
                jobs.append((build_prompt(card["image_prompt"], style, False, ref), config.IMAGE_SIZE_BODY, reference))
                card_slots.append(index)

    with ThreadPoolExecutor(max_workers=3) as pool:   # 동시에 3장까지 (API 속도 제한 고려)
        results = list(pool.map(lambda job: generate_image(*job), jobs))

    card_images: list[Image.Image | None] = [None] * len(cards)
    for slot, image in zip(card_slots, results[1:]):
        card_images[slot] = image
    print(f"  이미지 {sum(1 for r in results if r is not None)}/{len(jobs)}장 생성")
    return results[0], card_images


def create_mascot() -> bool:
    """마스코트 기준 그림과 인사하는 그림을 만들어 assets/ 에 저장합니다. (한 번만 실행, 마음에 안 들면 다시 실행)"""
    if not config.OPENAI_API_KEY:
        print("OPENAI_API_KEY가 필요합니다.")
        return False
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    sheet_prompt = (
        f"Character reference sheet of {MASCOT_DESCRIPTION}. Show the same cat four times, full body, evenly spaced "
        "in one row: standing front view, side view, sitting and smiling, and waving one paw cheerfully. "
        "Consistent design in every pose. Plain warm off-white paper background, no scenery. "
        "Hand-drawn 2D anime film character design. " + MASCOT_SHEET_STYLE + RULES
    )
    photo = _as_png(config.MASCOT_SOURCE_FILE) if config.MASCOT_SOURCE_FILE.exists() else None
    if photo:
        print(f"모델 사진({config.MASCOT_SOURCE_FILE.name})을 바탕으로 마스코트 기준 그림 생성 중…")
        sheet_prompt = ("The attached photo shows the real cat this character is modeled on. Turn this cat into a hand-drawn "
                        "character, keeping its real fur colors, face mask shape, eye look and body proportions. "
                        + sheet_prompt)
    else:
        print("마스코트 기준 그림 생성 중…")
    sheet = generate_image(sheet_prompt, "1536x1024", reference=photo, quality="high")
    if sheet is None:
        return False
    sheet.save(config.MASCOT_FILE, "PNG")
    print(f"  저장: {config.MASCOT_FILE}")

    print("인사하는 그림 생성 중…")
    wave_prompt = ("The attached image is the character reference sheet. Draw exactly the same character, alone, full body, "
                   "centered, waving one paw goodbye with a happy smile. Plain warm off-white paper background, no scenery. "
                   + MASCOT_SHEET_STYLE + RULES)
    wave = generate_image(wave_prompt, "1024x1024", reference=load_reference(), quality="high")
    if wave is not None:
        wave.save(config.MASCOT_WAVE_FILE, "PNG")
        print(f"  저장: {config.MASCOT_WAVE_FILE}")
    return True
