"""Render the numbered overlay image the judge sees. Owner: Orlando.

Set of marks style: every candidate box gets an outline and a numbered tag in the
same color. Tags go outside their box when there's room, so they don't hide the
text being judged, and never on top of another tag when a free spot exists.
Text dense photos reach 100+ marks (gotcha 38), which is what the placement is for.
"""

from PIL import Image, ImageDraw, ImageFont

from app.schemas import Candidate

# Saturated colors that keep white digits readable; neighbors in reading order differ.
PALETTE = [
    (230, 25, 75), (0, 110, 200), (40, 150, 60), (225, 110, 20),
    (145, 30, 180), (0, 128, 128), (200, 30, 160), (128, 0, 0),
]

Rect = tuple[int, int, int, int]


def render(image: Image.Image, candidates: list[Candidate]) -> Image.Image:
    """A new RGB image with outlines and numbered tags; image is left as is."""
    if any(c.mark is None for c in candidates):
        raise ValueError("render needs numbered candidates; call candidates.build first")
    out = image.convert("RGB")  # always a copy
    draw = ImageDraw.Draw(out)
    long_edge = max(out.size)
    font = ImageFont.load_default(size=min(40, max(12, round(long_edge / 75))))
    line = max(2, long_edge // 600)

    # Outlines first, biggest first, so no outline crosses a tag or hides a small box.
    for c in sorted(candidates, key=lambda c: -_area(c.box)):
        draw.rectangle(_inclusive(c.box), outline=_color(c.mark), width=line)

    for c, rect in zip(candidates, layout(out.size, candidates, font)):
        draw.rectangle(_inclusive(rect), fill=_color(c.mark), outline=(0, 0, 0), width=1)
        text_box = draw.textbbox((0, 0), str(c.mark), font=font)
        tx = rect[0] + (rect[2] - rect[0] - (text_box[2] - text_box[0])) // 2 - text_box[0]
        ty = rect[1] + (rect[3] - rect[1] - (text_box[3] - text_box[1])) // 2 - text_box[1]
        draw.text((tx, ty), str(c.mark), fill=(255, 255, 255), font=font)
    return out


def layout(size: tuple[int, int], candidates: list[Candidate], font) -> list[Rect]:
    """Half-open tag rectangles, one per candidate, in candidate order."""
    width, height = size
    placed: list[Rect] = []
    for c in candidates:
        tw, th = _tag_size(str(c.mark), font)
        spots = [_clamp(s, tw, th, width, height) for s in _spots(c.box, tw, th)]
        free = [s for s in spots if not any(_overlap(s, p) for p in placed)]
        placed.append(free[0] if free else min(spots, key=lambda s: sum(_overlap(s, p) for p in placed)))
    return placed


def _spots(box: list[int], tw: int, th: int) -> list[tuple[int, int]]:
    """Top left corners to try, in order: outside the box, then inside its corner."""
    x1, y1, x2, y2 = box
    return [
        (x1, y1 - th), (x2 - tw, y1 - th),  # above
        (x1, y2), (x2 - tw, y2),  # below
        (x1 - tw, y1), (x2, y1),  # left, right
        (x1, y1),  # inside top left
    ]


def _tag_size(text: str, font) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    pad = max(2, round(font.size / 5))
    return right - left + 2 * pad, bottom - top + 2 * pad


def _clamp(spot: tuple[int, int], tw: int, th: int, width: int, height: int) -> Rect:
    x = min(max(0, spot[0]), max(0, width - tw))
    y = min(max(0, spot[1]), max(0, height - th))
    return x, y, x + tw, y + th


def _overlap(a: Rect, b: Rect) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(box: list[int]) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])


def _inclusive(box) -> list[int]:
    # Our boxes are half-open; Pillow's rectangle includes its far edge.
    return [box[0], box[1], max(box[0], box[2] - 1), max(box[1], box[3] - 1)]


def _color(mark: int) -> tuple[int, int, int]:
    return PALETTE[(mark - 1) % len(PALETTE)]
