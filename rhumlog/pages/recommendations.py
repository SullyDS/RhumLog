from __future__ import annotations

import html
import math

import plotly.express as px
import streamlit as st

from rhumlog.services.final_model import build_final_model_snapshot
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService
from rhumlog.ui.components import empty_state, hero, section_title, stat_grid
from rhumlog.ui.theme import style_figure


def _chart(fig, *, height: int | None = None) -> None:
    style_figure(fig, height=height)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _table(frame) -> None:
    st.dataframe(
        frame.drop(columns=["Distance min"], errors="ignore"),
        hide_index=True,
        width="stretch",
        column_config={
            "Score prédit": st.column_config.NumberColumn(format="%.2f / 10"),
            "Borne basse indicative": st.column_config.NumberColumn(format="%.2f"),
            "Borne haute indicative": st.column_config.NumberColumn(format="%.2f"),
            "Couverture données (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f %%"
            ),
            "Couverture sensorielle (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f %%"
            ),
            "Confiance extraction": st.column_config.ProgressColumn(
                min_value=0, max_value=1, format="%.0%%"
            ),
            "Prix (€)": st.column_config.NumberColumn(format="%.2f €"),
            "Degré (%)": st.column_config.NumberColumn(format="%.1f %%"),
            "Niveau (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f %%"
            ),
        },
    )


def _format_price(value) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(number):
        return "—"
    return f"{number:.0f} €" if number.is_integer() else f"{number:.1f} €"


def _top_cards(frame, image_lookup: dict[str, str | None]) -> None:
    if frame.empty:
        return

    top = frame.head(3)
    columns = st.columns(len(top), gap="medium")

    for rank, (column, (_, row)) in enumerate(zip(columns, top.iterrows()), start=1):
        with column:
            with st.container(border=True):
                name = str(row["Rhum"])
                image_url = image_lookup.get(name)

                if image_url:
                    _, image_center, _ = st.columns([1, 1.1, 1])
                    with image_center:
                        st.image(image_url, width=78)

                st.markdown(
                    f'<div class="rhum-reco-rank">Choix #{rank}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="rhum-reco-name">{html.escape(name)}</div>',
                    unsafe_allow_html=True,
                )

                score = float(row["Score prédit"])
                st.markdown(
                    (
                        '<div class="rhum-reco-score">'
                        f"{score:.2f}"
                        '<span style="font-size:.85rem;color:#8fa2b3"> / 10</span>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

                low = row.get("Borne basse indicative")
                high = row.get("Borne haute indicative")
                if low is not None and high is not None:
                    st.caption(
                        "Bande empirique indicative · "
                        f"{float(low):.2f} → {float(high):.2f}"
                    )

                origin = html.escape(str(row.get("Origine") or "Origine inconnue"))
                rum_type = html.escape(str(row.get("Type") or "Type inconnu"))
                familiarity = html.escape(str(row.get("Proximité aux données") or "—"))
                coverage = float(row.get("Couverture données (%)") or 0)

                st.markdown(
                    (
                        '<div class="rhum-reco-sub">'
                        f"{origin} · {rum_type}<br>"
                        f"Prix · {_format_price(row.get('Prix (€)'))}<br>"
                        f"Données · {coverage:.0f}% · {familiarity}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )


def _candidate_section(frame, title: str, image_lookup: dict[str, str | None]) -> None:
    section_title(title)
    if frame.empty:
        empty_state(
            "Aucun candidat dans cette vue",
            "Aucune bouteille ne répond actuellement aux critères de cette catégorie. Le moteur reste limité aux données déjà présentes dans RhumLog.",
        )
        return

    _top_cards(frame, image_lookup)

    st.markdown("#### Comparer les candidats")
    plot = frame.head(10).sort_values("Score prédit")
    fig = px.bar(
        plot,
        x="Score prédit",
        y="Rhum",
        orientation="h",
        color="Couverture données (%)",
        range_x=[0, 10],
        hover_data=["Proximité aux données", "Source sensorielle", "Prix (€)", "Origine"],
        title="Top recommandations · score de goût prédit",
    )
    fig.update_layout(coloraxis_colorbar_title="Couverture")
    _chart(fig, height=390)

    with st.expander("Voir toutes les variables de décision"):
        _table(frame)



def _documentation_section(
    frame,
    image_lookup: dict[str, str | None],
    training_count: int,
) -> None:
    section_title("Dégustations à documenter")

    st.markdown(
        "Ces bouteilles sont **entamées mais n'ont aucune dégustation enregistrée**. "
        "RhumLog ne les considère donc plus comme des bouteilles à découvrir. "
        "Le niveau inférieur à 100 % est traité comme un **signal de qualité des données**, "
        "pas comme une preuve absolue qu'une dégustation personnelle a eu lieu."
    )

    if frame.empty:
        st.success("Aucune bouteille entamée sans dégustation enregistrée.")
        return

    stat_grid(
        [
            ("À documenter", len(frame), "bouteilles entamées sans dégustation"),
            ("N potentiel après saisie", training_count + len(frame), "maximum théorique avec scores exploitables"),
        ],
        columns=2,
    )

    st.info(
        "Enregistrer ces dégustations améliore d'abord la qualité du dataset. "
        "Si un score complet est saisi, la bouteille pourra ensuite devenir une nouvelle "
        "observation supervisée lors du prochain entraînement."
    )

    for start in range(0, len(frame), 3):
        cols = st.columns(3, gap="medium")
        subset = frame.iloc[start : start + 3]

        for col, (_, row) in zip(cols, subset.iterrows()):
            with col:
                with st.container(border=True):
                    name = str(row["Rhum"])
                    image_url = image_lookup.get(name)
                    if image_url:
                        _, center, _ = st.columns([1, 1.1, 1])
                        with center:
                            st.image(image_url, width=72)

                    level = float(row.get("Niveau (%)") or 0)
                    st.markdown(
                        f'<div class="rhum-reco-rank">NIVEAU · {level:.0f}%</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="rhum-reco-name">{html.escape(name)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.progress(int(max(0, min(100, round(level)))))

                    predicted = float(row["Score prédit"])
                    st.caption(
                        f"Estimation ML avant saisie · {predicted:.2f}/10"
                    )
                    st.caption(
                        "Action Data · ajouter la dégustation réelle pour documenter "
                        "ce que j'ai effectivement ressenti."
                    )

    with st.expander("Voir la file complète à documenter"):
        _table(frame)





def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    profiles = SensoryService(service.database_path, service.source_owner_id).list_profiles()
    snapshot = build_final_model_snapshot(rums, tastings, profiles)
    image_lookup = {str(rum.get("name") or ""): rum.get("image_url") for rum in rums}

    hero(
        "Recommandations",
        (
            "Je classe les bouteilles déjà connues de RhumLog à partir de mon historique de dégustation, "
            "avec une estimation du score, de la couverture et de l'incertitude."
        ),
        kicker="PERSONAL RANKING · EXPLAINABLE ML",
    )

    if snapshot.training_count == 0:
        st.info("Pas assez de dégustations pour produire des recommandations ML.")
        return

    section_title("Modèle utilisé")
    stat_grid(
        [
            ("Modèle", snapshot.model_name, "pipeline actuellement promu"),
            ("N entraînement", snapshot.training_count, "observations supervisées"),
            ("MAE LOOCV", f"{snapshot.mae:.2f}", "erreur absolue moyenne"),
            ("Spearman", f"{snapshot.spearman:+.2f}" if snapshot.spearman is not None else "—", "qualité de classement"),
        ],
        columns=4,
    )

    if snapshot.error_p80 is not None:
        st.caption(
            f"Incertitude affichée : ±{snapshot.error_p80:.2f} point (P80 des erreurs absolues LOOCV). "
            "Il s'agit d'une bande empirique globale, pas d'une probabilité individuelle."
        )

    section_title("File de décision")
    stat_grid(
        [
            ("En cave non dégustées", len(snapshot.next_to_taste), "niveau 100 % · aucune dégustation"),
            ("À documenter", len(snapshot.to_document), "entamées · dégustation manquante"),
            ("Wishlist scorée", len(snapshot.wishlist), "candidats avec estimation ML"),
            ("N potentiel", snapshot.training_count + len(snapshot.to_document), "si toutes les dégustations manquantes sont complétées"),
        ],
        columns=4,
    )

    tabs = st.tabs(
        [
            f"🥃 En cave · {len(snapshot.next_to_taste)}",
            f"📝 À documenter · {len(snapshot.to_document)}",
            f"🎯 Wishlist · {len(snapshot.wishlist)}",
            "Validation ML",
        ]
    )

    with tabs[0]:
        _candidate_section(
            snapshot.next_to_taste,
            "Bouteilles en cave sans dégustation enregistrée",
            image_lookup,
        )
        st.caption(
            "Critère : bouteille en cave, niveau documenté à 100 % et aucune "
            "dégustation enregistrée. Cette vue reste limitée aux bouteilles déjà présentes dans la cave."
        )

    with tabs[1]:
        _documentation_section(
            snapshot.to_document,
            image_lookup,
            snapshot.training_count,
        )

    with tabs[2]:
        _candidate_section(
            snapshot.wishlist,
            "Wishlist à fort potentiel",
            image_lookup,
        )
        st.caption(
            "Le prix est affiché pour la décision mais n'entre pas dans la "
            "prédiction du goût."
        )

    with tabs[3]:
        section_title("Pourquoi faire confiance au modèle avec prudence")
        st.dataframe(
            snapshot.comparison,
            hide_index=True,
            width="stretch",
            column_config={
                "MAE": st.column_config.NumberColumn(format="%.3f"),
                "Spearman": st.column_config.NumberColumn(format="%+.3f"),
            },
        )

        fig = px.scatter(
            snapshot.loocv_predictions,
            x="Score réel",
            y="Score prédit",
            hover_name="Rhum",
            size="Erreur absolue",
            range_x=[0, 10],
            range_y=[0, 10],
            title="Validation Leave-One-Out · prédiction vs score réel",
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=10, y1=10, line=dict(dash="dash"))
        _chart(fig, height=430)
        st.caption(
            "Chaque point correspond à une bouteille laissée de côté, prédite par un modèle "
            "entraîné sur toutes les autres. La diagonale représente une prédiction parfaite."
        )
