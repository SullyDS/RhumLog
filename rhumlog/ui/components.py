from __future__ import annotations

import html
from collections.abc import Sequence

import streamlit as st


_ICON_PATHS = {
    "bottle": "<path d='M10 2h4v4l2 2v12H8V8l2-2V2Z'/><path d='M10 6h4'/><path d='M10.5 12h3'/>",
    "cellar": "<path d='M4 7h16v13H4z'/><path d='M7 7V4h10v3'/><path d='M8 11h8'/><path d='M10 14h4'/>",
    "glass": "<path d='M6 3h12l-1.5 7a4.6 4.6 0 0 1-9 0L6 3Z'/><path d='M12 14v7'/><path d='M8.5 21h7'/><path d='M7 8h10'/>",
    "euro": "<path d='M18 6.5A7 7 0 1 0 18 17.5'/><path d='M5 9h9'/><path d='M5 13h8'/>",
    "trend": "<path d='M4 18V6'/><path d='M4 18h16'/><path d='m7 15 4-4 3 2 5-6'/><path d='M16 7h3v3'/>",
    "spark": "<path d='m12 3 1.4 4.1L17 9l-3.6 1.9L12 15l-1.4-4.1L7 9l3.6-1.9L12 3Z'/><path d='m18.5 15 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z'/>",
    "analytics": "<path d='M4 19V9'/><path d='M10 19V5'/><path d='M16 19v-7'/><path d='M22 19H2'/>",
    "quality": "<path d='M12 3 4.5 6v5c0 4.8 3.1 8.3 7.5 10 4.4-1.7 7.5-5.2 7.5-10V6L12 3Z'/><path d='m8.5 12 2.2 2.2 4.8-5'/>",
    "model": "<circle cx='12' cy='12' r='3'/><path d='M12 2v3'/><path d='M12 19v3'/><path d='M2 12h3'/><path d='M19 12h3'/><path d='m5 5 2.1 2.1'/><path d='m16.9 16.9 2.1 2.1'/><path d='m19 5-2.1 2.1'/><path d='m7.1 16.9-2.1 2.1'/>",
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 10v6'/><path d='M12 7h.01'/>",
}


def _svg(name: str, *, size: int = 20) -> str:
    path = _ICON_PATHS.get(name, _ICON_PATHS["spark"])
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" '
        'fill="none" stroke="currentColor" stroke-width="1.55" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{path}</svg>"
    )


def _icon_name(label: str) -> str:
    value = label.casefold()
    if any(word in value for word in ("référence", "bouteille")):
        return "bottle"
    if any(word in value for word in ("en cave", "collection", "acquisition")):
        return "cellar"
    if any(word in value for word in ("dégust", "plaisir", "goût", "aromatique")):
        return "glass"
    if any(word in value for word in ("valeur", "prix", "capital", "€")):
        return "euro"
    if any(word in value for word in ("mae", "spearman", "modèle", "ml", "prédiction")):
        return "model"
    if any(word in value for word in ("qualité", "couverture", "anomal")):
        return "quality"
    if any(word in value for word in ("analytics", "dynamique", "diversité", "profil")):
        return "analytics"
    if any(word in value for word in ("à propos", "architecture", "projet")):
        return "info"
    return "spark"


def hero(title: str, subtitle: str, kicker: str = "MY RUM DATA LABORATORY") -> None:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    safe_kicker = html.escape(kicker)
    title_html = safe_title.replace("RhumLog", "<span>RhumLog</span>")
    st.markdown(
        f"""
<div class="rhum-hero">
  <div class="rhum-hero-orbit" aria-hidden="true"></div>
  <div class="rhum-kicker">{safe_kicker}</div>
  <h1>{title_html}</h1>
  <p>{safe_subtitle}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_title(label: str) -> None:
    icon = _svg(_icon_name(label), size=16)
    st.markdown(
        (
            '<div class="rhum-section-title">'
            f'<span class="rhum-section-icon">{icon}</span>'
            f'<span>{html.escape(label)}</span>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def insight(title: str, body: str, meta: str | None = None) -> None:
    meta_html = f'<div class="rhum-insight-meta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
<div class="rhum-insight">
  <div class="rhum-insight-icon">{_svg("spark", size=17)}</div>
  <div class="rhum-insight-copy">
    <div class="rhum-insight-title">{html.escape(title)}</div>
    <div class="rhum-insight-body">{html.escape(body)}</div>
    {meta_html}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
<div class="rhum-empty">
  <div class="rhum-empty-icon">{_svg("info", size=19)}</div>
  <div>
    <div class="rhum-empty-title">{html.escape(title)}</div>
    <div class="rhum-empty-body">{html.escape(body)}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def stat_grid(
    items: Sequence[tuple[str, str | int | float, str | None]],
    *,
    columns: int | None = None,
) -> None:
    """Affiche une rangée de KPI compacte et cohérente avec le design system."""
    if not items:
        return
    grid_columns = max(1, min(columns or len(items), 6))
    cards = []
    for label, value, note in items:
        note_html = (
            f'<div class="rhum-stat-note">{html.escape(str(note))}</div>'
            if note
            else ""
        )
        icon = _svg(_icon_name(str(label)), size=23)
        cards.append(
            "".join(
                [
                    '<div class="rhum-stat-card">',
                    f'<div class="rhum-stat-icon">{icon}</div>',
                    '<div class="rhum-stat-copy">',
                    f'<div class="rhum-stat-label" title="{html.escape(str(label), quote=True)}">{html.escape(str(label))}</div>',
                    f'<div class="rhum-stat-value" title="{html.escape(str(value), quote=True)}">{html.escape(str(value))}</div>',
                    note_html,
                    "</div>",
                    "</div>",
                ]
            )
        )
    density_class = " rhum-stat-grid--dense" if grid_columns >= 5 else ""
    st.markdown(
        (
            f'<div class="rhum-stat-grid{density_class}" style="--rhum-stat-cols:{grid_columns}">'
            + "".join(cards)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )


def eyebrow(label: str) -> None:
    st.markdown(
        f'<div class="rhum-eyebrow">{html.escape(label)}</div>',
        unsafe_allow_html=True,
    )
