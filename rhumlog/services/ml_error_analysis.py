from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from rhumlog.services.ml_benchmark import MLBenchmarkSnapshot


@dataclass(frozen=True)
class ModelErrorAnalysis:
    model_name: str
    predictions: pd.DataFrame
    score_bands: pd.DataFrame
    underpredicted: pd.DataFrame
    overpredicted: pd.DataFrame
    actual_std: float | None
    predicted_std: float | None
    dispersion_ratio: float | None
    low_band_bias: float | None
    high_band_bias: float | None
    q1: float | None
    q3: float | None


def _safe_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def analyze_model_errors(
    snapshot: MLBenchmarkSnapshot,
    model_name: str,
) -> ModelErrorAnalysis:
    subset = snapshot.predictions[
        snapshot.predictions["Modèle"] == model_name
    ].copy()

    if subset.empty:
        return ModelErrorAnalysis(
            model_name=model_name,
            predictions=pd.DataFrame(),
            score_bands=pd.DataFrame(),
            underpredicted=pd.DataFrame(),
            overpredicted=pd.DataFrame(),
            actual_std=None,
            predicted_std=None,
            dispersion_ratio=None,
            low_band_bias=None,
            high_band_bias=None,
            q1=None,
            q3=None,
        )

    subset["Résidu"] = subset["Score prédit"] - subset["Score réel"]
    subset["Direction"] = np.select(
        [subset["Résidu"] > 0.10, subset["Résidu"] < -0.10],
        ["Surestimé", "Sous-estimé"],
        default="Proche",
    )

    q1 = float(subset["Score réel"].quantile(0.25))
    q3 = float(subset["Score réel"].quantile(0.75))
    subset["Bande"] = np.select(
        [subset["Score réel"] <= q1, subset["Score réel"] >= q3],
        ["Bas (≤ Q1)", "Haut (≥ Q3)"],
        default="Milieu",
    )

    band_order = ["Bas (≤ Q1)", "Milieu", "Haut (≥ Q3)"]
    score_bands = (
        subset.groupby("Bande", observed=True)
        .agg(
            N=("Rhum", "size"),
            **{
                "Score réel moyen": ("Score réel", "mean"),
                "Score prédit moyen": ("Score prédit", "mean"),
                "Biais moyen": ("Résidu", "mean"),
                "MAE": ("Erreur absolue", "mean"),
            },
        )
        .reindex(band_order)
        .reset_index()
    )

    actual_std = _safe_float(subset["Score réel"].std())
    predicted_std = _safe_float(subset["Score prédit"].std())
    dispersion_ratio = None
    if actual_std and actual_std > 0 and predicted_std is not None:
        dispersion_ratio = predicted_std / actual_std

    low_rows = subset[subset["Bande"] == "Bas (≤ Q1)"]
    high_rows = subset[subset["Bande"] == "Haut (≥ Q3)"]

    low_band_bias = _safe_float(low_rows["Résidu"].mean()) if not low_rows.empty else None
    high_band_bias = _safe_float(high_rows["Résidu"].mean()) if not high_rows.empty else None

    underpredicted = subset.sort_values("Résidu").head(8).copy()
    overpredicted = subset.sort_values("Résidu", ascending=False).head(8).copy()

    return ModelErrorAnalysis(
        model_name=model_name,
        predictions=subset,
        score_bands=score_bands,
        underpredicted=underpredicted,
        overpredicted=overpredicted,
        actual_std=actual_std,
        predicted_std=predicted_std,
        dispersion_ratio=dispersion_ratio,
        low_band_bias=low_band_bias,
        high_band_bias=high_band_bias,
        q1=q1,
        q3=q3,
    )
