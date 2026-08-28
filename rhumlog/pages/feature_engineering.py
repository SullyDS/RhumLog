from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from rhumlog.services.rum_service import RumService
from rhumlog.ui.components import hero, stat_grid
from rhumlog.ui.theme import style_figure


def _chart(fig) -> None:
    style_figure(fig)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}

    try:
        from rhumlog.services.feature_engineering import build_feature_engineering_snapshot

        snapshot = build_feature_engineering_snapshot(rums, tastings_by_rum)
    except ImportError as exc:
        st.error("Cette page nécessite scikit-learn. Exécute `pip install -r requirements.txt`.")
        st.exception(exc)
        return

    hero(
        "Feature Engineering",
        "Je garde Ridge et la LOOCV fixes pour isoler l'effet des nouvelles variables : une feature n'est conservée que si elle améliore la validation.",
        kicker="EXPERIMENT · ABLATION · FEATURE SELECTION",
    )

    if snapshot.sample_count < 3:
        st.warning("Pas assez de dégustations pour lancer les expériences.")
        return

    stat_grid(
        [
            ("Rhums évalués", snapshot.sample_count, "observations supervisées"),
            ("Âge exploitable", f"{snapshot.age_known_count}/{snapshot.sample_count}", f"couverture {snapshot.age_coverage:.0%}"),
            ("Origines", snapshot.origin_count, "catégories observées"),
            ("Origines singleton", snapshot.origin_singletons, "une seule observation"),
        ],
        columns=4,
    )

    st.info(
        "Important : `âge représentatif` est un proxy expérimental. Pour `6-25`, le code utilise 15,5 uniquement pour tester une information ordonnée ; "
        "cela ne signifie pas qu'un assemblage Solera a réellement 15,5 ans."
    )

    tabs = st.tabs(["Expériences", "Âge", "Origine", "Décision"])

    with tabs[0]:
        st.subheader("Ablation / ajout de features avec Ridge fixé")
        display = snapshot.experiments.copy()
        display["Top-k"] = display.apply(
            lambda row: f"{int(row['Top-k retrouvés'])}/{int(row['Top-k'])}", axis=1
        )
        st.dataframe(
            display[
                [
                    "Expérience",
                    "MAE",
                    "Δ MAE vs base",
                    "Spearman",
                    "Δ Spearman vs base",
                    "Top-k",
                    "Δ Top-k vs base",
                    "Note",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "MAE": st.column_config.NumberColumn(format="%.3f"),
                "Δ MAE vs base": st.column_config.NumberColumn(format="%+.3f"),
                "Spearman": st.column_config.NumberColumn(format="%+.3f"),
                "Δ Spearman vs base": st.column_config.NumberColumn(format="%+.3f"),
            },
        )

        ordered = snapshot.experiments.sort_values("MAE", ascending=True)
        fig = px.bar(
            ordered,
            x="MAE",
            y="Expérience",
            orientation="h",
            text="MAE",
            title="Ridge LOOCV · MAE par jeu de features (plus bas = mieux)",
        )
        fig.update_traces(texttemplate="%{text:.3f}")
        _chart(fig)

        ordered = snapshot.experiments.sort_values("Spearman")
        fig = px.bar(
            ordered,
            x="Spearman",
            y="Expérience",
            orientation="h",
            text="Spearman",
            range_x=[-1, 1],
            title="Ridge LOOCV · Spearman (plus haut = mieux)",
        )
        fig.update_traces(texttemplate="%{text:+.3f}")
        _chart(fig)

        st.markdown(
            "**Pourquoi garder le modèle fixe ?** Si on change simultanément les features et l'algorithme, on ne sait plus ce qui a produit le gain. "
            "Ici, seul `X` change ; Ridge, alpha=10, le preprocessing et LOOCV restent identiques."
        )

    with tabs[1]:
        st.subheader("Audit du parsing de l'âge")
        st.dataframe(
            snapshot.age_audit,
            hide_index=True,
            width="stretch",
            column_config={
                "Âge représentatif": st.column_config.NumberColumn(format="%.1f"),
                "Âge min": st.column_config.NumberColumn(format="%.1f"),
                "Âge max": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.caption(
            "`XO` et les valeurs vides restent manquants. Une plage conserve min/max ; son milieu n'est utilisé que comme proxy de recherche. "
            "La base SQLite n'est pas modifiée."
        )

    with tabs[2]:
        st.subheader("Sparsité de l'origine")
        fig = px.bar(
            snapshot.origin_counts.sort_values("N"),
            x="N",
            y="Origine",
            orientation="h",
            text="N",
            title="Nombre de rhums dégustés par origine",
        )
        _chart(fig)
        st.warning(
            f"{snapshot.origin_count} origines pour {snapshot.sample_count} rhums ; "
            f"{snapshot.origin_singletons} origines n'apparaissent qu'une seule fois. "
            "Un one-hot encoding d'origine peut donc apprendre des catégories très peu documentées."
        )

    with tabs[3]:
        st.subheader("Décision expérimentale")
        st.metric("Meilleure MAE Ridge", snapshot.best_mae_experiment or "—")
        st.metric("Meilleur Spearman Ridge", snapshot.best_spearman_experiment or "—")

        base = snapshot.experiments[snapshot.experiments["Expérience"] == "Base v1.10"].iloc[0]
        candidate = snapshot.experiments[
            snapshot.experiments["Expérience"] == "+ âge + origine"
        ].iloc[0]

        st.markdown(
            f"La combinaison **âge + origine** passe ici de MAE **{base['MAE']:.3f}** à **{candidate['MAE']:.3f}** "
            f"et de Spearman **{base['Spearman']:+.3f}** à **{candidate['Spearman']:+.3f}**. "
            "Le gain existe, mais reste petit sur seulement 38 observations."
        )
        st.success(
            "Décision : conserver l'expérience et le schéma de features, mais ne pas remplacer automatiquement le modèle v1.10. "
            "Il faut maintenant enrichir des variables sensorielles pré-dégustation plus discriminantes et accumuler davantage de notes."
        )
        st.error(
            "Le prix sert ici de contrôle négatif : son ajout dégrade la validation Ridge. C'est une démonstration concrète que `plus de colonnes` ne signifie pas `meilleur modèle`."
        )
