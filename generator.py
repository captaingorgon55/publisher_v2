"""
generator.py - Generador de tarjetas estilo El Espectador.

Soporta:
- Formato Post (1080x1350) y Story (1080x1920)
- 4 plantillas: "classic", "card", "with_cta", "attention" (portadas del v1)
- Múltiples fondos/degradados (de assets/fondos/)
- Stickers de sección con o sin icono (de assets/secciones/ o secciones-icono/)
- Logo EE oficial (blanco o negro)
- CTA "Lea la noticia completa en elespectador.com"
- Iconos de acciones IG (corazón, comentario, etc.)
- Ajuste de zoom y posición XY de la imagen
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import requests
import re
import os
import unicodedata
import numpy as np
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ============================================================
# CONSTANTES Y RUTAS
# ============================================================

FORMATS = {
    "post": {
        "name": "Post (Instagram)",
        "size": (1080, 1350),
        "description": "Formato cuadrado vertical 4:5",
    },
    "story": {
        "name": "Story (Instagram/Facebook)",
        "size": (1080, 1920),
        "description": "Formato vertical 9:16 para stories",
    },
}

DEFAULT_FORMAT = "post"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
FONDOS_DIR = os.path.join(ASSETS_DIR, "fondos")
SECCIONES_DIR = os.path.join(ASSETS_DIR, "secciones")
SECCIONES_ICONO_DIR = os.path.join(ASSETS_DIR, "secciones-icono")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")
GRAFICOS_DIR = os.path.join(ASSETS_DIR, "graficos")

# Colores
RED = (227, 27, 35)
WHITE = (255, 255, 255)
BLACK = (15, 15, 15)
GRAY_BG = (235, 235, 235)
PURPLE = (66, 28, 87)


# ============================================================
# REGISTRO DE PLANTILLAS
# ============================================================

TEMPLATES = {
    "classic": {
        "name": "Clásica",
        "description": "Foto a sangre con gradiente oscuro, título blanco e iconos sociales",
    },
    "card": {
        "name": "Card",
        "description": "Foto enmarcada sobre fondo gris claro, título en negro",
    },
    "with_cta": {
        "name": "Con CTA",
        "description": "Como Clásica pero con 'Lea la noticia completa...'",
    },
    "attention": {
        "name": "Atención",
        "description": "Foto arriba + bloque morado sólido abajo con título y CTA",
    },
}


# ============================================================
# UTILIDADES
# ============================================================

def normalize_key(s):
    """Minúsculas, sin acentos, espacios/símbolos → guiones."""
    if not s:
        return ""
    s = s.lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def find_in_dir(dir_path, key):
    """Busca un archivo PNG en un directorio que matchee la key normalizada."""
    if not key or not os.path.exists(dir_path):
        return None
    files = [f for f in os.listdir(dir_path) if f.lower().endswith(".png")]
    for f in files:
        if normalize_key(f[:-4]) == key:
            return os.path.join(dir_path, f)
    for f in files:
        name = normalize_key(f[:-4])
        if name.startswith(key + "-") or name.endswith("-" + key):
            return os.path.join(dir_path, f)
    return None


def list_fondos():
    """Devuelve lista de fondos disponibles."""
    if not os.path.exists(FONDOS_DIR):
        return []
    return sorted([f[:-4] for f in os.listdir(FONDOS_DIR) if f.lower().endswith(".png")])


SECTION_TO_FONDO = {
    "la-red-zoocial": "la-red-zoocial",
    "colombia-20": "colombia-20",
    "vea": "vea",
    "gastronomia": "gastronomia",
    "ultima-hora": "ultima-hora",
    "podcast": "podcast",
    "politica": "claro-oscuro",
    "judicial": "claro-oscuro",
    "investigacion": "claro-oscuro",
    "internacional": "claro-oscuro",
    "mundo": "claro-oscuro",
    "colombia": "claro-oscuro",
    "bogota": "claro-oscuro",
    "atencion": "ultima-hora",
    "lo-ultimo": "ultima-hora",
    "en-vivo": "ultima-hora",
    "en-directo": "ultima-hora",
    "deportes": "claro-oscuro",
    "economia": "echemos-cuentas",
    "magazin-cultural": "claro-oscuro",
    "entretenimiento": "claro-oscuro",
    "peliculas": "claro-oscuro",
    "series": "claro-oscuro",
    "vea-y-vea": "vea",
    "opinion": "gris-oscuro",
    "columna": "gris-oscuro",
    "entrevista": "claro-oscuro",
    "enfoque": "en-foco",
    "ambiente": "claro-oscuro",
    "ciencia": "claro-oscuro",
    "salud": "claro-oscuro",
    "tecnologia": "claro-oscuro",
    "educacion": "claro-oscuro",
    "genero": "impacto-mujer",
    "reportajes": "claro-oscuro",
    "turismo": "claro-oscuro",
    "autos": "claro-oscuro",
    "especial-ee": "claro-oscuro",
    "actualidad": "claro-oscuro",
}


def suggest_fondo_for_section(section_text):
    """Sugiere un fondo apropiado para la sección."""
    if not section_text:
        return "claro-oscuro"
    key = normalize_key(section_text)
    fondos_disponibles = set(list_fondos())
    if key in fondos_disponibles:
        return key
    if key in SECTION_TO_FONDO:
        candidate = SECTION_TO_FONDO[key]
        if candidate in fondos_disponibles:
            return candidate
    for fondo in fondos_disponibles:
        if fondo in key or key in fondo:
            return fondo
    if "claro-oscuro" in fondos_disponibles:
        return "claro-oscuro"
    if fondos_disponibles:
        return sorted(fondos_disponibles)[0]
    return None


def find_section_sticker(section_text, with_icon=False):
    """Busca el sticker de la sección (con o sin icono)."""
    key = normalize_key(section_text)
    if not key:
        return None
    folder = SECCIONES_ICONO_DIR if with_icon else SECCIONES_DIR
    return find_in_dir(folder, key)


def find_fondo(fondo_name):
    """Busca el fondo por nombre."""
    if not fondo_name:
        return None
    return find_in_dir(FONDOS_DIR, normalize_key(fondo_name))


def load_font(size, bold=True):
    """Carga fuente del sistema con fallbacks."""
    candidates_bold = [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]
    candidates_reg = [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for path in (candidates_bold if bold else candidates_reg):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def trim_transparent(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def upscale_image_url(url):
    """Genera URLs candidatas de mayor calidad."""
    candidates = []
    if "/resizer/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        hd = {**{k: v[0] for k, v in params.items()}, "width": "2400", "quality": "95", "smart": "true"}
        hd.pop("height", None)
        candidates.append(urlunparse(parsed._replace(query=urlencode(hd))))
        md = {**hd, "width": "1600"}
        candidates.append(urlunparse(parsed._replace(query=urlencode(md))))
    elif "/image/upload/" in url and "cloudinary" in url:
        candidates.append(re.sub(r"/image/upload/[^/]*?/", "/image/upload/w_2400,q_95,c_fill/", url, count=1))
    elif "wp-content/uploads" in url:
        orig = re.sub(r"-\d+x\d+(\.[a-z]+)$", r"\1", url)
        if orig != url:
            candidates.append(orig)
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        new_params = {k: v[0] for k, v in params.items()}
        modified = False
        for key in ("width", "w", "size"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 2000:
                        new_params[key] = "2400"
                        modified = True
                except ValueError:
                    pass
        for key in ("quality", "q"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 90:
                        new_params[key] = "95"
                        modified = True
                except ValueError:
                    pass
        for key in ("height", "h"):
            if key in new_params:
                new_params.pop(key)
                modified = True
        if modified:
            new_url = urlunparse(parsed._replace(query=urlencode(new_params)))
            if new_url not in candidates:
                candidates.append(new_url)
    candidates.append(url)
    return candidates


def fetch_image(url):
    """Descarga imagen con mejor calidad disponible."""
    candidates = upscale_image_url(url)
    last_err = None
    for u in candidates:
        try:
            r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"})
            if r.status_code == 200 and len(r.content) > 1000:
                img = Image.open(BytesIO(r.content)).convert("RGB")
                if img.width >= 400 and img.height >= 400:
                    return img
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise Exception("No se pudo descargar la imagen")


def cover_resize(img, target_size, zoom=1.0, offset_x=0.5, offset_y=0.5):
    """Cover resize con zoom y offsets."""
    tw, th = target_size
    iw, ih = img.size
    cover_scale = max(tw / iw, th / ih)
    final_scale = cover_scale * max(zoom, 1.0)
    nw, nh = int(iw * final_scale), int(ih * final_scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    max_left, max_top = nw - tw, nh - th
    left = max(0, min(int(max_left * offset_x), max_left))
    top = max(0, min(int(max_top * offset_y), max_top))
    return img.crop((left, top, left + tw, top + th))


def paste_asset(canvas, asset_path, target_height=None, target_width=None,
                position=(0, 0), anchor="top-left"):
    """Pega un PNG con transparencia."""
    if not asset_path or not os.path.exists(asset_path):
        return canvas
    asset = Image.open(asset_path).convert("RGBA")
    asset = trim_transparent(asset)
    if target_height:
        ratio = target_height / asset.height
        new_w = int(asset.width * ratio)
        asset = asset.resize((new_w, target_height), Image.LANCZOS)
    elif target_width:
        ratio = target_width / asset.width
        new_h = int(asset.height * ratio)
        asset = asset.resize((target_width, new_h), Image.LANCZOS)
    aw, ah = asset.size
    x, y = position
    if anchor == "top-left":
        px, py = x, y
    elif anchor == "top-right":
        px, py = x - aw, y
    elif anchor == "bottom-left":
        px, py = x, y - ah
    elif anchor == "bottom-right":
        px, py = x - aw, y - ah
    elif anchor == "center":
        px, py = x - aw // 2, y - ah // 2
    else:
        px, py = x, y
    rgba = canvas.convert("RGBA")
    rgba.paste(asset, (int(px), int(py)), asset)
    return rgba.convert("RGB")


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], []
    for w in words:
        test = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


def fit_title_font(draw, title, max_width, max_lines,
                   size_start=58, size_min=36, size_step=2, bold=True):
    for size in range(size_start, size_min - 1, -size_step):
        font = load_font(size, bold=bold)
        lines = wrap_text(title, font, max_width, draw)
        if len(lines) <= max_lines:
            return font, lines
    font = load_font(size_min, bold=bold)
    lines = wrap_text(title, font, max_width, draw)[:max_lines]
    if lines and not lines[-1].endswith("..."):
        lines[-1] = lines[-1].rsplit(" ", 1)[0] + "..."
    return font, lines


def draw_text_lines(draw, lines, font, x, y, color, line_spacing=1.25):
    lh_bbox = draw.textbbox((0, 0), "Ag", font=font)
    lh = (lh_bbox[3] - lh_bbox[1]) * line_spacing
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        ly = int(y + i * lh - bbox[1])
        draw.text((x, ly), line, font=font, fill=color)
    return int(lh * len(lines))


def add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82, max_alpha=200):
    """Gradiente oscuro concentrado en área del título."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    top = int(h * top_frac)
    bottom = int(h * bottom_frac)
    for y in range(top, bottom):
        alpha = int(max_alpha * ((y - top) / (bottom - top)) ** 1.2)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    for y in range(bottom, h):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, max_alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_section_badge(canvas, section_text, position, font, with_icon=False):
    """
    Dibuja el sticker/badge de sección.

    Busca primero en assets/secciones-icono/ o assets/secciones/ según with_icon.
    Si no encuentra el PNG, dibuja un badge básico con fondo rojo.

    Returns: (canvas, badge_width, badge_height)
    """
    x, y = position
    sticker_path = find_section_sticker(section_text, with_icon=with_icon)

    if sticker_path:
        sticker = Image.open(sticker_path).convert("RGBA")
        sticker = trim_transparent(sticker)
        target_h = int(font.size * 1.7)
        ratio = target_h / sticker.height
        new_w = int(sticker.width * ratio)
        sticker = sticker.resize((new_w, target_h), Image.LANCZOS)
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(sticker, (int(x), int(y)), sticker)
        return canvas_rgba.convert("RGB"), new_w, target_h

    # Fallback: badge básico con fondo rojo
    draw = ImageDraw.Draw(canvas)
    text = (section_text or "").upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 22, 14
    badge_w = text_w + pad_x * 2
    badge_h = text_h + pad_y * 2
    draw.rectangle([x, y, x + badge_w, y + badge_h], fill=RED)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=WHITE)
    return canvas, badge_w, badge_h


def _logo_path(color="blanco"):
    """Resuelve la ruta del logo EE según color ('blanco' o 'negro')."""
    return os.path.join(LOGOS_DIR, f"ee-{color}.png")


def _social_icons_path(color="blanco"):
    """Resuelve la ruta de los iconos de acciones IG según color."""
    return os.path.join(GRAFICOS_DIR, f"acciones-ig-{color}.png")


def _cta_path(color="blanco"):
    """Resuelve la ruta del CTA PNG según color."""
    return os.path.join(GRAFICOS_DIR, f"cta-{color}.png")


def draw_cta_inline(draw, position, font, canvas_size):
    """
    Dibuja el CTA '→ Lea la noticia completa en elespectador.com' usando texto
    cuando no existe el PNG de CTA. Retorna (width, height).
    """
    x, y = position
    text_normal = "Lea la noticia completa en "
    text_bold = "elespectador.com"

    bbox_n = draw.textbbox((0, 0), text_normal, font=font)
    text_w_n = bbox_n[2] - bbox_n[0]
    text_h = bbox_n[3] - bbox_n[1]

    bold_font = load_font(font.size, bold=True)
    bbox_b = draw.textbbox((0, 0), text_bold, font=bold_font)
    text_w_b = bbox_b[2] - bbox_b[0]

    arrow_w = 30
    arrow_gap = 14
    pad_x, pad_y = 18, 12

    total_text_w = arrow_w + arrow_gap + text_w_n + text_w_b
    box_w = total_text_w + pad_x * 2
    box_h = text_h + pad_y * 2

    try:
        draw.rounded_rectangle(
            [x, y, x + box_w, y + box_h],
            radius=6,
            outline=RED, width=3, fill=WHITE,
        )
    except AttributeError:
        draw.rectangle([x, y, x + box_w, y + box_h], outline=RED, width=3, fill=WHITE)

    # Flecha roja
    arrow_x = x + pad_x
    arrow_y = y + box_h // 2
    draw.line([(arrow_x, arrow_y), (arrow_x + arrow_w - 6, arrow_y)], fill=RED, width=3)
    arrow_tip = [
        (arrow_x + arrow_w - 6, arrow_y),
        (arrow_x + arrow_w - 14, arrow_y - 7),
        (arrow_x + arrow_w - 14, arrow_y + 7),
    ]
    draw.polygon(arrow_tip, fill=RED)

    # Texto
    text_x = arrow_x + arrow_w + arrow_gap
    text_y = y + pad_y - bbox_n[1]
    draw.text((text_x, text_y), text_normal, font=font, fill=BLACK)
    draw.text((text_x + text_w_n, text_y), text_bold, font=bold_font, fill=BLACK)

    return box_w, box_h


def _paste_cta(canvas, margin_x, footer_y, canvas_w, text_color, draw_fallback=None):
    """
    Intenta pegar el CTA PNG. Si no existe, usa draw_fallback (draw objeto) para
    dibujar el CTA inline. Si draw_fallback es None, omite el CTA sin imagen.
    """
    color = "blanco" if text_color == WHITE else "negro"
    cta_file = _cta_path(color)
    if os.path.exists(cta_file):
        cta_w = int(canvas_w * 0.65)
        canvas = paste_asset(
            canvas, cta_file,
            target_width=cta_w,
            position=(margin_x, footer_y),
            anchor="bottom-left",
        )
    elif draw_fallback is not None:
        cta_font = load_font(22, bold=False)
        draw_cta_inline(draw_fallback, (margin_x, footer_y - 60), cta_font, (canvas_w, footer_y))
    return canvas


def _paste_logo(canvas, canvas_w, footer_y, canvas_h, text_color):
    """Pega el logo EE en la esquina inferior derecha."""
    color = "blanco" if text_color == WHITE else "negro"
    logo_file = _logo_path(color)
    logo_h = int(canvas_h * 0.06)
    margin_x = int(canvas_w * 0.06)
    return paste_asset(
        canvas, logo_file,
        target_height=logo_h,
        position=(canvas_w - margin_x, footer_y),
        anchor="bottom-right",
    )


def _paste_social_icons(canvas, margin_x, footer_y, canvas_h, text_color):
    """Pega los iconos de acciones IG en la esquina inferior izquierda."""
    color = "blanco" if text_color == WHITE else "negro"
    icons_file = _social_icons_path(color)
    icons_h = int(canvas_h * 0.05)
    return paste_asset(
        canvas, icons_file,
        target_height=icons_h,
        position=(margin_x, footer_y),
        anchor="bottom-left",
    )


# ============================================================
# PLANTILLA 1: CLASSIC
# Foto sangrada + gradiente oscuro + título blanco + iconos sociales + logo EE
# ============================================================

def render_classic(source_image, section, title,
                   format_key="post", seccion_con_icono=False,
                   zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    footer_y = canvas_h - int(canvas_h * 0.044)
    img = _paste_social_icons(img, margin_x, footer_y, canvas_h, WHITE)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)

    return img


# ============================================================
# PLANTILLA 2: CARD
# Fondo gris + foto enmarcada + título en negro + logo EE oscuro
# ============================================================

def render_card(source_image, section, title,
                format_key="post", seccion_con_icono=False,
                zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = Image.new("RGB", (canvas_w, canvas_h), GRAY_BG)

    draw = ImageDraw.Draw(canvas)
    badge_font = load_font(28, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Foto enmarcada
    photo_top = int(canvas_h * 0.104)
    photo_left = margin_x
    photo_right = canvas_w - margin_x
    photo_bottom = int(canvas_h * 0.607)
    photo_w = photo_right - photo_left
    photo_h = photo_bottom - photo_top

    photo = cover_resize(source_image, (photo_w, photo_h), zoom, offset_x, offset_y)
    canvas.paste(photo, (photo_left, photo_top))

    # Título en negro debajo de la foto
    title_max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(
        draw, title, max_width=title_max_w,
        max_lines=3 if format_key == "post" else 4,
        size_start=56, size_min=42,
    )

    line_y_start = photo_bottom + int(canvas_h * 0.037)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, line_y_start, margin_x + 6, line_y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, line_y_start, BLACK)

    # Iconos sociales y logo en negro (fondo claro)
    footer_y = canvas_h - int(canvas_h * 0.044)
    canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, BLACK)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, BLACK)

    return canvas


# ============================================================
# PLANTILLA 3: WITH_CTA
# Como classic + CTA "Lea la noticia completa..." en footer
# ============================================================

def render_with_cta(source_image, section, title,
                    format_key="post", seccion_con_icono=False,
                    zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.50, bottom_frac=0.80, max_alpha=210)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=54)

    # Reservar espacio para CTA + logo debajo del título
    cta_reserved = int(canvas_h * 0.148)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - cta_reserved - total_h - int(canvas_h * 0.022)

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(img)  # re-crear draw si paste_asset convirtió a RGB
    img = _paste_cta(img, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)

    return img


# ============================================================
# PLANTILLA 4: ATTENTION
# Foto arriba + bloque morado sólido abajo + título blanco + CTA
# ============================================================

def render_attention(source_image, section, title,
                     format_key="post", seccion_con_icono=False,
                     zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    # Foto cubre todo el canvas al fondo
    photo_full = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = photo_full.convert("RGBA")

    # Bloque morado con degradado (transición foto → morado)
    photo_h = int(canvas_h * 0.62)
    block_height = canvas_h - photo_h
    transition_height = int(block_height * 0.40)

    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    for i in range(transition_height):
        progress = i / transition_height
        alpha = int(255 * (progress ** 0.85))
        y = photo_h + i
        draw_overlay.line([(0, y), (canvas_w, y)],
                          fill=(PURPLE[0], PURPLE[1], PURPLE[2], alpha))

    draw_overlay.rectangle(
        [0, photo_h + transition_height, canvas_w, canvas_h],
        fill=(PURPLE[0], PURPLE[1], PURPLE[2], 255)
    )

    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    # Badge de sección sobre el bloque morado
    badge_y = photo_h + int(block_height * 0.06)
    badge_font = load_font(30, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, badge_y), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Título blanco
    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=50)

    title_y = badge_y + int(block_height * 0.18)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_y, margin_x + 6, title_y + total_h], fill=WHITE)
    draw_text_lines(draw, lines, title_font, margin_x + 26, title_y, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(canvas)
    canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, WHITE)

    return canvas


# ============================================================
# RENDER GENÉRICO (del script v2, adaptado a las nuevas plantillas)
# ============================================================

def render_generic(source_image, section, title,
                   format_key="post", fondo_name="ultima-hora",
                   seccion_con_icono=False, show_cta=False,
                   show_social_icons=True,
                   zoom=1.0, offset_x=0.5, offset_y=0.5):
    """
    Render con fondo/degradado PNG de assets/fondos/.
    Versión original del script v2.
    """
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = canvas.convert("RGBA")

    bg_path = find_fondo(fondo_name)
    if bg_path:
        overlay = Image.open(bg_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, overlay)

    canvas = canvas.convert("RGB")

    text_area_top = int(canvas_h * 0.62)
    text_area_h = canvas_h - text_area_top

    # Sticker de sección
    sticker_y = text_area_top + int(text_area_h * 0.10)
    sticker_h = int(canvas_h * 0.05) if format_key == "post" else int(canvas_h * 0.04)
    badge_font = load_font(28, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, sticker_y), badge_font, seccion_con_icono)

    # Título
    title_top = sticker_y + sticker_h + int(canvas_h * 0.025)
    title_max_w = canvas_w - margin_x * 2 - 30
    reserved_bottom = int(canvas_h * 0.14) if (show_cta or show_social_icons) else int(canvas_h * 0.10)
    max_title_h = canvas_h - title_top - reserved_bottom
    line_h_approx = 60 if format_key == "post" else 65
    max_lines = max(3, max_title_h // line_h_approx)

    draw = ImageDraw.Draw(canvas)
    title_font, lines = fit_title_font(
        draw, title, title_max_w, max_lines=max_lines,
        size_start=48 if format_key == "post" else 54,
        size_min=32,
    )

    # Detectar color de texto según luminosidad del área
    sample_area = canvas.crop((0, title_top, canvas_w, min(canvas_h, title_top + 200)))
    bg_sample = np.array(sample_area.resize((50, 50))).mean()
    title_color = WHITE if bg_sample < 128 else BLACK

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    title_total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_top, margin_x + 6, title_top + title_total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26 + 6, title_top, title_color)

    footer_y = canvas_h - int(canvas_h * 0.04)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, title_color)

    if show_cta:
        canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, title_color, draw_fallback=draw)
    elif show_social_icons:
        canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, title_color)

    return canvas


# ============================================================
# API PÚBLICA
# ============================================================

def generate_card_from_image(
    source_image,
    section,
    title,
    template="classic",            # "classic" | "card" | "with_cta" | "attention" | "generic"
    format_key="post",             # "post" | "story"
    fondo_name=None,               # para template="generic", nombre del fondo a usar
    seccion_con_icono=False,       # True = usar sticker con icono
    show_cta=False,                # solo para template="generic"
    show_social_icons=True,        # solo para template="generic"
    zoom=1.0,
    offset_x=0.5,
    offset_y=0.5,
    output_path=None,
):
    """
    Genera la tarjeta usando la plantilla seleccionada.

    Args:
        template:   "classic" | "card" | "with_cta" | "attention" | "generic"
        format_key: "post" (1080x1350) | "story" (1080x1920)
        fondo_name: solo para template "generic". Si es None se autodetecta por sección.
        seccion_con_icono: True para usar sticker con icono de la sección.
        show_cta:   solo para template "generic".
        show_social_icons: solo para template "generic".
        zoom, offset_x, offset_y: control de encuadre de la foto.
        output_path: si se especifica, guarda el PNG en esa ruta y devuelve None.

    Returns:
        PIL.Image si output_path es None, o None si se guardó en archivo.
    """
    if format_key not in FORMATS:
        format_key = DEFAULT_FORMAT

    common_kwargs = dict(
        format_key=format_key,
        seccion_con_icono=seccion_con_icono,
        zoom=zoom,
        offset_x=offset_x,
        offset_y=offset_y,
    )

    if template == "classic":
        img = render_classic(source_image, section, title, **common_kwargs)

    elif template == "card":
        img = render_card(source_image, section, title, **common_kwargs)

    elif template == "with_cta":
        img = render_with_cta(source_image, section, title, **common_kwargs)

    elif template == "attention":
        img = render_attention(source_image, section, title, **common_kwargs)

    elif template == "generic":
        resolved_fondo = fondo_name or suggest_fondo_for_section(section)
        img = render_generic(
            source_image, section, title,
            fondo_name=resolved_fondo,
            show_cta=show_cta,
            show_social_icons=show_social_icons,
            **common_kwargs,
        )

    else:
        valid = list(TEMPLATES.keys()) + ["generic"]
        raise ValueError(f"Plantilla desconocida: '{template}'. Opciones: {valid}")

    if output_path:
        img.save(output_path, "PNG", quality=95)
        return None
    return img


def generate_card(image_url, section, title, **kwargs):
    """Versión que descarga la imagen desde URL primero."""
    source_image = fetch_image(image_url)
    return generate_card_from_image(source_image, section, title, **kwargs)"""
generator.py - Generador de tarjetas estilo El Espectador.

Soporta:
- Formato Post (1080x1350) y Story (1080x1920)
- 4 plantillas: "classic", "card", "with_cta", "attention" (portadas del v1)
- Múltiples fondos/degradados (de assets/fondos/)
- Stickers de sección con o sin icono (de assets/secciones/ o secciones-icono/)
- Logo EE oficial (blanco o negro)
- CTA "Lea la noticia completa en elespectador.com"
- Iconos de acciones IG (corazón, comentario, etc.)
- Ajuste de zoom y posición XY de la imagen
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import requests
import re
import os
import unicodedata
import numpy as np
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ============================================================
# CONSTANTES Y RUTAS
# ============================================================

FORMATS = {
    "post": {
        "name": "Post (Instagram)",
        "size": (1080, 1350),
        "description": "Formato cuadrado vertical 4:5",
    },
    "story": {
        "name": "Story (Instagram/Facebook)",
        "size": (1080, 1920),
        "description": "Formato vertical 9:16 para stories",
    },
}

DEFAULT_FORMAT = "post"

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
FONDOS_DIR = os.path.join(ASSETS_DIR, "fondos")
SECCIONES_DIR = os.path.join(ASSETS_DIR, "secciones")
SECCIONES_ICONO_DIR = os.path.join(ASSETS_DIR, "secciones-icono")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")
GRAFICOS_DIR = os.path.join(ASSETS_DIR, "graficos")

# Colores
RED = (227, 27, 35)
WHITE = (255, 255, 255)
BLACK = (15, 15, 15)
GRAY_BG = (235, 235, 235)
PURPLE = (66, 28, 87)


# ============================================================
# REGISTRO DE PLANTILLAS
# ============================================================

TEMPLATES = {
    "classic": {
        "name": "Clásica",
        "description": "Foto a sangre con gradiente oscuro, título blanco e iconos sociales",
    },
    "card": {
        "name": "Card",
        "description": "Foto enmarcada sobre fondo gris claro, título en negro",
    },
    "with_cta": {
        "name": "Con CTA",
        "description": "Como Clásica pero con 'Lea la noticia completa...'",
    },
    "attention": {
        "name": "Atención",
        "description": "Foto arriba + bloque morado sólido abajo con título y CTA",
    },
}


# ============================================================
# UTILIDADES
# ============================================================

def normalize_key(s):
    """Minúsculas, sin acentos, espacios/símbolos → guiones."""
    if not s:
        return ""
    s = s.lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def find_in_dir(dir_path, key):
    """Busca un archivo PNG en un directorio que matchee la key normalizada."""
    if not key or not os.path.exists(dir_path):
        return None
    files = [f for f in os.listdir(dir_path) if f.lower().endswith(".png")]
    for f in files:
        if normalize_key(f[:-4]) == key:
            return os.path.join(dir_path, f)
    for f in files:
        name = normalize_key(f[:-4])
        if name.startswith(key + "-") or name.endswith("-" + key):
            return os.path.join(dir_path, f)
    return None


def list_fondos():
    """Devuelve lista de fondos disponibles."""
    if not os.path.exists(FONDOS_DIR):
        return []
    return sorted([f[:-4] for f in os.listdir(FONDOS_DIR) if f.lower().endswith(".png")])


SECTION_TO_FONDO = {
    "la-red-zoocial": "la-red-zoocial",
    "colombia-20": "colombia-20",
    "vea": "vea",
    "gastronomia": "gastronomia",
    "ultima-hora": "ultima-hora",
    "podcast": "podcast",
    "politica": "claro-oscuro",
    "judicial": "claro-oscuro",
    "investigacion": "claro-oscuro",
    "internacional": "claro-oscuro",
    "mundo": "claro-oscuro",
    "colombia": "claro-oscuro",
    "bogota": "claro-oscuro",
    "atencion": "ultima-hora",
    "lo-ultimo": "ultima-hora",
    "en-vivo": "ultima-hora",
    "en-directo": "ultima-hora",
    "deportes": "claro-oscuro",
    "economia": "echemos-cuentas",
    "magazin-cultural": "claro-oscuro",
    "entretenimiento": "claro-oscuro",
    "peliculas": "claro-oscuro",
    "series": "claro-oscuro",
    "vea-y-vea": "vea",
    "opinion": "gris-oscuro",
    "columna": "gris-oscuro",
    "entrevista": "claro-oscuro",
    "enfoque": "en-foco",
    "ambiente": "claro-oscuro",
    "ciencia": "claro-oscuro",
    "salud": "claro-oscuro",
    "tecnologia": "claro-oscuro",
    "educacion": "claro-oscuro",
    "genero": "impacto-mujer",
    "reportajes": "claro-oscuro",
    "turismo": "claro-oscuro",
    "autos": "claro-oscuro",
    "especial-ee": "claro-oscuro",
    "actualidad": "claro-oscuro",
}


def suggest_fondo_for_section(section_text):
    """Sugiere un fondo apropiado para la sección."""
    if not section_text:
        return "claro-oscuro"
    key = normalize_key(section_text)
    fondos_disponibles = set(list_fondos())
    if key in fondos_disponibles:
        return key
    if key in SECTION_TO_FONDO:
        candidate = SECTION_TO_FONDO[key]
        if candidate in fondos_disponibles:
            return candidate
    for fondo in fondos_disponibles:
        if fondo in key or key in fondo:
            return fondo
    if "claro-oscuro" in fondos_disponibles:
        return "claro-oscuro"
    if fondos_disponibles:
        return sorted(fondos_disponibles)[0]
    return None


def find_section_sticker(section_text, with_icon=False):
    """Busca el sticker de la sección (con o sin icono)."""
    key = normalize_key(section_text)
    if not key:
        return None
    folder = SECCIONES_ICONO_DIR if with_icon else SECCIONES_DIR
    return find_in_dir(folder, key)


def find_fondo(fondo_name):
    """Busca el fondo por nombre."""
    if not fondo_name:
        return None
    return find_in_dir(FONDOS_DIR, normalize_key(fondo_name))


def load_font(size, bold=True):
    """Carga fuente del sistema con fallbacks."""
    candidates_bold = [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]
    candidates_reg = [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for path in (candidates_bold if bold else candidates_reg):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def trim_transparent(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def upscale_image_url(url):
    """Genera URLs candidatas de mayor calidad."""
    candidates = []
    if "/resizer/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        hd = {**{k: v[0] for k, v in params.items()}, "width": "2400", "quality": "95", "smart": "true"}
        hd.pop("height", None)
        candidates.append(urlunparse(parsed._replace(query=urlencode(hd))))
        md = {**hd, "width": "1600"}
        candidates.append(urlunparse(parsed._replace(query=urlencode(md))))
    elif "/image/upload/" in url and "cloudinary" in url:
        candidates.append(re.sub(r"/image/upload/[^/]*?/", "/image/upload/w_2400,q_95,c_fill/", url, count=1))
    elif "wp-content/uploads" in url:
        orig = re.sub(r"-\d+x\d+(\.[a-z]+)$", r"\1", url)
        if orig != url:
            candidates.append(orig)
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        new_params = {k: v[0] for k, v in params.items()}
        modified = False
        for key in ("width", "w", "size"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 2000:
                        new_params[key] = "2400"
                        modified = True
                except ValueError:
                    pass
        for key in ("quality", "q"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 90:
                        new_params[key] = "95"
                        modified = True
                except ValueError:
                    pass
        for key in ("height", "h"):
            if key in new_params:
                new_params.pop(key)
                modified = True
        if modified:
            new_url = urlunparse(parsed._replace(query=urlencode(new_params)))
            if new_url not in candidates:
                candidates.append(new_url)
    candidates.append(url)
    return candidates


def fetch_image(url):
    """Descarga imagen con mejor calidad disponible."""
    candidates = upscale_image_url(url)
    last_err = None
    for u in candidates:
        try:
            r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"})
            if r.status_code == 200 and len(r.content) > 1000:
                img = Image.open(BytesIO(r.content)).convert("RGB")
                if img.width >= 400 and img.height >= 400:
                    return img
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise Exception("No se pudo descargar la imagen")


def cover_resize(img, target_size, zoom=1.0, offset_x=0.5, offset_y=0.5):
    """Cover resize con zoom y offsets."""
    tw, th = target_size
    iw, ih = img.size
    cover_scale = max(tw / iw, th / ih)
    final_scale = cover_scale * max(zoom, 1.0)
    nw, nh = int(iw * final_scale), int(ih * final_scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    max_left, max_top = nw - tw, nh - th
    left = max(0, min(int(max_left * offset_x), max_left))
    top = max(0, min(int(max_top * offset_y), max_top))
    return img.crop((left, top, left + tw, top + th))


def paste_asset(canvas, asset_path, target_height=None, target_width=None,
                position=(0, 0), anchor="top-left"):
    """Pega un PNG con transparencia."""
    if not asset_path or not os.path.exists(asset_path):
        return canvas
    asset = Image.open(asset_path).convert("RGBA")
    asset = trim_transparent(asset)
    if target_height:
        ratio = target_height / asset.height
        new_w = int(asset.width * ratio)
        asset = asset.resize((new_w, target_height), Image.LANCZOS)
    elif target_width:
        ratio = target_width / asset.width
        new_h = int(asset.height * ratio)
        asset = asset.resize((target_width, new_h), Image.LANCZOS)
    aw, ah = asset.size
    x, y = position
    if anchor == "top-left":
        px, py = x, y
    elif anchor == "top-right":
        px, py = x - aw, y
    elif anchor == "bottom-left":
        px, py = x, y - ah
    elif anchor == "bottom-right":
        px, py = x - aw, y - ah
    elif anchor == "center":
        px, py = x - aw // 2, y - ah // 2
    else:
        px, py = x, y
    rgba = canvas.convert("RGBA")
    rgba.paste(asset, (int(px), int(py)), asset)
    return rgba.convert("RGB")


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], []
    for w in words:
        test = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


def fit_title_font(draw, title, max_width, max_lines,
                   size_start=58, size_min=36, size_step=2, bold=True):
    for size in range(size_start, size_min - 1, -size_step):
        font = load_font(size, bold=bold)
        lines = wrap_text(title, font, max_width, draw)
        if len(lines) <= max_lines:
            return font, lines
    font = load_font(size_min, bold=bold)
    lines = wrap_text(title, font, max_width, draw)[:max_lines]
    if lines and not lines[-1].endswith("..."):
        lines[-1] = lines[-1].rsplit(" ", 1)[0] + "..."
    return font, lines


def draw_text_lines(draw, lines, font, x, y, color, line_spacing=1.25):
    lh_bbox = draw.textbbox((0, 0), "Ag", font=font)
    lh = (lh_bbox[3] - lh_bbox[1]) * line_spacing
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        ly = int(y + i * lh - bbox[1])
        draw.text((x, ly), line, font=font, fill=color)
    return int(lh * len(lines))


def add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82, max_alpha=200):
    """Gradiente oscuro concentrado en área del título."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    top = int(h * top_frac)
    bottom = int(h * bottom_frac)
    for y in range(top, bottom):
        alpha = int(max_alpha * ((y - top) / (bottom - top)) ** 1.2)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    for y in range(bottom, h):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, max_alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_section_badge(canvas, section_text, position, font, with_icon=False):
    """
    Dibuja el sticker/badge de sección.

    Busca primero en assets/secciones-icono/ o assets/secciones/ según with_icon.
    Si no encuentra el PNG, dibuja un badge básico con fondo rojo.

    Returns: (canvas, badge_width, badge_height)
    """
    x, y = position
    sticker_path = find_section_sticker(section_text, with_icon=with_icon)

    if sticker_path:
        sticker = Image.open(sticker_path).convert("RGBA")
        sticker = trim_transparent(sticker)
        target_h = int(font.size * 1.7)
        ratio = target_h / sticker.height
        new_w = int(sticker.width * ratio)
        sticker = sticker.resize((new_w, target_h), Image.LANCZOS)
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(sticker, (int(x), int(y)), sticker)
        return canvas_rgba.convert("RGB"), new_w, target_h

    # Fallback: badge básico con fondo rojo
    draw = ImageDraw.Draw(canvas)
    text = (section_text or "").upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 22, 14
    badge_w = text_w + pad_x * 2
    badge_h = text_h + pad_y * 2
    draw.rectangle([x, y, x + badge_w, y + badge_h], fill=RED)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=WHITE)
    return canvas, badge_w, badge_h


def _logo_path(color="blanco"):
    """Resuelve la ruta del logo EE según color ('blanco' o 'negro')."""
    return os.path.join(LOGOS_DIR, f"ee-{color}.png")


def _social_icons_path(color="blanco"):
    """Resuelve la ruta de los iconos de acciones IG según color."""
    return os.path.join(GRAFICOS_DIR, f"acciones-ig-{color}.png")


def _cta_path(color="blanco"):
    """Resuelve la ruta del CTA PNG según color."""
    return os.path.join(GRAFICOS_DIR, f"cta-{color}.png")


def draw_cta_inline(draw, position, font, canvas_size):
    """
    Dibuja el CTA '→ Lea la noticia completa en elespectador.com' usando texto
    cuando no existe el PNG de CTA. Retorna (width, height).
    """
    x, y = position
    text_normal = "Lea la noticia completa en "
    text_bold = "elespectador.com"

    bbox_n = draw.textbbox((0, 0), text_normal, font=font)
    text_w_n = bbox_n[2] - bbox_n[0]
    text_h = bbox_n[3] - bbox_n[1]

    bold_font = load_font(font.size, bold=True)
    bbox_b = draw.textbbox((0, 0), text_bold, font=bold_font)
    text_w_b = bbox_b[2] - bbox_b[0]

    arrow_w = 30
    arrow_gap = 14
    pad_x, pad_y = 18, 12

    total_text_w = arrow_w + arrow_gap + text_w_n + text_w_b
    box_w = total_text_w + pad_x * 2
    box_h = text_h + pad_y * 2

    try:
        draw.rounded_rectangle(
            [x, y, x + box_w, y + box_h],
            radius=6,
            outline=RED, width=3, fill=WHITE,
        )
    except AttributeError:
        draw.rectangle([x, y, x + box_w, y + box_h], outline=RED, width=3, fill=WHITE)

    # Flecha roja
    arrow_x = x + pad_x
    arrow_y = y + box_h // 2
    draw.line([(arrow_x, arrow_y), (arrow_x + arrow_w - 6, arrow_y)], fill=RED, width=3)
    arrow_tip = [
        (arrow_x + arrow_w - 6, arrow_y),
        (arrow_x + arrow_w - 14, arrow_y - 7),
        (arrow_x + arrow_w - 14, arrow_y + 7),
    ]
    draw.polygon(arrow_tip, fill=RED)

    # Texto
    text_x = arrow_x + arrow_w + arrow_gap
    text_y = y + pad_y - bbox_n[1]
    draw.text((text_x, text_y), text_normal, font=font, fill=BLACK)
    draw.text((text_x + text_w_n, text_y), text_bold, font=bold_font, fill=BLACK)

    return box_w, box_h


def _paste_cta(canvas, margin_x, footer_y, canvas_w, text_color, draw_fallback=None):
    """
    Intenta pegar el CTA PNG. Si no existe, usa draw_fallback (draw objeto) para
    dibujar el CTA inline. Si draw_fallback es None, omite el CTA sin imagen.
    """
    color = "blanco" if text_color == WHITE else "negro"
    cta_file = _cta_path(color)
    if os.path.exists(cta_file):
        cta_w = int(canvas_w * 0.65)
        canvas = paste_asset(
            canvas, cta_file,
            target_width=cta_w,
            position=(margin_x, footer_y),
            anchor="bottom-left",
        )
    elif draw_fallback is not None:
        cta_font = load_font(22, bold=False)
        draw_cta_inline(draw_fallback, (margin_x, footer_y - 60), cta_font, (canvas_w, footer_y))
    return canvas


def _paste_logo(canvas, canvas_w, footer_y, canvas_h, text_color):
    """Pega el logo EE en la esquina inferior derecha."""
    color = "blanco" if text_color == WHITE else "negro"
    logo_file = _logo_path(color)
    logo_h = int(canvas_h * 0.06)
    margin_x = int(canvas_w * 0.06)
    return paste_asset(
        canvas, logo_file,
        target_height=logo_h,
        position=(canvas_w - margin_x, footer_y),
        anchor="bottom-right",
    )


def _paste_social_icons(canvas, margin_x, footer_y, canvas_h, text_color):
    """Pega los iconos de acciones IG en la esquina inferior izquierda."""
    color = "blanco" if text_color == WHITE else "negro"
    icons_file = _social_icons_path(color)
    icons_h = int(canvas_h * 0.05)
    return paste_asset(
        canvas, icons_file,
        target_height=icons_h,
        position=(margin_x, footer_y),
        anchor="bottom-left",
    )


# ============================================================
# PLANTILLA 1: CLASSIC
# Foto sangrada + gradiente oscuro + título blanco + iconos sociales + logo EE
# ============================================================

def render_classic(source_image, section, title,
                   format_key="post", seccion_con_icono=False,
                   zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    footer_y = canvas_h - int(canvas_h * 0.044)
    img = _paste_social_icons(img, margin_x, footer_y, canvas_h, WHITE)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)

    return img


# ============================================================
# PLANTILLA 2: CARD
# Fondo gris + foto enmarcada + título en negro + logo EE oscuro
# ============================================================

def render_card(source_image, section, title,
                format_key="post", seccion_con_icono=False,
                zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = Image.new("RGB", (canvas_w, canvas_h), GRAY_BG)

    draw = ImageDraw.Draw(canvas)
    badge_font = load_font(28, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Foto enmarcada
    photo_top = int(canvas_h * 0.104)
    photo_left = margin_x
    photo_right = canvas_w - margin_x
    photo_bottom = int(canvas_h * 0.607)
    photo_w = photo_right - photo_left
    photo_h = photo_bottom - photo_top

    photo = cover_resize(source_image, (photo_w, photo_h), zoom, offset_x, offset_y)
    canvas.paste(photo, (photo_left, photo_top))

    # Título en negro debajo de la foto
    title_max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(
        draw, title, max_width=title_max_w,
        max_lines=3 if format_key == "post" else 4,
        size_start=56, size_min=42,
    )

    line_y_start = photo_bottom + int(canvas_h * 0.037)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, line_y_start, margin_x + 6, line_y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, line_y_start, BLACK)

    # Iconos sociales y logo en negro (fondo claro)
    footer_y = canvas_h - int(canvas_h * 0.044)
    canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, BLACK)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, BLACK)

    return canvas


# ============================================================
# PLANTILLA 3: WITH_CTA
# Como classic + CTA "Lea la noticia completa..." en footer
# ============================================================

def render_with_cta(source_image, section, title,
                    format_key="post", seccion_con_icono=False,
                    zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.50, bottom_frac=0.80, max_alpha=210)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=54)

    # Reservar espacio para CTA + logo debajo del título
    cta_reserved = int(canvas_h * 0.148)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - cta_reserved - total_h - int(canvas_h * 0.022)

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(img)  # re-crear draw si paste_asset convirtió a RGB
    img = _paste_cta(img, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)

    return img


# ============================================================
# PLANTILLA 4: ATTENTION
# Foto arriba + bloque morado sólido abajo + título blanco + CTA
# ============================================================

def render_attention(source_image, section, title,
                     format_key="post", seccion_con_icono=False,
                     zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    # Foto cubre todo el canvas al fondo
    photo_full = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = photo_full.convert("RGBA")

    # Bloque morado con degradado (transición foto → morado)
    photo_h = int(canvas_h * 0.62)
    block_height = canvas_h - photo_h
    transition_height = int(block_height * 0.40)

    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    for i in range(transition_height):
        progress = i / transition_height
        alpha = int(255 * (progress ** 0.85))
        y = photo_h + i
        draw_overlay.line([(0, y), (canvas_w, y)],
                          fill=(PURPLE[0], PURPLE[1], PURPLE[2], alpha))

    draw_overlay.rectangle(
        [0, photo_h + transition_height, canvas_w, canvas_h],
        fill=(PURPLE[0], PURPLE[1], PURPLE[2], 255)
    )

    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    # Badge de sección sobre el bloque morado
    badge_y = photo_h + int(block_height * 0.06)
    badge_font = load_font(30, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, badge_y), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Título blanco
    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=50)

    title_y = badge_y + int(block_height * 0.18)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_y, margin_x + 6, title_y + total_h], fill=WHITE)
    draw_text_lines(draw, lines, title_font, margin_x + 26, title_y, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(canvas)
    canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, WHITE)

    return canvas


# ============================================================
# RENDER GENÉRICO (del script v2, adaptado a las nuevas plantillas)
# ============================================================

def render_generic(source_image, section, title,
                   format_key="post", fondo_name="ultima-hora",
                   seccion_con_icono=False, show_cta=False,
                   show_social_icons=True,
                   zoom=1.0, offset_x=0.5, offset_y=0.5):
    """
    Render con fondo/degradado PNG de assets/fondos/.
    Versión original del script v2.
    """
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = canvas.convert("RGBA")

    bg_path = find_fondo(fondo_name)
    if bg_path:
        overlay = Image.open(bg_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, overlay)

    canvas = canvas.convert("RGB")

    text_area_top = int(canvas_h * 0.62)
    text_area_h = canvas_h - text_area_top

    # Sticker de sección
    sticker_y = text_area_top + int(text_area_h * 0.10)
    sticker_h = int(canvas_h * 0.05) if format_key == "post" else int(canvas_h * 0.04)
    badge_font = load_font(28, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, sticker_y), badge_font, seccion_con_icono)

    # Título
    title_top = sticker_y + sticker_h + int(canvas_h * 0.025)
    title_max_w = canvas_w - margin_x * 2 - 30
    reserved_bottom = int(canvas_h * 0.14) if (show_cta or show_social_icons) else int(canvas_h * 0.10)
    max_title_h = canvas_h - title_top - reserved_bottom
    line_h_approx = 60 if format_key == "post" else 65
    max_lines = max(3, max_title_h // line_h_approx)

    draw = ImageDraw.Draw(canvas)
    title_font, lines = fit_title_font(
        draw, title, title_max_w, max_lines=max_lines,
        size_start=48 if format_key == "post" else 54,
        size_min=32,
    )

    # Detectar color de texto según luminosidad del área
    sample_area = canvas.crop((0, title_top, canvas_w, min(canvas_h, title_top + 200)))
    bg_sample = np.array(sample_area.resize((50, 50))).mean()
    title_color = WHITE if bg_sample < 128 else BLACK

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    title_total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_top, margin_x + 6, title_top + title_total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26 + 6, title_top, title_color)

    footer_y = canvas_h - int(canvas_h * 0.04)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, title_color)

    if show_cta:
        canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, title_color, draw_fallback=draw)
    elif show_social_icons:
        canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, title_color)

    return canvas


# ============================================================
# API PÚBLICA
# ============================================================

def generate_card_from_image(
    source_image,
    section,
    title,
    template="classic",            # "classic" | "card" | "with_cta" | "attention" | "generic"
    format_key="post",             # "post" | "story"
    fondo_name=None,               # para template="generic", nombre del fondo a usar
    seccion_con_icono=False,       # True = usar sticker con icono
    show_cta=False,                # solo para template="generic"
    show_social_icons=True,        # solo para template="generic"
    zoom=1.0,
    offset_x=0.5,
    offset_y=0.5,
    output_path=None,
):
    """
    Genera la tarjeta usando la plantilla seleccionada.

    Args:
        template:   "classic" | "card" | "with_cta" | "attention" | "generic"
        format_key: "post" (1080x1350) | "story" (1080x1920)
        fondo_name: solo para template "generic". Si es None se autodetecta por sección.
        seccion_con_icono: True para usar sticker con icono de la sección.
        show_cta:   solo para template "generic".
        show_social_icons: solo para template "generic".
        zoom, offset_x, offset_y: control de encuadre de la foto.
        output_path: si se especifica, guarda el PNG en esa ruta y devuelve None.

    Returns:
        PIL.Image si output_path es None, o None si se guardó en archivo.
    """
    if format_key not in FORMATS:
        format_key = DEFAULT_FORMAT

    common_kwargs = dict(
        format_key=format_key,
        seccion_con_icono=seccion_con_icono,
        zoom=zoom,
        offset_x=offset_x,
        offset_y=offset_y,
    )

    if template == "classic":
        img = render_classic(source_image, section, title, **common_kwargs)

    elif template == "card":
        img = render_card(source_image, section, title, **common_kwargs)

    elif template == "with_cta":
        img = render_with_cta(source_image, section, title, **common_kwargs)

    elif template == "attention":
        img = render_attention(source_image, section, title, **common_kwargs)

    elif template == "generic":
        resolved_fondo = fondo_name or suggest_fondo_for_section(section)
        img = render_generic(
            source_image, section, title,
            fondo_name=resolved_fondo,
            show_cta=show_cta,
            show_social_icons=show_social_icons,
            **common_kwargs,
        )

    else:
        valid = list(TEMPLATES.keys()) + ["generic"]
        raise ValueError(f"Plantilla desconocida: '{template}'. Opciones: {valid}")

    if output_path:
        img.save(output_path, "PNG", quality=95)
        return None
    return img


def generate_card(image_url, section, title, **kwargs):
    """Versión que descarga la imagen desde URL primero."""
    source_image = fetch_image(image_url)
    return generate_card_from_image(source_image, section, title, **kwargs)
