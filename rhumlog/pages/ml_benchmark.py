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


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}f}"


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings_by_rum = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}

    try:
        from rhumlog.services.ml_benchmark import build_ml_benchmark_snapshot

        snapshot = build_ml_benchmark_snapshot(rums, tastings_by_rum)
    except ImportError as exc:
        st.error(
            "Le benchmark ML nécessite scikit-learn. Exécute `pip install -r requirements.txt` "
            "dans l'environnement virtuel puis relancer Streamlit."
        )
        st.exception(exc)
        return

    hero(
        "Benchmark Machine Learning",
        "Même dataset, même preprocessing dans chaque fold et même Leave-One-Out : les modèles sont comparés sur un protocole commun.",
        kicker="EXPERIMENT · MODEL COMPARISON · LOOCV",
    )

    if snapshot.sample_count < 3:
        st.warning("Pas assez de rhums dégustés pour construire un benchmark.")
        return

    stat_grid(
        [
            ("Observations", snapshot.sample_count, "évaluées en LOOCV"),
            ("Variables brutes", snapshot.feature_count_raw, "avant encodage"),
            ("Meilleure MAE", snapshot.best_mae_model or "—", "sur le benchmark courant"),
            ("Meilleur Spearman", snapshot.best_spearman_model or "—", "sur le benchmark courant"),
        ],
        columns=4,
    )

    st.info(
        "Le dataset reste très petit. Un modèle qui gagne aujourd'hui n'est pas automatiquement un modèle fiable en production : "
        "on cherche d'abord à mesurer proprement ce que les données permettent réellement."
    )

    tabs = st.tabs(["Comparaison", "Prédictions LOOCV", "Variables", "Méthode"])

    with tabs[0]:
        st.subheader("Tableau de benchmark")
        metrics = snapshot.metrics.copy()
        metrics["Top-k"] = metrics.apply(
            lambda row: f"{int(row['Top-k retrouvés'])}/{int(row['Top-k'])}"
            if pd.notna(row.get("Top-k")) and pd.notna(row.get("Top-k retrouvés")) and int(row.get("Top-k", 0)) > 0
            else "—",
            axis=1,
        )
        display = metrics[["Modèle", "MAE", "Pearson", "Spearman", "Top-k"]]
        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            column_config={
                "MAE": st.column_config.NumberColumn(format="%.3f"),
                "Pearson": st.column_config.NumberColumn(format="%+.3f"),
                "Spearman": st.column_config.NumberColumn(format="%+.3f"),
            },
        )

        st.markdown(
            "**Lecture :** MAE plus basse = meilleure précision de note. Spearman plus haut = meilleur classement. "
            "La baseline heuristique v1.9 n'a pas de MAE car son `Match` 0–100 n'est pas une note prédite sur 10. "
            "La moyenne globale sert uniquement de référence de MAE : en Leave-One-Out, son classement produit un artefact mathématique, donc Pearson/Spearman/Top-k ne sont volontairement pas affichés."
        )

        model_metrics = metrics[metrics["MAE"].notna()].copy().sort_values("MAE")
        if not model_metrics.empty:
            fig = px.bar(
                model_metrics,
                x="MAE",
                y="Modèle",
                orientation="h",
                text="MAE",
                title="Erreur absolue moyenne en Leave-One-Out · plus bas = mieux",
            )
            fig.update_traces(texttemplate="%{text:.3f}")
            fig.update_yaxes(categoryorder="total descending")
            _chart(fig)

        ranking_metrics = metrics[metrics["Spearman"].notna()].copy().sort_values("Spearman")
        if not ranking_metrics.empty:
            fig = px.bar(
                ranking_metrics,
                x="Spearman",
                y="Modèle",
                orientation="h",
                text="Spearman",
                range_x=[-1, 1],
                title="Qualité du classement · Spearman",
            )
            fig.update_traces(texttemplate="%{text:+.3f}")
            _chart(fig)

    with tabs[1]:
        st.subheader("Prédictions obtenues sans voir le rhum cible")
        if snapshot.predictions.empty:
            st.info("Aucune prédiction disponible.")
        else:
            available = snapshot.predictions["Modèle"].drop_duplicates().tolist()
            model_name = st.selectbox("Modèle", available, index=0)
            subset = snapshot.predictions[snapshot.predictions["Modèle"] == model_name].copy()

            mae = float(subset["Erreur absolue"].mean())
            spearman = subset["Score prédit"].rank().corr(subset["Score réel"].rank())
            p1, p2 = st.columns(2)
            p1.metric("MAE", f"{mae:.3f} point")
            p2.metric("Spearman", _fmt(float(spearman) if pd.notna(spearman) else None, 3))

            fig = px.scatter(
                subset,
                x="Score prédit",
                y="Score réel",
                hover_name="Rhum",
                range_x=[0, 10],
                range_y=[0, 10],
                title=f"{model_name} · score prédit vs score réel",
            )
            fig.add_shape(
                type="line",
                x0=0,
                y0=0,
                x1=10,
                y1=10,
                line=dict(dash="dash", width=2),
            )
            _chart(fig)

            st.dataframe(
                subset.sort_values("Erreur absolue", ascending=False),
                width="stretch",
                hide_index=True,
                column_config={
                    "Score réel": st.column_config.NumberColumn(format="%.2f"),
                    "Score prédit": st.column_config.NumberColumn(format="%.2f"),
                    "Erreur absolue": st.column_config.NumberColumn(format="%.2f"),
                },
            )
            st.caption(
                "Les premières lignes sont les plus grosses erreurs : ce sont souvent les exemples les plus utiles pour comprendre ce qui manque au modèle."
            )

    with tabs[2]:
        st.subheader("Ce que Ridge apprend sur le dataset complet")
        st.caption(
            "Ces coefficients servent à l'interprétation descriptive après le benchmark. Ils ne sont pas des effets causaux. "
            "Les variables numériques sont standardisées, ce qui rend leurs coefficients plus comparables entre eux."
        )
        if snapshot.coefficient_table.empty:
            st.info("Coefficients indisponibles.")
        else:
            coeffs = snapshot.coefficient_table.head(20).sort_values("Coefficient")
            fig = px.bar(
                coeffs,
                x="Coefficient",
                y="Feature",
                orientation="h",
                title="Ridge · principaux coefficients sur l'ensemble des données",
            )
            _chart(fig)
            st.dataframe(
                snapshot.coefficient_table.head(25),
                width="stretch",
                hide_index=True,
                column_config={
                    "Coefficient": st.column_config.NumberColumn(format="%+.4f"),
                    "Importance absolue": st.column_config.NumberColumn(format="%.4f"),
                },
            )

    with tabs[3]:
        st.subheader("Protocole")
        st.markdown(
            f"""
            **Cible** : score moyen de dégustation par rhum.

            **Variables brutes** : ABV, les 6 dimensions aromatiques, indicateur `profil aromatique connu`, et type de rhum.  
            Le prix reste volontairement hors de ce premier benchmark de goût.

            **Préprocessing dans chaque fold** :
            - médiane pour les valeurs numériques manquantes + indicateurs de valeurs manquantes ;
            - standardisation des variables numériques pour les modèles qui en ont besoin ;
            - encodage one-hot du type avec catégories inconnues ignorées.

            **Validation** : Leave-One-Out, soit {snapshot.sample_count} entraînements par modèle. À chaque tour, le rhum évalué est absent du `fit` du preprocessing **et** du modèle.

            **Groupe haut** : score ≥ Q3 ({snapshot.high_score_threshold:.3f}/10), soit {snapshot.high_score_count} rhums. Le Top-k mesure combien de ces rhums sont retrouvés dans les {snapshot.high_score_count} meilleures prédictions.
            """
        )
        st.markdown(
            """
            **Modèles du benchmark**
            - Moyenne globale : référence prédictive naïve ;
            - Ridge : relation linéaire avec pénalisation L2 ;
            - ElasticNet : mélange L1/L2 ;
            - k-NN : prédiction à partir de rhums proches dans l'espace de variables ;
            - Random Forest : modèle non linéaire, volontairement contraint pour réduire le risque de surapprentissage.
            """
        )
        st.warning(
            "Les hyperparamètres sont fixes dans cette version. Si nous les réglons plus tard, il faudra faire une validation imbriquée (nested CV) "
            "ou séparer clairement la phase de sélection de la phase d'évaluation pour ne pas optimiser sur le même score que celui que l'on présente comme preuve."
        )
