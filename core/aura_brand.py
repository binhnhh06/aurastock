"""AURA UI branding. Uses the owner's logo as-is, when available."""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# No asset is invented. The exact logo is copied once by the owner to assets/aura_logo.png.
NAMES = (
    'assets/aura_mark.webp', 'assets/aura_logo.png', 'assets/aura_logo.webp', 'assets/aura_logo.jpg',
    'assets/aura_logo.jpeg', 'aura_logo.png', 'aura_logo.webp',
)


def logo_path():
    for rel in NAMES:
        p = ROOT / rel
        if p.is_file() and p.stat().st_size <= 8_000_000:
            return p
    return None


def favicon():
    p = logo_path()
    if p:
        try:
            from PIL import Image
            return Image.open(p)
        except (OSError, ValueError, ImportError):
            pass
    return '🟣'


def logo_html(*, size=54):
    p = logo_path()
    if p:
        ext = p.suffix.lower()
        mime = 'image/png' if ext == '.png' else 'image/webp' if ext == '.webp' else 'image/jpeg'
        data = base64.b64encode(p.read_bytes()).decode('ascii')
        return (f'<img alt="Logo AURA" src="data:{mime};base64,{data}" '
                f'style="width:{int(size)}px;height:{int(size)}px;object-fit:contain;'
                'border-radius:12px;flex-shrink:0;filter:drop-shadow(3px 4px 1px #0E0624);"/>')
    return (f'<span class="aura-letter" aria-label="AURA" '
            f'style="width:{int(size)}px;height:{int(size)}px;display:inline-flex;'
            'align-items:center;justify-content:center;border-radius:13px;'
            'background:linear-gradient(135deg,#6634EE,#C14FD7);color:white;'
            'font-size:30px;font-weight:850;flex-shrink:0;">A</span>')


def banner_html():
    """The actual owner-supplied wide AURA logo (optimized for navigation)."""
    p = ROOT / "assets" / "aura_banner.webp"
    if not p.is_file():
        return logo_html(size=74)
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return (f'<img alt="AURA · Smart Stock Filter" src="data:image/webp;base64,{data}" '
            'style="display:block;width:100%;height:142px;object-fit:cover;'
            'border-radius:17px;box-shadow:5px 5px 0 #13091F;"/>')
