"""4단계: 원고와 배경 이미지를 1080x1350(4:5) 카드 이미지로 렌더링합니다."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H = 1080, 1350
MARGIN = 84
WHITE = (255, 255, 255)
INK = (14, 15, 20)
KST = timezone(timedelta(hours=9))

# (경로, ttc 안에서 한국어 글꼴 번호) — 위에서부터 있는 것을 씁니다.
_FONTS = {
    "black": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ],
    "bold": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ],
    "regular": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
        ("C:/Windows/Fonts/malgun.ttf", 0),
    ],
}
_font_cache: dict = {}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key in _font_cache:
        return _font_cache[key]
    override = os.environ.get(f"FONT_{weight.upper()}")
    candidates = ([(override, 0)] if override else []) + _FONTS[weight]
    for path, index in candidates:
        if Path(path).exists():
            try:
                _font_cache[key] = ImageFont.truetype(path, size, index=index)
            except OSError:
                _font_cache[key] = ImageFont.truetype(path, size)
            return _font_cache[key]
    raise RuntimeError(
        "한글 글꼴을 찾지 못했습니다. Ubuntu: sudo apt-get install fonts-noto-cjk, "
        "또는 FONT_BLACK / FONT_BOLD / FONT_REGULAR 환경변수에 ttf 경로를 지정하세요."
    )


# ── 텍스트 유틸 ─────────────────────────────────────────────────────────
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\U0000200D\U00002B00-\U00002BFF]"
)


def clean(text: str) -> str:
    """카드 글꼴에 없는 이모지를 제거합니다 (캡션에는 그대로 남습니다)."""
    return re.sub(r"\s+", " ", _EMOJI.sub("", text or "")).strip()


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """띄어쓰기 단위로 줄바꿈하고, 한 단어가 너무 길 때만 글자 단위로 자릅니다."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}".strip()
            if fnt.getlength(trial) <= max_width:
                line = trial
                continue
            if line:
                lines.append(line)
            line = ""
            for ch in word:  # 단어 하나가 한 줄보다 긴 경우
                if fnt.getlength(line + ch) > max_width:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
        if line:
            lines.append(line)
    return lines


def fit(text: str, weight: str, max_width: int, max_lines: int, start: int, minimum: int):
    """max_lines 안에 들어갈 때까지 글자 크기를 줄입니다. 반환: (글꼴, 줄 목록)"""
    size = start
    while True:
        fnt = font(weight, size)
        lines = wrap(text, fnt, max_width)
        if len(lines) <= max_lines or size <= minimum:
            if len(lines) > max_lines:  # 최소 크기에서도 넘치면 말줄임
                lines = lines[:max_lines]
                while lines[-1] and fnt.getlength(lines[-1] + "…") > max_width:
                    lines[-1] = lines[-1][:-1]
                lines[-1] += "…"
            return fnt, lines
        size -= 4


def draw_lines(draw, xy, lines, fnt, fill, line_height: float) -> int:
    """여러 줄을 그리고, 마지막 줄 아래 y좌표를 돌려줍니다."""
    x, y = xy
    step = int(fnt.size * line_height)
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += step
    return y


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# ── 배경 ────────────────────────────────────────────────────────────────
def cover_fit(img: Image.Image, width: int = W, height: int = H, focus_y: float = 0.5) -> Image.Image:
    """비율을 유지하며 지정한 크기에 꽉 차게 자릅니다. focus_y: 세로로 넘칠 때 어디를 남길지 (0=위, 1=아래)"""
    scale = max(width / img.width, height / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (resized.width - width) // 2, int((resized.height - height) * focus_y)
    return resized.crop((left, top, left + width, top + height))


def fallback_background(seed: str) -> Image.Image:
    """AI 이미지가 없을 때 쓰는 그라데이션 배경. 주제마다 색이 달라집니다."""
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    palettes = [
        ((255, 94, 98), (60, 20, 110)), ((36, 198, 220), (81, 74, 157)),
        ((255, 153, 102), (150, 30, 90)), ((17, 153, 142), (20, 40, 110)),
        ((252, 92, 125), (106, 60, 190)), ((247, 183, 51), (200, 60, 60)),
    ]
    top_color, bottom_color = palettes[digest[0] % len(palettes)]
    small = Image.new("RGB", (2, 2))
    small.putdata([top_color, tuple((a + b) // 2 for a, b in zip(top_color, bottom_color)),
                   tuple((a + b) // 2 for a, b in zip(top_color, bottom_color)), bottom_color])
    bg = small.resize((W, H), Image.BICUBIC)
    # 부드러운 빛 덩어리로 밋밋함을 덜어냅니다
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for i in range(3):
        cx = 120 + digest[1 + i] / 255 * (W - 240)
        cy = 100 + digest[4 + i] / 255 * (H * 0.55)
        radius = 220 + digest[7 + i] % 200
        gdraw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 255, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")


def shade(img: Image.Image, start: float, max_alpha: int) -> Image.Image:
    """아래로 갈수록 어두워지는 그라데이션을 덮어 글자가 읽히게 합니다."""
    mask = Image.new("L", (1, H))
    begin = int(H * start)
    mask.putdata([0 if y < begin else int(max_alpha * ((y - begin) / (H - begin)) ** 0.8) for y in range(H)])
    overlay = Image.new("RGB", (W, H), INK)
    return Image.composite(overlay, img, mask.resize((W, H)))


# ── 공통 요소 ───────────────────────────────────────────────────────────
def draw_chip(draw, x: int, y: int, text: str, accent, size: int = 32) -> None:
    fnt = font("black", size)
    pad_x, pad_y = int(size * 0.6), int(size * 0.3)
    width = int(fnt.getlength(text)) + pad_x * 2
    height = int(size * 1.45) + pad_y
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=accent)
    draw.text((x + width / 2, y + height / 2), text, font=fnt, fill=INK, anchor="mm")


def draw_right(draw, y: int, text: str, fnt, fill) -> None:
    draw.text((W - MARGIN, y), text, font=fnt, fill=fill, anchor="ra")


# ── 카드 종류별 렌더링 ──────────────────────────────────────────────────
def render_cover(bg: Image.Image, plan: dict, accent, has_ai_image: bool) -> Image.Image:
    img = shade(bg, start=0.22, max_alpha=242)
    # 상단도 살짝 어둡게 (칩과 날짜가 밝은 배경에 묻히지 않도록)
    top = Image.new("L", (1, H))
    top.putdata([int(110 * max(0, 1 - y / 260)) for y in range(H)])
    img = Image.composite(Image.new("RGB", (W, H), INK), img, top.resize((W, H)))
    draw = ImageDraw.Draw(img, "RGBA")

    draw_chip(draw, MARGIN, 76, config.CHANNEL_NAME, accent)
    now = datetime.now(KST)
    draw_right(draw, 88, f"{now.month}.{now.day:02d} {now.hour}시 기준", font("bold", 30), (255, 255, 255, 230))

    max_w = W - MARGIN * 2
    head_font, head_lines = fit(clean(plan["cover"]["headline"]), "black", max_w, 3, 104, 68)
    sub_font = font("regular", 40)
    sub_lines = wrap(clean(plan["cover"].get("sub", "")), sub_font, max_w)[:2]
    kicker_font = font("black", 36)

    # 아래에서부터 쌓아 올려 헤드라인 길이에 상관없이 하단 정렬
    footer_y = H - 118
    block_h = (int(kicker_font.size * 1.9) + int(head_font.size * 1.22) * len(head_lines) + 26
               + int(sub_font.size * 1.45) * len(sub_lines))
    y = footer_y - 56 - block_h

    draw.text((MARGIN, y), clean(plan["cover"].get("kicker", "")), font=kicker_font, fill=accent)
    y += int(kicker_font.size * 1.9)
    y = draw_lines(draw, (MARGIN, y), head_lines, head_font, WHITE, 1.22) + 26
    draw_lines(draw, (MARGIN, y), sub_lines, sub_font, (255, 255, 255, 222), 1.45)

    draw.line((MARGIN, footer_y, W - MARGIN, footer_y), fill=(255, 255, 255, 70), width=2)
    draw.text((MARGIN, footer_y + 26), "밀어서 보기  →", font=font("bold", 30), fill=WHITE)
    if has_ai_image:
        draw_right(draw, footer_y + 30, "AI 생성 이미지", font("regular", 26), (255, 255, 255, 170))
    return img


def body_background(bg: Image.Image) -> Image.Image:
    blurred = bg.filter(ImageFilter.GaussianBlur(48))
    return Image.blend(blurred, Image.new("RGB", (W, H), INK), 0.74)


def render_body(bg: Image.Image, card: dict, number: int, page: int, total: int, topic: str, accent) -> Image.Image:
    img = bg.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    max_w = W - MARGIN * 2

    draw_chip(draw, MARGIN, 76, config.CHANNEL_NAME, accent, size=28)
    draw_right(draw, 86, f"{page} / {total}", font("bold", 30), (255, 255, 255, 170))

    y = 250
    draw.text((MARGIN - 6, y), f"{number:02d}", font=font("black", 150), fill=accent)
    y += 218
    title_font, title_lines = fit(clean(card["title"]), "black", max_w, 2, 72, 52)
    y = draw_lines(draw, (MARGIN, y), title_lines, title_font, WHITE, 1.25) + 30
    draw.rounded_rectangle((MARGIN, y, MARGIN + 84, y + 8), radius=4, fill=accent)
    y += 56
    body_font, body_lines = fit(clean(card["body"]), "regular", max_w, 8, 46, 36)
    draw_lines(draw, (MARGIN, y), body_lines, body_font, (255, 255, 255, 235), 1.6)

    foot_font = font("regular", 28)
    foot = clean(topic)
    if foot_font.getlength(foot) > max_w:
        while foot and foot_font.getlength(foot + "…") > max_w:
            foot = foot[:-1]
        foot += "…"
    draw.line((MARGIN, H - 118, W - MARGIN, H - 118), fill=(255, 255, 255, 50), width=2)
    draw.text((MARGIN, H - 92), foot, font=foot_font, fill=(255, 255, 255, 140))
    return img


def fit_height(text: str, weight: str, max_width: int, max_height: int, start: int, minimum: int,
               line_height: float):
    """주어진 높이 안에 들어갈 때까지 글자 크기를 줄입니다. 반환: (글꼴, 줄 목록)"""
    size = start
    while True:
        fnt = font(weight, size)
        lines = wrap(text, fnt, max_width)
        step = int(fnt.size * line_height)
        if len(lines) * step <= max_height or size <= minimum:
            max_lines = max(1, max_height // step)
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                while lines[-1] and fnt.getlength(lines[-1] + "…") > max_width:
                    lines[-1] = lines[-1][:-1]
                lines[-1] += "…"
            return fnt, lines
        size -= 2


IMAGE_H = 660   # 본문 카드 위쪽 이미지 영역 높이


def render_body_with_image(bg: Image.Image, picture: Image.Image, card: dict, number: int, page: int,
                           total: int, topic: str, accent) -> Image.Image:
    """위에는 그 카드 내용의 AI 이미지, 아래에는 글이 들어가는 본문 카드."""
    img = bg.copy()
    img.paste(cover_fit(picture, W, IMAGE_H), (0, 0))
    # 이미지 아래쪽을 배경으로 자연스럽게 녹이고, 위쪽은 칩이 보이게 살짝 어둡게
    fade = Image.new("L", (1, H))
    fade.putdata([0 if y < IMAGE_H - 200 else min(255, int(255 * ((y - (IMAGE_H - 200)) / 200) ** 1.4))
                  for y in range(H)])
    img = Image.composite(bg, img, fade.resize((W, H)))
    top = Image.new("L", (1, H))
    top.putdata([int(120 * max(0, 1 - y / 220)) for y in range(H)])
    img = Image.composite(Image.new("RGB", (W, H), INK), img, top.resize((W, H)))

    draw = ImageDraw.Draw(img, "RGBA")
    max_w = W - MARGIN * 2
    footer_y = H - 118

    draw_chip(draw, MARGIN, 76, config.CHANNEL_NAME, accent, size=28)
    draw_right(draw, 86, f"{page} / {total}", font("bold", 30), (255, 255, 255, 230))
    draw_right(draw, IMAGE_H - 96, "AI 생성 이미지", font("regular", 24), (255, 255, 255, 150))

    y = IMAGE_H - 96
    draw.text((MARGIN - 4, y), f"{number:02d}", font=font("black", 104), fill=accent)
    y += 150
    title_font, title_lines = fit(clean(card["title"]), "black", max_w, 2, 66, 50)
    y = draw_lines(draw, (MARGIN, y), title_lines, title_font, WHITE, 1.25) + 24
    draw.rounded_rectangle((MARGIN, y, MARGIN + 84, y + 8), radius=4, fill=accent)
    y += 44
    body_font, body_lines = fit_height(clean(card["body"]), "regular", max_w, footer_y - 28 - y, 44, 32, 1.55)
    draw_lines(draw, (MARGIN, y), body_lines, body_font, (255, 255, 255, 235), 1.55)

    foot_font = font("regular", 28)
    foot = clean(topic)
    if foot_font.getlength(foot) > max_w:
        while foot and foot_font.getlength(foot + "…") > max_w:
            foot = foot[:-1]
        foot += "…"
    draw.line((MARGIN, footer_y, W - MARGIN, footer_y), fill=(255, 255, 255, 50), width=2)
    draw.text((MARGIN, H - 92), foot, font=foot_font, fill=(255, 255, 255, 140))
    return img


def placeholder_picture(seed: str, label: str = "AI 이미지가 들어갈 자리") -> Image.Image:
    """샘플용 가짜 이미지 (실제 운영에서는 AI가 만든 이미지가 들어갑니다)."""
    picture = fallback_background(seed).resize((1536, 1920)).crop((0, 300, 1536, 1324))
    draw = ImageDraw.Draw(picture, "RGBA")
    draw.text((768, 470), label, font=font("bold", 56), fill=(255, 255, 255, 215), anchor="mm")
    return picture


def render_closing(bg: Image.Image, sources: list[str], page: int, total: int, accent,
                   has_ai_image: bool) -> Image.Image:
    img = bg.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    max_w = W - MARGIN * 2

    draw_chip(draw, MARGIN, 76, config.CHANNEL_NAME, accent, size=28)
    draw_right(draw, 86, f"{page} / {total}", font("bold", 30), (255, 255, 255, 170))

    y = 270
    y = draw_lines(draw, (MARGIN, y), ["매시간, 지금 뜨는", "이야기만 골라드려요"], font("black", 78), WHITE, 1.25) + 34
    follow = "팔로우하고 다음 소식 받아보기"
    if config.CHANNEL_HANDLE:
        follow = f"{config.CHANNEL_HANDLE} 팔로우하고 다음 소식 받아보기"
    follow_font, follow_lines = fit(follow, "bold", max_w, 2, 40, 30)
    y = draw_lines(draw, (MARGIN, y), follow_lines, follow_font, accent, 1.4) + 90

    draw.text((MARGIN, y), "출처", font=font("black", 32), fill=(255, 255, 255, 235))
    y += 60
    source_font = font("regular", 32)
    source_lines = wrap("  ·  ".join(sources) or "각 언론사 보도", source_font, max_w)[:4]
    y = draw_lines(draw, (MARGIN, y), source_lines, source_font, (255, 255, 255, 190), 1.5)

    note_font = font("regular", 28)
    ai_note = "이 콘텐츠는 AI가 공개된 보도를 요약해 만들었" + ("고, 이미지는 AI로 생성했습니다. " if has_ai_image else "습니다. ")
    notes = wrap(ai_note + "자세한 내용은 각 언론사 기사를 확인해 주세요.", note_font, max_w)
    note_y = H - 118 - int(note_font.size * 1.55) * len(notes) - 30
    draw_lines(draw, (MARGIN, note_y), notes, note_font, (255, 255, 255, 150), 1.55)
    draw.line((MARGIN, H - 118, W - MARGIN, H - 118), fill=(255, 255, 255, 50), width=2)
    draw.text((MARGIN, H - 92), "저장해두고 나중에 다시 보기", font=font("bold", 28), fill=(255, 255, 255, 170))
    return img


# ── 진입점 ──────────────────────────────────────────────────────────────
def render_cards(plan: dict, sources: list[str], cover_image: Image.Image | None, out_dir: Path,
                 card_images: list[Image.Image | None] | None = None,
                 closing_image: Image.Image | None = None) -> list[Path]:
    """표지 + 본문 + 마무리 카드를 JPEG로 저장하고 경로 목록을 돌려줍니다.

    card_images[i]가 있으면 i번째 본문 카드 위쪽에 그 이미지를 넣고, 없으면 글만 있는 디자인으로 만듭니다.
    """
    card_images = list(card_images or []) + [None] * len(plan["cards"])
    has_ai_image = cover_image is not None or any(p is not None for p in card_images)
    if config.MASCOT:   # 마스코트 모드: 종이 배경 + 말풍선 디자인
        from bot import render_mascot
        out_dir.mkdir(parents=True, exist_ok=True)
        return _save(render_mascot.render_all(plan, sources, cover_image, card_images, closing_image), out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    accent = hex_rgb(config.ACCENT_COLOR)
    base = cover_fit(cover_image) if cover_image else fallback_background(plan["topic"])
    body_bg = body_background(base)

    total = len(plan["cards"]) + 2
    cards = [render_cover(base, plan, accent, has_ai_image=cover_image is not None)]
    for i, card in enumerate(plan["cards"], start=1):
        picture = card_images[i - 1]
        if picture is not None:
            cards.append(render_body_with_image(body_bg, picture, card, i, i + 1, total, plan["topic"], accent))
        else:
            cards.append(render_body(body_bg, card, i, i + 1, total, plan["topic"], accent))
    cards.append(render_closing(body_bg, sources, total, total, accent, has_ai_image=has_ai_image))

    return _save(cards, out_dir)


def _save(cards: list[Image.Image], out_dir: Path) -> list[Path]:
    paths = []
    for i, card in enumerate(cards, start=1):
        path = out_dir / f"{i:02d}.jpg"
        card.convert("RGB").save(path, "JPEG", quality=90, optimize=True)  # 인스타 API는 JPEG만 받습니다
        paths.append(path)
    return paths
