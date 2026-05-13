"""
generator.py - Generador de plantillas estilo El Espectador
Soporta 4 plantillas:
  1. "classic"   - Foto sangrada + titulo blanco con linea roja (original)
  2. "card"      - Foto enmarcada + titulo negro sobre fondo gris claro
  3. "with_cta"  - Como classic pero con CTA "Lea la noticia completa en elespectador.com"
  4. "attention" - Foto + bloque morado solido abajo con titulo y CTA
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import requests
import re
import os
import numpy as np
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ============================================================
# CONSTANTES GLOBALES
# ============================================================
CANVAS_SIZE = (1080, 1350)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
SOCIAL_ICONS_PATH = os.path.join(ASSETS_DIR, "social_icons.png")
LOGO_EE_PATH = os.path.join(ASSETS_DIR, "logo_ee.png")

# Colores
RED = (227, 27, 35)
WHITE = (255, 255, 255)
BLACK = (15, 15, 15)
GRAY_BG = (235, 235, 235)        # fondo de la card en plantilla 2
PURPLE = (66, 28, 87)            # morado plantilla atencion

# Tamanos de logos (compartidos entre plantillas)
LOGO_EE_HEIGHT = 80
SOCIAL_ICONS_HEIGHT = 80


# ============================================================
# UTILIDADES DE IMAGEN
# ============================================================

# ============================================================
# FUENTES
# ============================================================
# ============================================================
# FUENTES
# ============================================================

FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

ABRIL_TITLING_PATH = os.path.join(FONTS_DIR, "abriltitling.ttf")


def load_font(size, bold=True):
    """
    Usa Abril Titling como fuente principal.
    """

    # ========================================================
    # Abril Titling
    # ========================================================

    if os.path.exists(ABRIL_TITLING_PATH):
        try:
            return ImageFont.truetype(ABRIL_TITLING_PATH, size)
        except Exception:
            pass

    # ========================================================
    # Fallback del sistema
    # ========================================================

    fallback_candidates = [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]

    for path in fallback_candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def upscale_image_url(url):
    """Reescribe URLs de CDNs para pedir mayor resolucion."""
    candidates = []

    if "/resizer/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params_hd = {**{k: v[0] for k, v in params.items()}, "width": "2400", "quality": "95", "smart": "true"}
        params_hd.pop("height", None)
        candidates.append(urlunparse(parsed._replace(query=urlencode(params_hd))))
        params_md = {**params_hd, "width": "1600"}
        candidates.append(urlunparse(parsed._replace(query=urlencode(params_md))))
    elif "/image/upload/" in url and "cloudinary" in url:
        candidates.append(re.sub(r"/image/upload/[^/]*?/", "/image/upload/w_2400,q_95,c_fill/", url, count=1))
    elif "wp-content/uploads" in url:
        url_orig = re.sub(r"-\d+x\d+(\.[a-z]+)$", r"\1", url)
        if url_orig != url:
            candidates.append(url_orig)

    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        modified = False
        new_params = {k: v[0] for k, v in params.items()}
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
    """Descarga la imagen con la mejor calidad disponible."""
    candidates = upscale_image_url(url)
    last_error = None
    for candidate_url in candidates:
        try:
            resp = requests.get(
                candidate_url, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            if resp.status_code == 200 and len(resp.content) > 1000:
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                if img.width >= 400 and img.height >= 400:
                    return img
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise Exception("No se pudo descargar la imagen")


def cover_resize(img, target_size, zoom=1.0, offset_x=0.5, offset_y=0.5):
    """Cover resize con zoom y offsets."""
    target_w, target_h = target_size
    img_w, img_h = img.size
    cover_scale = max(target_w / img_w, target_h / img_h)
    final_scale = cover_scale * max(zoom, 1.0)
    new_w = int(img_w * final_scale)
    new_h = int(img_h * final_scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    max_left = new_w - target_w
    max_top = new_h - target_h
    left = max(0, min(int(max_left * offset_x), max_left))
    top = max(0, min(int(max_top * offset_y), max_top))
    return img.crop((left, top, left + target_w, top + target_h))


def trim_transparent(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def paste_asset(canvas, asset_path, target_height, position, anchor="bottom-left"):
    """Pega un PNG con transparencia."""
    if not os.path.exists(asset_path):
        return canvas
    asset = Image.open(asset_path).convert("RGBA")
    asset = trim_transparent(asset)
    ratio = target_height / asset.height
    new_w = int(asset.width * ratio)
    asset = asset.resize((new_w, target_height), Image.LANCZOS)

    x, y = position
    if anchor == "bottom-left":
        paste_x, paste_y = x, y - target_height
    elif anchor == "bottom-right":
        paste_x, paste_y = x - new_w, y - target_height
    elif anchor == "top-right":
        paste_x, paste_y = x - new_w, y
    else:
        paste_x, paste_y = x, y

    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.paste(asset, (paste_x, paste_y), asset)
    return canvas_rgba.convert("RGB"), (paste_x, paste_y, new_w, target_height)


def wrap_text(text, font, max_width, draw):
    """Envuelve texto en multiples lineas."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def fit_title_font(draw, title, max_width, max_lines, bold=True,
                   size_start=58, size_min=36, size_step=2):
    """Encuentra el tamano de fuente adecuado para que el titulo quepa en max_lines."""
    for size in range(size_start, size_min - 1, -size_step):
        font = load_font(size, bold=bold)
        lines = wrap_text(title, font, max_width, draw)
        if len(lines) <= max_lines:
            return font, lines
    # Si no cabe, truncar con el tamano minimo
    font = load_font(size_min, bold=bold)
    lines = wrap_text(title, font, max_width, draw)[:max_lines]
    if lines and not lines[-1].endswith("..."):
        lines[-1] = lines[-1].rsplit(" ", 1)[0] + "..."
    return font, lines


def draw_lines(draw, lines, font, x, y, color, line_spacing=1.25):
    """Dibuja un bloque de texto multilinea."""
    line_height_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = (line_height_bbox[3] - line_height_bbox[1]) * line_spacing
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        ly = int(y + i * line_h - bbox[1])
        draw.text((x, ly), line, font=font, fill=color)
    return int(line_h * len(lines))


def normalize_section_key(section_text):
    """
    Convierte texto de seccion en clave normalizada para match.
    Quita acentos, pone minusculas, y deja guiones (-) o guiones bajos (_) como separadores.

    Ejemplos:
        "POLÍTICA"       -> "politica"
        "Última Hora"    -> "ultima-hora"
        "Colombia +20"   -> "colombia-20"
        "Magazín Cultural" -> "magazin-cultural"
    """
    import unicodedata
    s = section_text.lower().strip()
    # Remover acentos
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # Reemplazar "+" por espacio
    s = s.replace("+", " ")
    # Cualquier cosa que no sea letra/digito -> guion
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


SECTIONS_DIR = os.path.join(ASSETS_DIR, "sections")


def find_section_banner(section_text):
    """
    Busca el archivo PNG del banner completo de la seccion en assets/sections/.
    El PNG debe contener el banner entero (fondo rojo + texto + icono).

    Estrategias de match (en orden):
    1. Match exacto: politica -> politica.png
    2. Match con guion/guion-bajo intercambiables: ultima-hora -> ultima_hora.png
    3. Match parcial
    """
    if not section_text or not os.path.exists(SECTIONS_DIR):
        return None

    key = normalize_section_key(section_text)
    if not key:
        return None

    files = [f for f in os.listdir(SECTIONS_DIR) if f.lower().endswith(".png")]
    if not files:
        return None

    # 1. Match exacto
    for f in files:
        if f[:-4].lower() == key:
            return os.path.join(SECTIONS_DIR, f)

    # 2. Probar intercambiando _ <-> -
    key_alt1 = key.replace("-", "_")
    key_alt2 = key.replace("_", "-")
    for f in files:
        name = f[:-4].lower()
        if name == key_alt1 or name == key_alt2:
            return os.path.join(SECTIONS_DIR, f)

    # 3. Normalizar el nombre de archivo y comparar
    for f in files:
        name_normalized = re.sub(r"[^a-z0-9]+", "-", f[:-4].lower()).strip("-")
        if name_normalized == key:
            return os.path.join(SECTIONS_DIR, f)

    # 4. Match parcial
    for f in files:
        name = re.sub(r"[^a-z0-9]+", "-", f[:-4].lower()).strip("-")
        if name.startswith(key + "-") or name.endswith("-" + key):
            return os.path.join(SECTIONS_DIR, f)
        if key.startswith(name + "-") or key.endswith("-" + name):
            return os.path.join(SECTIONS_DIR, f)

    return None


# Alias hacia atras por compatibilidad
find_section_icon = find_section_banner


def draw_section_badge(canvas, section_text, position, font, with_icon=True):
    """
    Pega el banner de seccion (PNG completo) en el canvas.

    El archivo PNG ya contiene todo: fondo rojo, texto, icono.
    Solo hay que pegarlo en la posicion correcta.

    Si NO encuentra el PNG, dibuja un badge basico solo con texto
    (fallback para no romper si falta un icono).

    Args:
        canvas: PIL Image RGB donde dibujar
        section_text: texto de la seccion (ej "POLITICA")
        position: (x, y) esquina superior izquierda donde pegar el banner
        font: fuente del texto (solo se usa si no hay PNG, para el fallback)
        with_icon: si False, fuerza el fallback de solo texto

    Returns: (canvas modificado, banner_width, banner_height)
    """
    x, y = position

    # Buscar archivo PNG del banner
    banner_path = find_section_icon(section_text) if with_icon else None

    if banner_path:
        # Pegar el banner tal cual, redimensionando a una altura estandar
        banner = Image.open(banner_path).convert("RGBA")
        banner = trim_transparent(banner)

        # Altura objetivo del banner: proporcional al tamano de fuente solicitado
        target_h = int(font.size * 1.7)  # mas compacto
        ratio = target_h / banner.height
        new_w = int(banner.width * ratio)
        banner = banner.resize((new_w, target_h), Image.LANCZOS)

        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(banner, (int(x), int(y)), banner)
        canvas = canvas_rgba.convert("RGB")

        return canvas, new_w, target_h

    # ===== Fallback: dibujar badge basico solo con texto =====
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), section_text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = 22, 14
    badge_w = text_w + pad_x * 2
    badge_h = text_h + pad_y * 2

    draw.rectangle([x, y, x + badge_w, y + badge_h], fill=RED)

    text_x = x + pad_x
    text_y = y + pad_y - bbox[1]
    draw.text((text_x, text_y), section_text, font=font, fill=WHITE)

    return canvas, badge_w, badge_h


def add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82, max_alpha=200):
    """Gradiente oscuro corto, concentrado en area del titulo."""
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


def draw_cta_box(draw, position, font, canvas_size):
    """
    Dibuja el CTA "→ Lea la noticia completa en elespectador.com"
    con un recuadro fino rojo redondeado.
    Retorna (width, height) del bloque dibujado.
    """
    x, y = position
    text_normal = "Lea la noticia completa en "
    text_bold = "elespectador.com"

    # Medir
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

    # Recuadro con borde rojo (rectangulo con esquinas ligeramente redondeadas)
    try:
        draw.rounded_rectangle(
            [x, y, x + box_w, y + box_h],
            radius=6,
            outline=RED, width=3, fill=WHITE,
        )
    except AttributeError:
        # Pillow viejo no tiene rounded_rectangle
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


# ============================================================
# PLANTILLA 1: CLASSIC (la original)
# Foto sangrada + titulo blanco con linea roja + iconos sociales + logo EE
# ============================================================
def render_classic(source_image, section, title, zoom=1.0, offset_x=0.5, offset_y=0.5):
    img = cover_resize(source_image, CANVAS_SIZE, zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82)
    canvas_w, canvas_h = CANVAS_SIZE
    draw = ImageDraw.Draw(img)

    # Badge
    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (60, 60), badge_font)
    draw = ImageDraw.Draw(img)  # recrear draw despues de paste

    # Titulo
    max_w = canvas_w - 80 - 6 - 20 - 100
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4)

    line_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (line_bbox[3] - line_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - 220 - total_h

    # Linea roja
    draw.rectangle([80, y_start, 86, y_start + total_h], fill=RED)
    draw_lines(draw, lines, title_font, 106, y_start, WHITE)

    # Footer
    footer_y = canvas_h - 60             # mas pegado al borde inferior
    img, _ = paste_asset(img, SOCIAL_ICONS_PATH, SOCIAL_ICONS_HEIGHT, (75, footer_y), "bottom-left")
    img, _ = paste_asset(img, LOGO_EE_PATH, LOGO_EE_HEIGHT, (canvas_w - 60, footer_y), "bottom-right")

    return img


# ============================================================
# PLANTILLA 2: CARD (foto enmarcada)
# Fondo gris, badge con punto blanco arriba, foto recuadrada, titulo en negro
# ============================================================
def render_card(source_image, section, title, zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = CANVAS_SIZE
    canvas = Image.new("RGB", CANVAS_SIZE, GRAY_BG)
    draw = ImageDraw.Draw(canvas)

    # Badge arriba
    badge_font = load_font(28, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (60, 60), badge_font)
    draw = ImageDraw.Draw(canvas)

    # Foto recuadrada
    photo_top = 140
    photo_left = 60
    photo_right = canvas_w - 60
    photo_bottom = 820
    photo_w = photo_right - photo_left
    photo_h = photo_bottom - photo_top

    photo = cover_resize(source_image, (photo_w, photo_h), zoom, offset_x, offset_y)
    canvas.paste(photo, (photo_left, photo_top))

    # Titulo en negro debajo de la foto
    title_font, lines = fit_title_font(
        draw, title,
        max_width=canvas_w - 80 - 6 - 20 - 80,
        max_lines=3,
        size_start=56, size_min=42,
    )

    # Linea roja a la izquierda del titulo
    line_y_start = photo_bottom + 50
    line_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (line_bbox[3] - line_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([80, line_y_start, 86, line_y_start + total_h], fill=RED)
    draw_lines(draw, lines, title_font, 106, line_y_start, BLACK)

    # Footer: iconos sociales abajo izquierda + EE abajo derecha
    # Como el fondo es claro, los iconos blancos no se verian. Hay que pintarlos en oscuro.
    # Solucion: invertir el alpha (no es lo ideal pero funciona)
    footer_y = canvas_h - 60

    # Iconos: cargar y pintarlos en negro
    if os.path.exists(SOCIAL_ICONS_PATH):
        icons = Image.open(SOCIAL_ICONS_PATH).convert("RGBA")
        icons = trim_transparent(icons)
        # Crear version negra: usar alpha de la imagen original
        import numpy as np
        arr = np.array(icons)
        # Donde hay alpha, poner negro
        black_icons = np.zeros_like(arr)
        black_icons[:, :, 3] = arr[:, :, 3]  # mantener alpha
        # RGB en negro
        black_icons[:, :, 0:3] = 30
        icons_black = Image.fromarray(black_icons, mode="RGBA")

        ratio = SOCIAL_ICONS_HEIGHT / icons_black.height
        new_w = int(icons_black.width * ratio)
        icons_black = icons_black.resize((new_w, SOCIAL_ICONS_HEIGHT), Image.LANCZOS)

        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(icons_black, (75, footer_y - SOCIAL_ICONS_HEIGHT), icons_black)
        canvas = canvas_rgba.convert("RGB")

    # EE logo - sus letras son blancas, no se veran sobre gris claro
    # Hay que pintar el logo en negro tambien. Pero el logo ya tiene la barrita roja
    # asi que mejor solucion: hacer una version invertida del logo donde el blanco se vuelve negro
    if os.path.exists(LOGO_EE_PATH):
        import numpy as np
        logo = Image.open(LOGO_EE_PATH).convert("RGBA")
        logo = trim_transparent(logo)
        arr = np.array(logo)

        # Mantener alpha. Donde RGB era blanco (~255,255,255), volverlo negro
        # Donde era rojo, dejarlo rojo
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        white_mask = (r > 200) & (g > 200) & (b > 200) & (a > 50)
        arr[white_mask, 0:3] = [30, 30, 30]  # blanco -> negro
        logo_inverted = Image.fromarray(arr, mode="RGBA")

        ratio = LOGO_EE_HEIGHT / logo_inverted.height
        new_w = int(logo_inverted.width * ratio)
        logo_inverted = logo_inverted.resize((new_w, LOGO_EE_HEIGHT), Image.LANCZOS)

        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(logo_inverted, (canvas_w - 75 - new_w, footer_y - LOGO_EE_HEIGHT), logo_inverted)
        canvas = canvas_rgba.convert("RGB")

    return canvas


# ============================================================
# PLANTILLA 3: WITH_CTA
# Como classic + CTA "Lea la noticia completa..." abajo izquierda
# ============================================================
def render_with_cta(source_image, section, title, zoom=1.0, offset_x=0.5, offset_y=0.5):
    img = cover_resize(source_image, CANVAS_SIZE, zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.50, bottom_frac=0.80, max_alpha=210)
    canvas_w, canvas_h = CANVAS_SIZE
    draw = ImageDraw.Draw(img)

    badge_font = load_font(30, bold=True)
    img, _, _ = draw_section_badge(img, section.upper(), (60, 60), badge_font)
    draw = ImageDraw.Draw(img)

    # Titulo
    max_w = canvas_w - 80 - 6 - 20 - 100
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=54)

    # Posicion del titulo: dejar espacio para el CTA abajo
    cta_height_reserved = 200  # espacio para CTA + logos
    line_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (line_bbox[3] - line_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - cta_height_reserved - total_h - 30

    draw.rectangle([80, y_start, 86, y_start + total_h], fill=RED)
    draw_lines(draw, lines, title_font, 106, y_start, WHITE)

    # CTA
    cta_font = load_font(22, bold=False)
    cta_y = canvas_h - 130
    draw_cta_box(draw, (80, cta_y), cta_font, CANVAS_SIZE)

    # Logo EE solo (sin iconos sociales en esta plantilla)
    footer_y = canvas_h - 60
    img, _ = paste_asset(img, LOGO_EE_PATH, LOGO_EE_HEIGHT, (canvas_w - 60, footer_y), "bottom-right")

    return img


# ============================================================
# PLANTILLA 4: ATTENTION
# Foto + bloque morado solido abajo (no gradiente) + badge + titulo + CTA
# ============================================================
def render_attention(source_image, section, title, zoom=1.0, offset_x=0.5, offset_y=0.5):
    canvas_w, canvas_h = CANVAS_SIZE

    # Foto que cubre todo el canvas (al fondo)
    photo_full = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = photo_full.convert("RGBA")

    # ===== Bloque morado con degradado =====
    # Empieza en photo_h (donde antes terminaba la foto) y va hasta abajo
    photo_h = int(canvas_h * 0.62)
    block_top = photo_h
    block_bottom = canvas_h
    block_height = block_bottom - block_top

    # Zona de transicion: ~40% del bloque para una transicion mas suave
    transition_height = int(block_height * 0.40)

    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Degradado: de alpha=0 arriba a alpha=255 abajo (en la zona de transicion)
    for i in range(transition_height):
        # Curva exponencial suave para que la mayoria del cambio ocurra rapido
        progress = i / transition_height
        alpha = int(255 * (progress ** 0.85))
        y = block_top + i
        draw_overlay.line(
            [(0, y), (canvas_w, y)],
            fill=(PURPLE[0], PURPLE[1], PURPLE[2], alpha)
        )

    # Resto del bloque: morado solido
    draw_overlay.rectangle(
        [0, block_top + transition_height, canvas_w, block_bottom],
        fill=(PURPLE[0], PURPLE[1], PURPLE[2], 255)
    )

    # Componer overlay sobre la foto
    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # Badge "ATENCION" sobre el bloque morado, parte superior
    badge_y = photo_h + 30
    badge_font = load_font(30, bold=True)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (60, badge_y), badge_font)
    draw = ImageDraw.Draw(canvas)

    # Titulo blanco
    max_w = canvas_w - 80 - 6 - 20 - 80
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=50)

    title_y = badge_y + 90
    line_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (line_bbox[3] - line_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    # Linea blanca a la izquierda del titulo
    draw.rectangle([80, title_y, 86, title_y + total_h], fill=WHITE)
    draw_lines(draw, lines, title_font, 106, title_y, WHITE)

    # CTA + logo EE en el footer
    cta_font = load_font(22, bold=False)
    cta_y = canvas_h - 130
    draw_cta_box(draw, (80, cta_y), cta_font, CANVAS_SIZE)

    footer_y = canvas_h - 60
    canvas, _ = paste_asset(canvas, LOGO_EE_PATH, LOGO_EE_HEIGHT, (canvas_w - 60, footer_y), "bottom-right")

    return canvas


# ============================================================
# REGISTRO DE PLANTILLAS
# ============================================================
TEMPLATES = {
    "classic": {
        "name": "Clasica",
        "description": "Foto a sangre con titulo blanco e iconos sociales",
        "render": render_classic,
    },
    "card": {
        "name": "Card",
        "description": "Foto enmarcada sobre fondo gris claro, titulo en negro",
        "render": render_card,
    },
    "with_cta": {
        "name": "Con CTA",
        "description": "Como Clasica pero con 'Lea la noticia completa...'",
        "render": render_with_cta,
    },
    "attention": {
        "name": "Atencion",
        "description": "Foto arriba + bloque morado solido abajo (alarma)",
        "render": render_attention,
    },
}


# ============================================================
# API PUBLICA
# ============================================================
def generate_card_from_image(
    source_image, section, title,
    template="classic",
    zoom=1.0, offset_x=0.5, offset_y=0.5,
    output_path=None,
):
    """
    Genera la tarjeta usando la plantilla seleccionada.

    Args:
        template: "classic" | "card" | "with_cta" | "attention"
    """
    if template not in TEMPLATES:
        raise ValueError(f"Plantilla desconocida: {template}. Opciones: {list(TEMPLATES.keys())}")

    render_fn = TEMPLATES[template]["render"]
    img = render_fn(source_image, section, title, zoom, offset_x, offset_y)

    if output_path:
        img.save(output_path, "PNG", quality=95)
        return None
    return img


def generate_card(image_url, section, title, template="classic", output_path=None):
    """Version que recibe URL."""
    source_image = fetch_image(image_url)
    return generate_card_from_image(source_image, section, title, template=template, output_path=output_path)
