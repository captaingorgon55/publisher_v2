"""
app.py - EE Publisher
App que extrae contenido de URLs de El Espectador y genera la tarjeta
estilo plantilla automaticamente.
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from io import BytesIO

from generator import (
    generate_card_from_image,
    fetch_image,
    FORMATS,
    TEMPLATES,
    list_fondos,
    suggest_fondo_for_section,
)

st.set_page_config(page_title="EE Publisher", page_icon=":newspaper:", layout="centered")
st.title("EE Publisher")
st.caption("Pega una URL y obten la tarjeta lista para publicar")


def extract_from_url(url):
    """Extrae titulo, imagen (en mejor calidad posible) y seccion desde cualquier URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            },
            timeout=20,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise Exception(f"No se pudo cargar la URL: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")

    def meta(sel):
        tag = soup.select_one(sel)
        return (tag.get("content", "") if tag else "") or ""

    # ================== Titulo ==================
    title = (
        meta('meta[property="og:title"]')
        or meta('meta[name="twitter:title"]')
        or meta('meta[name="title"]')
        or (soup.title.string if soup.title else "")
        or (soup.h1.get_text() if soup.h1 else "")
    )

    title = title.strip()
    for separator in [" | ", " - "]:
        if separator in title:
            parts = title.rsplit(separator, 1)
            if len(parts[1]) < 40 and not any(c in parts[1] for c in ".?!,;:"):
                title = parts[0].strip()
                break

    # ================== Imagen ==================
    image = ""

    main_img_selectors = [
        "article figure img",
        "article header img",
        "figure.lead img",
        "figure[class*='hero'] img",
        "figure[class*='main'] img",
        "figure[class*='cover'] img",
        ".article-image img",
        ".post-thumbnail img",
        "article img",
        "main img",
    ]

    for selector in main_img_selectors:
        main_img = soup.select_one(selector)
        if main_img:
            srcset = main_img.get("srcset") or main_img.get("data-srcset")
            if srcset:
                best = parse_srcset_max(srcset)
                if best:
                    image = best
                    break
            src = (
                main_img.get("data-src")
                or main_img.get("data-original")
                or main_img.get("data-lazy-src")
                or main_img.get("src")
            )
            if src and not src.startswith("data:"):
                image = src
                break

    if not image:
        image = (
            meta('meta[property="og:image:secure_url"]')
            or meta('meta[property="og:image"]')
            or meta('meta[name="twitter:image"]')
            or meta('meta[name="twitter:image:src"]')
            or meta('link[rel="image_src"]')
        )

    if image:
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            from urllib.parse import urljoin
            image = urljoin(url, image)

    # ================== Seccion ==================
    section = ""

    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        skip = {
            "articulo", "article", "post", "noticia", "noticias",
            "news", "story", "stories", "amp", "video", "videos",
            "blog", "tag", "tags", "categoria", "category",
        }
        for part in parts:
            part_lower = part.lower()
            if part.replace("-", "").isdigit():
                continue
            if part_lower in skip:
                continue
            if len(part) == 4 and part.isdigit() and part.startswith("20"):
                continue
            section = part.replace("-", " ")
            break
    except Exception:
        pass

    if not section:
        section = (
            meta('meta[property="article:section"]')
            or meta('meta[name="section"]')
            or meta('meta[name="category"]')
            or meta('meta[property="article:tag"]')
        )

    if not section:
        breadcrumb = soup.select_one(
            '[class*="breadcrumb"] a, nav.breadcrumb a, ol[itemtype*="BreadcrumbList"] a'
        )
        if breadcrumb:
            section = breadcrumb.get_text(strip=True)

    return {
        "title": title.strip(),
        "image": (image or "").strip(),
        "section": (section or "").upper().strip(),
    }


def parse_srcset_max(srcset):
    if not srcset:
        return None
    best_url = None
    best_width = 0
    for item in srcset.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.rsplit(" ", 1)
        if len(parts) == 2:
            url_part, width_part = parts
            try:
                width = int("".join(c for c in width_part if c.isdigit()))
                if width > best_width:
                    best_width = width
                    best_url = url_part.strip()
            except ValueError:
                pass
        elif len(parts) == 1:
            if not best_url:
                best_url = parts[0].strip()
    return best_url


# =====================================================
# Plantillas disponibles para la UI
# =====================================================

ALL_TEMPLATES = {
    **TEMPLATES,
    "generic": {
        "name": "Generica (fondos PNG)",
        "description": "Usa degradados de assets/fondos/ con deteccion automatica de color",
    },
}

TEMPLATE_FOOTER_INFO = {
    "classic":   "Iconos sociales + logo EE",
    "card":      "Iconos sociales + logo EE",
    "with_cta":  "CTA Lea la noticia + logo EE",
    "attention": "CTA Lea la noticia + logo EE",
    "generic":   "Configurable (ver opciones)",
}


# =====================================================
# UI
# =====================================================

st.subheader("1. URL del articulo")

col_url, col_reset = st.columns([4, 1])
with col_url:
    url = st.text_input(
        "URL",
        placeholder="https://www.elespectador.com/...",
        label_visibility="collapsed",
    )
with col_reset:
    if st.button("Resetear", use_container_width=True, help="Limpiar todo y empezar de nuevo"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

if st.button("Extraer y generar tarjeta", type="primary", use_container_width=True):
    if not url:
        st.error("Pega una URL primero")
    else:
        try:
            with st.spinner("Extrayendo contenido..."):
                data = extract_from_url(url)
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("img_cache_")]
            for k in keys_to_remove:
                del st.session_state[k]
            st.session_state["data"] = data
            st.session_state["edited"] = False
        except Exception as e:
            st.error(f"Error al extraer: {e}")

if "data" in st.session_state:
    data = st.session_state["data"]

    # ===== PASO 2: Datos editables =====
    st.subheader("2. Datos extraidos (editables)")
    title = st.text_input("Titulo", value=data["title"], key="title_input")
    section = st.text_input("Seccion", value=data["section"], key="section_input")
    image_url = st.text_input("URL de la imagen", value=data["image"], key="image_input")

    data["title"] = title
    data["section"] = section

    if image_url != data.get("image"):
        keys_to_remove = [k for k in st.session_state.keys() if k.startswith("img_cache_")]
        for k in keys_to_remove:
            del st.session_state[k]
    data["image"] = image_url

    # ===== PASO 3: Formato =====
    st.subheader("3. Formato")

    selected_format = st.radio(
        "Formato",
        options=list(FORMATS.keys()),
        format_func=lambda k: FORMATS[k]["name"] + " (" + FORMATS[k]["description"] + ")",
        label_visibility="collapsed",
    )

    # ===== PASO 4: Plantilla =====
    st.subheader("4. Plantilla")

    selected_template = st.radio(
        "Plantilla",
        options=list(ALL_TEMPLATES.keys()),
        format_func=lambda k: ALL_TEMPLATES[k]["name"] + " - " + ALL_TEMPLATES[k]["description"],
        label_visibility="collapsed",
    )

    # ===== PASO 5: Fondo (solo plantilla generic) =====
    selected_fondo = None
    step_offset = 0

    if selected_template == "generic":
        st.subheader("5. Fondo (degradado)")
        step_offset = 1
        fondos = list_fondos()
        if not fondos:
            st.warning("No hay fondos disponibles en assets/fondos/")
        else:
            suggested = suggest_fondo_for_section(section)
            default_idx = fondos.index(suggested) if suggested in fondos else 0
            st.caption("Sugerencia automatica para '" + (section or "sin seccion") + "': " + str(suggested))
            selected_fondo = st.selectbox(
                "Fondo:",
                options=fondos,
                index=default_idx,
                help="Archivos PNG de assets/fondos/",
            )

    # ===== PASO 5/6: Opciones =====
    st.subheader(str(5 + step_offset) + ". Opciones")

    col_opt1, col_opt2 = st.columns(2)

    with col_opt1:
        seccion_con_icono = st.checkbox(
            "Icono en sticker de seccion",
            value=False,
            help="Usa el sticker con icono (carpeta secciones-icono/)",
        )

    with col_opt2:
        if selected_template == "generic":
            footer_type = st.radio(
                "Footer:",
                options=["Iconos sociales", "CTA Lea la noticia", "Sin nada"],
            )
            show_cta = footer_type == "CTA Lea la noticia"
            show_social_icons = footer_type == "Iconos sociales"
        else:
            st.caption("Footer: " + TEMPLATE_FOOTER_INFO[selected_template])
            show_cta = False
            show_social_icons = False

    # ===== PASO 6/7: Ajustar imagen =====
    st.subheader(str(6 + step_offset) + ". Ajustar imagen")

    if not title or not image_url:
        st.warning("Falta titulo o imagen")
    else:
        cache_key = "img_cache_" + image_url
        if cache_key not in st.session_state:
            with st.spinner("Descargando imagen en alta calidad..."):
                try:
                    st.session_state[cache_key] = fetch_image(image_url)
                except Exception as e:
                    st.error("Error al descargar imagen: " + str(e))
                    st.stop()

        source_img = st.session_state[cache_key]

        st.caption(
            "Imagen: " + str(source_img.width) + " x " + str(source_img.height) + " px"
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            zoom = st.slider("Zoom", 1.0, 3.0, 1.0, 0.05)
        with col2:
            offset_x = st.slider("Horizontal", 0.0, 1.0, 0.5, 0.05)
        with col3:
            offset_y = st.slider("Vertical", 0.0, 1.0, 0.5, 0.05)

        if st.button("Restablecer ajustes"):
            st.rerun()

        # ===== Tarjeta generada =====
        st.subheader(str(7 + step_offset) + ". Tarjeta generada")

        try:
            img = generate_card_from_image(
                source_image=source_img,
                section=section or "NOTICIAS",
                title=title,
                template=selected_template,
                format_key=selected_format,
                fondo_name=selected_fondo,
                seccion_con_icono=seccion_con_icono,
                show_cta=show_cta,
                show_social_icons=show_social_icons,
                zoom=zoom,
                offset_x=offset_x,
                offset_y=offset_y,
            )

            st.image(img, use_column_width=True)

            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            safe_name = "".join(c if c.isalnum() else "-" for c in title.lower())[:50]

            st.download_button(
                label="Descargar PNG (" + FORMATS[selected_format]["name"] + " / " + ALL_TEMPLATES[selected_template]["name"] + ")",
                data=buf,
                file_name=selected_format + "-" + selected_template + "-" + safe_name + ".png",
                mime="image/png",
                use_container_width=True,
                type="primary",
            )

            st.info("Sube este PNG a SocialFlow o donde lo necesites publicar")

        except Exception as e:
            st.error("Error al generar: " + str(e))
            import traceback
            with st.expander("Detalles del error"):
                st.code(traceback.format_exc())