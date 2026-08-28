from __future__ import annotations

import plotly.express as px
import streamlit as st

from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SensoryService
from rhumlog.services.sensory_benchmark import build_sensory_benchmark_snapshot
from rhumlog.ui.components import hero, stat_grid
from rhumlog.ui.theme import style_figure


def _chart(fig) -> None:
    style_figure(fig)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(service: RumService) -> None:
    rums = service.list_rums()
    tastings = {rum["id"]: service.list_tastings(rum["id"]) for rum in rums}
    sensory = SensoryService(service.database_path, service.source_owner_id)
    snapshot = build_sensory_benchmark_snapshot(rums, tastings, sensory.list_profiles())

    hero(
        "Benchmark sensoriel",
        "Même Ridge, même alpha et même LOOCV : je mesure l'effet réel du vocabulaire sensoriel sans changer le reste du protocole.",
        kicker="EXPERIMENT · SENSORY FEATURES · ABLATION",
    )

    if snapshot.sample_count < 3:
        st.warning("Pas assez de dégustations pour lancer le benchmark.")
        return

    stat_grid(
        [
            ("Rhums évalués", snapshot.sample_count, "observations supervisées"),
            ("Auto exploitables", snapshot.auto_eligible_count, "extractions éligibles"),
            ("Profils enregistrés", snapshot.stored_profile_count, "dans SQLite"),
            ("Validés", snapshot.validated_profile_count, "revus humainement"),
        ],
        columns=4,
    )

    tabs = st.tabs(["Comparaison", "Couverture", "Erreurs", "Décision"])

    with tabs[0]:
        display = snapshot.experiments.copy()
        display["Top-k"] = display.apply(lambda r: f"{int(r['Top-k retrouvés'])}/{int(r['Top-k'])}", axis=1)
        st.dataframe(
            display[["Expérience", "MAE", "Δ MAE vs base", "Spearman", "Δ Spearman vs base", "Top-k", "Note"]],
            hide_index=True,
            width="stretch",
            column_config={
                "MAE": st.column_config.NumberColumn(format="%.3f"),
                "Δ MAE vs base": st.column_config.NumberColumn(format="%+.3f"),
                "Spearman": st.column_config.NumberColumn(format="%+.3f"),
                "Δ Spearman vs base": st.column_config.NumberColumn(format="%+.3f"),
            },
        )
        fig = px.bar(
            snapshot.experiments.sort_values("MAE"),
            x="MAE", y="Expérience", orientation="h", text="MAE",
            title="Ridge LOOCV · MAE (plus bas = mieux)",
        )
        fig.update_traces(texttemplate="%{text:.3f}")
        _chart(fig)
        fig = px.bar(
            snapshot.experiments.sort_values("Spearman"),
            x="Spearman", y="Expérience", orientation="h", text="Spearman",
            range_x=[-1, 1], title="Ridge LOOCV · Spearman (plus haut = mieux)",
        )
        fig.update_traces(texttemplate="%{text:+.3f}")
        _chart(fig)

    with tabs[1]:
        st.subheader("Couverture réelle de l'enrichissement")
        st.dataframe(
            snapshot.feature_coverage,
            hide_index=True,
            width="stretch",
            column_config={"Part": st.column_config.NumberColumn(format="%.0%%")},
        )
        st.warning(
            "Une amélioration obtenue avec seulement quelques descriptions exploitables reste fragile. "
            "La v1.15 mesure le signal disponible ; elle ne transforme pas automatiquement un brouillon non validé en vérité sensorielle."
        )

    with tabs[2]:
        experiment = st.selectbox("Expérience", snapshot.experiments["Expérience"].tolist())
        pred = snapshot.predictions[snapshot.predictions["Expérience"] == experiment].copy()
        pred = pred.sort_values("Erreur absolue", ascending=False)
        st.dataframe(pred, hide_index=True, width="stretch")
        fig = px.scatter(
            pred,
            x="Score réel",
            y="Score prédit",
            hover_name="Rhum",
            title=f"Réel vs prédit · {experiment}",
        )
        fig.add_shape(type="line", x0=4, y0=4, x1=10, y1=10, line=dict(dash="dash", width=2))
        _chart(fig)

    with tabs[3]:
        st.metric("Meilleure MAE", snapshot.best_mae_experiment or "—")
        st.metric("Meilleur Spearman", snapshot.best_spearman_experiment or "—")
        best = snapshot.experiments.sort_values("Spearman", ascending=False).iloc[0]
        base = snapshot.experiments[snapshot.experiments["Expérience"] == "Base v1.10"].iloc[0]
        if float(best["Spearman"]) > float(base["Spearman"]):
            st.success(
                f"Le meilleur jeu de variables améliore ici Spearman de {float(best['Spearman']) - float(base['Spearman']):+.3f}. "
                "C'est un signal favorable, à confirmer avec davantage de profils validés et de dégustations."
            )
        else:
            st.info(
                "Le vocabulaire sensoriel fin ne bat pas encore la référence sur cette validation. "
                "C'est un résultat utile : on évite de promouvoir des features uniquement parce qu'elles semblent intuitivement riches."
            )
        st.markdown(
            "**Règle de promotion :** on ne remplace pas le modèle de recommandation tant qu'un enrichissement n'apporte pas "
            "un gain reproductible et interprétable sur MAE / classement / top-k."
        )
