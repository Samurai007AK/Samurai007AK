"""Draw the parts of the README that don't change: the banner and the project
cards. Text is turned into SVG paths, so the brush lettering looks the same on
every machine without shipping a font.

Run once locally, then commit the output in assets/:
    pip install fonttools
    python scripts/static_art.py <font_dir>

<font_dir> needs YujiSyuku-Regular.ttf, ShipporiMincho-Regular.ttf and
ShipporiMincho-SemiBold.ttf (all from Google Fonts, OFL licensed).
"""

import random
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from daily import HERE, SERIF, THEMES, mountains, seal, svg

ASSETS = HERE.parent / "assets"


class Face:
    def __init__(self, path):
        font = TTFont(path)
        self.glyphs = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm

    def width(self, text, size, track=0):
        return sum(self.glyphs[self.cmap[ord(c)]].width for c in text) * size / self.upm + track * (len(text) - 1)

    def path(self, text, x, y, size, track=0):
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}")
        s = size / self.upm
        for c in text:
            g = self.glyphs[self.cmap[ord(c)]]
            g.draw(TransformPen(pen, (s, 0, 0, -s, x, y)))
            x += g.width * s + track
        return pen.getCommands()

    def boxed(self, char, box):
        """One glyph scaled and centred into a box x box square."""
        g = self.glyphs[self.cmap[ord(char)]]
        b = BoundsPen(self.glyphs)
        g.draw(b)
        x0, y0, x1, y1 = b.bounds
        s = box / max(x1 - x0, y1 - y0)
        dx = (box - (x1 - x0) * s) / 2 - x0 * s
        dy = (box - (y1 - y0) * s) / 2 + y1 * s
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}")
        g.draw(TransformPen(pen, (s, 0, 0, -s, dx, dy)))
        return pen.getCommands()


def text(face, s, x, y, size, fill, track=0):
    """Brush lettering, drawn as outlines so it renders the same everywhere."""
    return f'<path d="{face.path(s, x, y, size, track)}" fill="{fill}"/>'


def label(s, x, y, size, fill, track=0, anchor="start"):
    """Plain text in a system serif. Much smaller than outlines, which keeps the page quick to load."""
    return (f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" font-family="{SERIF}" font-size="{size}" '
            f'letter-spacing="{track}" fill="{fill}">{s}</text>')


def banner(brush, serif, bold, t):
    W, H = 1200, 400
    body = [f'<circle cx="1062" cy="150" r="105" fill="{t["red"]}" opacity="0.92" filter="url(#brush)"/>',
            f'<g transform="translate(790,40)">{mountains(random.Random(8), t, 430)}</g>']
    name = "Arijit Konar"
    body.append(text(brush, name, 70, 200, 118, t["ink"]))
    body.append(seal(70 + brush.width(name, 118) + 34, 104, 84, t))
    body.append(text(brush, "アリジット・コナル", 74, 256, 26, t["wash"], track=8))
    body.append(label("MLOPS  ·  AI INFRASTRUCTURE", 72, 318, 20, t["ink"], track=5))
    body.append(label("Curious builder. I find new tools, take them apart, and make them better.",
                      72, 356, 20, t["wash"]))
    return svg(W, H, t, "".join(body))


CARDS = [
    dict(slug="gpumesh", kanji="網", meaning="NET", title="GPUMesh", role="MAINTAINER",
         lines=["Borrow your friends' GPUs: a distributed compute mesh in pure Python,",
                "with token auth, opt-in TLS and CI that heals its own flaky runs."],
         tools="PYTHON  ·  DOCKER  ·  DISTRIBUTED SYSTEMS  ·  GITHUB ACTIONS"),
    dict(slug="anchor", kanji="錨", meaning="ANCHOR", title="Anchor", role="PRIVATE BETA  ·  ASK ME FOR A DEMO",
         lines=["A vector store that lives in your own cloud. Hybrid search (BM25 + dense),",
                "migrations, evals and cost controls across S3 Vectors, DynamoDB and LanceDB."],
         tools="PYTHON  ·  ASYNCIO  ·  AWS  ·  LANCEDB  ·  DUCKDB"),
    dict(slug="hiddenhelp", kanji="隠", meaning="HIDDEN", title="HiddenHelp", role="SIDE PROJECT",
         lines=["Walk away from your screen and the video pauses. Come back and it plays.",
                "A webcam, a face detector and one keypress, joined together."],
         tools="PYTHON  ·  OPENCV  ·  PYAUTOGUI  ·  CUSTOMTKINTER"),
]


def card(c, brush, serif, bold, t):
    W, H = 840, 160
    body = [f'<path d="{brush.boxed(c["kanji"], 64)}" fill="{t["red"]}" transform="translate(40,30)"/>',
            label(c["meaning"], 72, 124, 10, t["wash"], track=3, anchor="middle"),
            f'<path d="M140,28 V132" stroke="{t["wash"]}" stroke-width="1" opacity="0.5"/>',
            text(bold, c["title"], 164, 56, 28, t["ink"]),
            label(c["role"], 164 + bold.width(c["title"], 28) + 18, 55, 11, t["red"], track=2.5)]
    for i, line in enumerate(c["lines"]):
        body.append(label(line, 164, 88 + i * 22, 14.5, t["wash"]))
    body.append(label(c["tools"], 164, 140, 10.5, t["ink"], track=2.2))
    return svg(W, H, t, "".join(body))


HEADINGS = ["Work", "The path", "Today", "Numbers"]


def heading(title, bold, t):
    """Section title centred between two ink lines, with a red diamond at each inner end.
    Transparent background so it sits on GitHub's own page colour."""
    W, H = 840, 84
    label = title.upper()
    w = bold.width(label, 24, 8)
    x = (W - w) / 2
    left, right = x - 30, x + w + 30
    diamond = lambda cx: (f'<rect x="{cx - 6:.0f}" y="36" width="12" height="12" fill="{t["red"]}" '
                          f'transform="rotate(45 {cx:.0f} 42)"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<path d="M30,42 H{left - 16:.0f} M{right + 16:.0f},42 H{W - 30}" stroke="{t["ink"]}" '
            f'stroke-width="1.6" opacity="0.7"/>{diamond(left)}{diamond(right)}'
            f'{text(bold, label, x, 51, 24, t["ink"], track=8)}</svg>')


def main():
    fonts = Path(sys.argv[1])
    brush = Face(fonts / "YujiSyuku-Regular.ttf")
    serif = Face(fonts / "ShipporiMincho-Regular.ttf")
    bold = Face(fonts / "ShipporiMincho-SemiBold.ttf")
    (HERE / "seal.txt").write_text(brush.boxed("侍", 100) + "\n")
    ASSETS.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        (ASSETS / f"banner-{name}.svg").write_text(banner(brush, serif, bold, t), encoding="utf-8")
        for title in HEADINGS:
            slug = title.lower().replace(" ", "-")
            (ASSETS / f"heading-{slug}-{name}.svg").write_text(heading(title, bold, t), encoding="utf-8")
        for c in CARDS:
            (ASSETS / f"card-{c['slug']}-{name}.svg").write_text(card(c, brush, serif, bold, t), encoding="utf-8")


if __name__ == "__main__":
    main()
