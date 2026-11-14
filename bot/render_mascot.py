"""마스코트 모드 카드 디자인: 종이 질감 배경 + 그림 + 말풍선.

위쪽 그림 속 캐릭터가 아래 말풍선으로 설명해 주는 구성입니다. 글자는 AI 그림에 넣지 않고
여기서 직접 그려 넣기 때문에 한글이 깨지지 않습니다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

import config
from bot.render import (H, KST, W, clean, cover_fit, draw_lines, fallback_background, fit, fit_height, font,
                        hex_rgb, wrap)

PAPER = (251, 246, 234)
BROWN = (46, 34, 26)
WHITE = (255, 255, 255)
M = 72            # 바깥 여백
PICTURE_H = 640   # 본문 카드 위쪽 그림 높이


def _soft(alpha: int) -> tuple[int, int, int, int]:
    return (*BROWN, alpha)


def _pill(draw, x: int, y: int, text: str, fnt, fill, text_fill, anchor_right: bool = False) -> None:
    pad_x, height = int(fnt.size * 0.62), int(fnt.size * 1.75)
    width = int(fnt.getlength(text)) + pad_x * 2
    if anchor_right:
        x -= width
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=fill)
    draw.text((x + width / 2, y + height / 2), text, font=fnt, fill=text_fill, anchor="mm")


def _header(draw, accent, right_text: str) -> None:
    _pill(draw, M, 60, config.CHANNEL_NAME, font("black", 30), accent, WHITE)
    _pill(draw, W - M, 62, right_text, font("bold", 26), PAPER, BROWN, anchor_right=True)


def _ellipsize(text: str, fnt, max_width: int) -> str:
    if fnt.getlength(text) <= max_width:
        return text
    while text and fnt.getlength(text + "…") > max_width:
        text = text[:-1]
    return text + "…"


# ── 표지 ────────────────────────────────────────────────────────────────
def render_cover(picture: Image.Image | None, plan: dict, accent) -> Image.Image:
    max_w = W - M * 2
    kicker_font = font("black", 34)
    head_font, head_lines = fit(clean(plan["cover"]["headline"]), "black", max_w, 3, 92, 60)
    sub_font = font("regular", 38)
    sub_lines = wrap(clean(plan["cover"].get("sub", "")), sub_font, max_w)[:2]

    head_h = int(head_font.size * 1.22) * len(head_lines)
    sub_h = int(sub_font.size * 1.45) * len(sub_lines)
    panel_h = 58 + int(kicker_font.size * 1.75) + head_h + 18 + sub_h + 36 + 96
    panel_top = H - panel_h

    source = picture if picture is not None else fallback_background(plan["topic"])
    img = Image.new("RGB", (W, H), PAPER)
    img.paste(cover_fit(source, W, panel_top + 64, focus_y=0.2), (0, 0))   # 그림 위쪽(주인공)을 살립니다
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rounded_rectangle((0, panel_top, W, H + 80), radius=60, fill=PAPER)   # 그림 위로 올라오는 종이 패널

    now = datetime.now(KST)
    _header(draw, accent, f"{now.month}.{now.day:02d} {now.hour}시 기준")

    y = panel_top + 58
    draw.text((M, y), clean(plan["cover"].get("kicker", "")), font=kicker_font, fill=accent)
    y += int(kicker_font.size * 1.75)
    y = draw_lines(draw, (M, y), head_lines, head_font, BROWN, 1.22) + 18
    draw_lines(draw, (M, y), sub_lines, sub_font, _soft(200), 1.45)

    footer_y = H - 96
    draw.line((M, footer_y, W - M, footer_y), fill=_soft(40), width=2)
    draw.text((M, footer_y + 26), "밀어서 보기  →", font=font("bold", 30), fill=BROWN)
    if picture is not None:
        draw.text((W - M, footer_y + 30), "AI 생성 이미지", font=font("regular", 24), fill=_soft(130), anchor="ra")
    return img


# ── 본문: 그림 + 말풍선 ─────────────────────────────────────────────────
def render_body(picture: Image.Image | None, card: dict, number: int, page: int, total: int,
                topic: str, accent) -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    if picture is not None:
        img.paste(cover_fit(picture, W, PICTURE_H), (0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    _header(draw, accent, f"{page} / {total}")

    left, right = 48, W - 48
    top = PICTURE_H - 70 if picture is not None else 190
    bottom = H - 150
    # 말풍선: 포인트 색 그림자 → 흰 바탕 + 갈색 테두리
    draw.rounded_rectangle((left + 12, top + 12, right + 12, bottom + 12), radius=46, fill=accent)
    draw.rounded_rectangle((left, top, right, bottom), radius=46, fill=WHITE, outline=BROWN, width=5)
    if picture is not None:   # 위쪽 그림 속 캐릭터를 가리키는 꼬리
        tip, a, b = (178, top - 54), (150, top + 3), (236, top + 3)
        draw.polygon([tip, a, b], fill=WHITE)
        draw.line([a, tip, b], fill=BROWN, width=5, joint="curve")
        draw.line([(a[0] + 4, top + 2), (b[0] - 4, top + 2)], fill=WHITE, width=7)

    pad = 54
    x, max_w = left + pad, (right - left) - pad * 2
    y = top + 44
    draw.text((x, y), f"{number:02d}", font=font("black", 50), fill=accent)
    y += 74
    title_font, title_lines = fit(clean(card["title"]), "black", max_w, 2, 62, 46)
    y = draw_lines(draw, (x, y), title_lines, title_font, BROWN, 1.25) + 22
    draw.rounded_rectangle((x, y, x + 76, y + 8), radius=4, fill=accent)
    y += 40
    body_font, body_lines = fit_height(clean(card["body"]), "regular", max_w, bottom - 44 - y, 42, 30, 1.58)
    draw_lines(draw, (x, y), body_lines, body_font, _soft(235), 1.58)

    foot_font = font("regular", 26)
    note_w = 190 if picture is not None else 0
    draw.text((M, H - 100), _ellipsize(clean(topic), foot_font, W - M * 2 - note_w), font=foot_font, fill=_soft(140))
    if picture is not None:
        draw.text((W - M, H - 98), "AI 생성 이미지", font=font("regular", 24), fill=_soft(130), anchor="ra")
    return img


# ── 마무리 ──────────────────────────────────────────────────────────────
def render_closing(sources: list[str], page: int, total: int, accent, has_ai_image: bool,
                   wave: Image.Image | None = None) -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img, "RGBA")
    _header(draw, accent, f"{page} / {total}")
    max_w = W - M * 2

    y = 190
    if wave is None and Path(config.MASCOT_WAVE_FILE).exists():
        wave = Image.open(config.MASCOT_WAVE_FILE).convert("RGB")
    if wave is not None:   # 인사하는 마스코트를 동그랗게
        size = 400
        circle = Image.new("L", (size * 2, size * 2), 0)
        ImageDraw.Draw(circle).ellipse((0, 0, size * 2 - 1, size * 2 - 1), fill=255)
        cx = (W - size) // 2
        draw.ellipse((cx - 10 + 10, y - 10 + 12, cx + size + 10 + 10, y + size + 10 + 12), fill=accent)
        draw.ellipse((cx - 10, y - 10, cx + size + 10, y + size + 10), fill=BROWN)
        img.paste(cover_fit(wave, size, size), (cx, y), circle.resize((size, size), Image.LANCZOS))
        draw = ImageDraw.Draw(img, "RGBA")
        y += size + 70
    else:
        y += 170

    head_font = font("black", 68)
    for line in ("다음 이야기도", "제가 물어올게요"):
        draw.text((W / 2, y), line, font=head_font, fill=BROWN, anchor="ma")
        y += int(head_font.size * 1.25)
    y += 16
    follow = "팔로우하고 다음 소식 받아보기"
    if config.CHANNEL_HANDLE:
        follow = f"{config.CHANNEL_HANDLE} 팔로우하고 다음 소식 받아보기"
    follow_font, follow_lines = fit(follow, "bold", max_w, 2, 38, 28)
    for line in follow_lines:
        draw.text((W / 2, y), line, font=follow_font, fill=accent, anchor="ma")
        y += int(follow_font.size * 1.4)

    note_font = font("regular", 26)
    ai_note = "이 콘텐츠는 AI가 공개된 보도를 요약해 만들었" + ("고, 그림은 AI로 생성했습니다. " if has_ai_image else "습니다. ")
    notes = wrap(ai_note + "자세한 내용은 각 언론사 기사를 확인해 주세요.", note_font, max_w)
    note_y = H - 96 - int(note_font.size * 1.55) * len(notes) - 26
    source_font = font("regular", 30)
    source_lines = wrap("  ·  ".join(sources) or "각 언론사 보도", source_font, max_w)[:3]
    source_y = note_y - 36 - int(source_font.size * 1.5) * len(source_lines)
    draw.text((M, source_y - 52), "출처", font=font("black", 30), fill=BROWN)
    draw_lines(draw, (M, source_y), source_lines, source_font, _soft(190), 1.5)
    draw_lines(draw, (M, note_y), notes, note_font, _soft(140), 1.55)
    draw.line((M, H - 96, W - M, H - 96), fill=_soft(40), width=2)
    draw.text((M, H - 70), "저장해두고 나중에 다시 보기", font=font("bold", 28), fill=_soft(180))
    return img


def render_all(plan: dict, sources: list[str], cover_image: Image.Image | None,
               card_images: list[Image.Image | None], closing_image: Image.Image | None = None) -> list[Image.Image]:
    accent = hex_rgb(config.ACCENT_COLOR)
    has_ai_image = cover_image is not None or any(p is not None for p in card_images)
    total = len(plan["cards"]) + 2
    cards = [render_cover(cover_image, plan, accent)]
    for i, card in enumerate(plan["cards"], start=1):
        cards.append(render_body(card_images[i - 1], card, i, i + 1, total, plan["topic"], accent))
    cards.append(render_closing(sources, total, total, accent, has_ai_image, closing_image))
    return cards


# ── 샘플용 임시 그림 (실제 운영에서는 AI가 그린 마스코트가 들어갑니다) ──────────
def placeholder_cat(width: int, height: int, seed: int = 0, label: str = "") -> Image.Image:
    """디자인 확인용으로 단순하게 그린 샴고양이. 화풍·생김새는 실제 AI 그림과 다릅니다."""
    s = 2  # 2배로 그린 뒤 줄여서 가장자리를 부드럽게
    backgrounds = [(203, 226, 214), (250, 221, 196), (214, 222, 245), (247, 214, 222), (228, 236, 200)]
    canvas = Image.new("RGB", (width * s, height * s), backgrounds[seed % len(backgrounds)])
    d = ImageDraw.Draw(canvas)
    cream, dark, blue, pink = (245, 232, 208), (84, 58, 44), (72, 132, 204), (236, 150, 160)
    # 바닥 그림자와 배경 언덕
    d.ellipse((-200 * s, int(height * 0.72) * s, (width + 200) * s, (height + 400) * s),
              fill=tuple(max(0, c - 22) for c in backgrounds[seed % len(backgrounds)]))
    unit = min(width, height) * s / 100
    cx = int(width * s * (0.5 + 0.16 * ((seed % 3) - 1)))
    cy = int(height * s * 0.60)

    def ell(x0, y0, x1, y1, fill):
        d.ellipse((cx + x0 * unit, cy + y0 * unit, cx + x1 * unit, cy + y1 * unit), fill=fill)

    d.arc((cx + 8 * unit, cy - 6 * unit, cx + 44 * unit, cy + 30 * unit), 250, 70, fill=dark, width=int(5 * unit))  # 꼬리
    ell(-22, -4, 22, 34, cream)                                   # 몸
    ell(-20, 24, -6, 36, dark); ell(6, 24, 20, 36, dark)          # 발
    for sign in (-1, 1):                                          # 귀
        d.polygon([(cx + sign * 24 * unit, cy - 22 * unit), (cx + sign * 20 * unit, cy - 50 * unit),
                   (cx + sign * 4 * unit, cy - 36 * unit)], fill=dark)
    ell(-26, -42, 26, 6, cream)                                   # 머리
    ell(-15, -26, 15, 5, dark)                                    # 얼굴 포인트
    for sign in (-1, 1):                                          # 눈
        ex = sign * 11
        ell(ex - 6, -24, ex + 6, -12, (255, 255, 255)); ell(ex - 4.5, -22.5, ex + 4.5, -13.5, blue)
        ell(ex - 2, -21, ex + 2, -17, (20, 30, 50)); ell(ex + 0.5, -21.5, ex + 2.5, -19.5, (255, 255, 255))
    ell(-2.2, -10, 2.2, -6.5, pink)                               # 코
    ell(-14, 2, 14, 22, (252, 248, 240))                          # 가슴 털
    picture = canvas.resize((width, height), Image.LANCZOS)
    if label:
        draw = ImageDraw.Draw(picture, "RGBA")
        fnt = font("bold", max(22, width // 44))
        tw, th = int(fnt.getlength(label)) + int(fnt.size * 1.2), int(fnt.size * 1.9)
        x, y = int(width * 0.04), int(height * 0.40)
        draw.rounded_rectangle((x, y, x + tw, y + th), radius=th // 2, fill=(255, 255, 255, 215))
        draw.text((x + tw / 2, y + th / 2), label, font=fnt, fill=BROWN, anchor="mm")
    return picture
