"""Render Lucide icons to PIL images (stroke-based, 24x24 viewBox)."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Lucide SVG snippets (MIT) — stroke icons, 24x24 viewBox.
_LUCIDE: dict[str, str] = {
    "audio-lines": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>""",
    "copy": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>""",
    "trash-2": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>""",
    "file-text": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>""",
    "clock": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>""",
    "type": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/><line x1="12" x2="12" y1="4" y2="20"/></svg>""",
    "mic": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>""",
    "gauge": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>""",
    "shield-check": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "wifi": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.859a10 10 0 0 1 14 0"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/></svg>""",
    "cpu": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>""",
    "hard-drive": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" x2="2" y1="12" y2="12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" x2="6.01" y1="16" y2="16"/><line x1="10" x2="10.01" y1="16" y2="16"/></svg>""",
    "keyboard": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 8h.01"/><path d="M12 12h.01"/><path d="M14 8h.01"/><path d="M16 12h.01"/><path d="M18 8h.01"/><path d="M6 8h.01"/><path d="M7 16h10"/><path d="M8 12h.01"/><rect width="20" height="16" x="2" y="4" rx="2"/></svg>""",
    "square": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/></svg>""",
}


def _arc_center(x0: float, y0: float, r: float, sweep: float, x: float, y: float):
    mx, my = (x0 + x) / 2, (y0 + y) / 2
    dx, dy = x0 - x, y0 - y
    dist = math.hypot(dx, dy)
    if dist > 2 * r:
        r = dist / 2
    h = math.sqrt(max(r * r - (dist / 2) ** 2, 0))
    if sweep:
        cx = mx + h * dy / (dist or 1)
        cy = my - h * dx / (dist or 1)
    else:
        cx = mx - h * dy / (dist or 1)
        cy = my + h * dx / (dist or 1)
    return cx, cy, r, r


_NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    key = color.lower().strip()
    if key in _NAMED_COLORS:
        return _NAMED_COLORS[key]
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _tokenize_path(d: str) -> list:
    tokens = re.findall(
        r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:e[-+]?\d+)?)",
        d,
    )
    out: list = []
    for cmd, num in tokens:
        if cmd:
            out.append(cmd)
        else:
            out.append(float(num))
    return out


def _path_points(d: str) -> list[tuple[float, float]]:
    tokens = _tokenize_path(d)
    i = 0
    points: list[tuple[float, float]] = []
    x, y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    cmd = "M"

    def read(n: int) -> list[float]:
        nonlocal i
        vals = tokens[i : i + n]
        i += n
        return vals

    while i < len(tokens):
        if isinstance(tokens[i], str):
            cmd = tokens[i]
            i += 1
        rel = cmd.islower()
        c = cmd.upper()

        if c == "M":
            x, y = read(2)
            if rel:
                x += points[-1][0] if points else 0
                y += points[-1][1] if points else 0
            start_x, start_y = x, y
            points.append((x, y))
            cmd = "L"
        elif c == "L":
            x, y = read(2)
            if rel:
                x += points[-1][0]
                y += points[-1][1]
            points.append((x, y))
        elif c == "H":
            (x,) = read(1)
            if rel:
                x += points[-1][0]
            y = points[-1][1]
            points.append((x, y))
        elif c == "V":
            (y,) = read(1)
            if rel:
                y += points[-1][1]
            x = points[-1][0]
            points.append((x, y))
        elif c == "C":
            x1, y1, x2, y2, x, y = read(6)
            if rel:
                ox, oy = points[-1]
                x1 += ox
                y1 += oy
                x2 += ox
                y2 += oy
                x += ox
                y += oy
            for t in range(1, 13):
                t_ = t / 12
                mt = 1 - t_
                px = mt**3 * points[-1][0] + 3 * mt**2 * t_ * x1 + 3 * mt * t_**2 * x2 + t_**3 * x
                py = mt**3 * points[-1][1] + 3 * mt**2 * t_ * y1 + 3 * mt * t_**2 * y2 + t_**3 * y
                points.append((px, py))
        elif c == "Q":
            x1, y1, x, y = read(4)
            if rel:
                ox, oy = points[-1]
                x1 += ox
                y1 += oy
                x += ox
                y += oy
            for t in range(1, 9):
                t_ = t / 8
                mt = 1 - t_
                px = mt**2 * points[-1][0] + 2 * mt * t_ * x1 + t_**2 * x
                py = mt**2 * points[-1][1] + 2 * mt * t_ * y1 + t_**2 * y
                points.append((px, py))
        elif c == "A":
            rx, ry, rot, large, sweep, x, y = read(7)
            x0, y0 = points[-1]
            if rel:
                x += x0
                y += y0
            if rx == 0 or ry == 0:
                points.append((x, y))
            elif abs(rx - ry) < 1e-6:
                cx, cy, _, _ = _arc_center(x0, y0, rx, float(sweep), x, y)
                start = math.atan2(y0 - cy, x0 - cx)
                end = math.atan2(y - cy, x - cx)
                if float(sweep):
                    if end <= start:
                        end += 2 * math.pi
                else:
                    if end >= start:
                        end -= 2 * math.pi
                for t in range(1, 13):
                    t_ = t / 12
                    ang = start + (end - start) * t_
                    points.append((cx + rx * math.cos(ang), cy + rx * math.sin(ang)))
            else:
                for t in range(1, 13):
                    t_ = t / 12
                    points.append((x0 + (x - x0) * t_, y0 + (y - y0) * t_))
        elif c == "Z":
            points.append((start_x, start_y))
        else:
            break
    return points


class _LucideCanvas:
    def __init__(self, size: int, color: str, stroke_scale: float = 1.0):
        self.size = size
        self.scale = size / 24.0
        self.color = _hex_to_rgb(color) + (255,)
        self.stroke = max(1, round(2 * self.scale * stroke_scale))
        self.img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)

    def _pt(self, x: float, y: float) -> tuple[float, float]:
        return x * self.scale, y * self.scale

    def stroke_polyline(self, pts: list[tuple[float, float]], close: bool = False):
        if len(pts) < 2:
            return
        scaled = [self._pt(x, y) for x, y in pts]
        self.draw.line(scaled, fill=self.color, width=self.stroke, joint="curve")
        if close and len(scaled) > 2:
            self.draw.line([scaled[-1], scaled[0]], fill=self.color, width=self.stroke)

    def stroke_path(self, d: str, close: bool = False):
        pts = _path_points(d)
        if not pts:
            return
        should_close = close or d.rstrip().endswith(("Z", "z"))
        self.stroke_polyline(pts, close=should_close)

    def stroke_line(self, x1, y1, x2, y2):
        self.draw.line([self._pt(x1, y1), self._pt(x2, y2)], fill=self.color, width=self.stroke)

    def stroke_rect(self, x, y, w, h, rx=0):
        x1, y1 = self._pt(x, y)
        x2, y2 = self._pt(x + w, y + h)
        r = rx * self.scale
        if r > 0:
            self.draw.rounded_rectangle((x1, y1, x2, y2), radius=r, outline=self.color, width=self.stroke)
        else:
            self.draw.rectangle((x1, y1, x2, y2), outline=self.color, width=self.stroke)

    def stroke_circle(self, cx, cy, r):
        cx, cy = self._pt(cx, cy)
        rad = r * self.scale
        self.draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=self.color, width=self.stroke)

    def fill_circle(self, cx, cy, r, fill_color: str):
        cx, cy = self._pt(cx, cy)
        rad = r * self.scale
        rgb = _hex_to_rgb(fill_color) + (255,)
        self.draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=rgb)

    def fill_path(self, d: str, fill_color: str):
        pts = _path_points(d)
        if len(pts) < 3:
            return
        rgb = _hex_to_rgb(fill_color) + (255,)
        self.draw.polygon([self._pt(x, y) for x, y in pts], fill=rgb)

    def fill_rect(self, x, y, w, h, rx=0, fill_color: str = "#000"):
        x1, y1 = self._pt(x, y)
        x2, y2 = self._pt(x + w, y + h)
        rgb = _hex_to_rgb(fill_color) + (255,)
        r = rx * self.scale
        if r > 0:
            self.draw.rounded_rectangle((x1, y1, x2, y2), radius=r, fill=rgb)
        else:
            self.draw.rectangle((x1, y1, x2, y2), fill=rgb)


def _render_element(canvas: _LucideCanvas, el: ET.Element, fill_override: str | None):
    tag = el.tag.split("}")[-1]
    if tag == "path":
        d = el.get("d", "")
        if el.get("fill", "none") != "none" and fill_override:
            canvas.fill_path(d, fill_override)
        else:
            canvas.stroke_path(d)
    elif tag == "line":
        canvas.stroke_line(
            float(el.get("x1", 0)),
            float(el.get("y1", 0)),
            float(el.get("x2", 0)),
            float(el.get("y2", 0)),
        )
    elif tag == "rect":
        fill = el.get("fill", "none")
        if fill != "none" and fill_override:
            canvas.fill_rect(
                float(el.get("x", 0)),
                float(el.get("y", 0)),
                float(el.get("width", 0)),
                float(el.get("height", 0)),
                float(el.get("rx", 0)),
                fill_override,
            )
        else:
            canvas.stroke_rect(
                float(el.get("x", 0)),
                float(el.get("y", 0)),
                float(el.get("width", 0)),
                float(el.get("height", 0)),
                float(el.get("rx", 0)),
            )
    elif tag == "circle":
        canvas.stroke_circle(float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0)))
    elif tag == "polyline":
        raw = el.get("points", "")
        nums = [float(n) for n in re.findall(r"-?\d*\.?\d+", raw)]
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        canvas.stroke_polyline(pts)
    elif tag == "polygon":
        raw = el.get("points", "")
        nums = [float(n) for n in re.findall(r"-?\d*\.?\d+", raw)]
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        canvas.stroke_polyline(pts, close=True)


def render_lucide(
    name: str,
    size: int,
    color: str = "#71717B",
    *,
    fill: str | None = None,
    stroke_scale: float = 1.0,
) -> Image.Image:
    """Rasterize a Lucide icon to a PIL RGBA image."""
    svg_text = _LUCIDE.get(name)
    if svg_text is None:
        file_path = _ICONS_DIR / f"{name}.svg"
        if file_path.exists():
            svg_text = file_path.read_text(encoding="utf-8")
        else:
            raise KeyError(f"Unknown icon: {name}")

    svg_text = svg_text.replace("currentColor", color)
    root = ET.fromstring(svg_text)
    canvas = _LucideCanvas(size, color, stroke_scale=stroke_scale)
    for child in root:
        _render_element(canvas, child, fill)
    return canvas.img


def render_logo(size: int, bg: str = "#2B7FFF", icon_color: str = "#EFF6FF") -> Image.Image:
    """App logo: rounded blue tile with AudioLines icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=_hex_to_rgb(bg) + (255,))
    icon_size = int(size * 0.5)
    icon = render_lucide("audio-lines", icon_size, icon_color)
    offset = (size - icon_size) // 2
    img.paste(icon, (offset, offset), icon)
    return img
