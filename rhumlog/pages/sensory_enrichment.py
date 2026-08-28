from __future__ import annotations

import pandas as pd
import streamlit as st

from rhumlog.access import AccessContext
from rhumlog.services.rum_service import RumService
from rhumlog.services.sensory import SENSORY_FEATURES, SensoryService
from rhumlog.ui.components import hero, stat_grid


def render(service: RumService, access: AccessContext) -> None:
    sensory = SensoryService(service.database_path, service.source_owner_id)
    rums = service.list_rums()
    profiles = sensory.list_profiles()
    profiles_by_id = {row["rum_id"]: row for row in profiles}

    candidates = []
    eligible = 0
    excluded = 0
    for rum in rums:
        extraction = sensory.candidate_for_rum(rum)
        if extraction.eligible:
            eligible += 1
        else:
            excluded += 1
        candidates.append((rum, extraction))

    validated = sum(row.get("validation_status") == "validated" for row in profiles)
    drafts = sum(row.get("validation_status") == "draft" for row in profiles)

    hero(
        "Vocabulaire sensoriel",
        "Je structure un profil sensoriel fin, sa provenance et sa validation, avec une extraction déterministe limitée aux descriptions pré-dégustation exploitables.",
        kicker="DATA ENRICHMENT · PROVENANCE · HUMAN REVIEW",
    )

    stat_grid(
        [
            ("Bouteilles", len(rums), "références analysées"),
            ("Descriptions éligibles", eligible, "pré-dégustation"),
            ("Brouillons extraits", drafts, "à revoir"),
            ("Profils validés", validated, "revus humainement"),
        ],
        columns=4,
    )

    st.info(
        "Sécurité méthodologique : les commentaires personnels et les formulations marketing personnalisantes "
        "sont exclus ou tronqués. Une donnée utilisée pour prédire mon goût "
        "doit pouvoir exister avant ma dégustation."
    )

    tabs = st.tabs(["Extraction", "À valider", "Matrice", "Méthode"])

    with tabs[0]:
        st.subheader("Extraction automatique depuis les données déjà présentes")
        st.write(
            "L'extracteur cherche un vocabulaire contrôlé (vanille, caramel, miel, cacao, fruits, bois, etc.). "
            "Il n'utilise ni Gemini ni une API externe : chaque score est traçable par mots-clés."
        )
        if access.can_write:
            overwrite = st.checkbox("Réextraire aussi les brouillons existants", value=False)
            if st.button("Extraire tous les brouillons éligibles", type="primary"):
                stats = sensory.extract_all_drafts(rums, access, overwrite_drafts=overwrite)
                st.success(
                    f"Extraction terminée : {stats['created']} brouillons créés, "
                    f"{stats['skipped']} conservés, {stats['excluded']} textes exclus."
                )
                st.rerun()
        else:
            st.info("Le mode démonstration reste en lecture seule.")

        audit_rows = []
        for rum, extraction in candidates:
            audit_rows.append(
                {
                    "Rhum": rum["name"],
                    "Éligible": extraction.eligible,
                    "Dimensions détectées": extraction.mentioned_count,
                    "Confiance extraction": extraction.confidence,
                    "Raison exclusion": extraction.exclusion_reason or "",
                    "Statut profil": (profiles_by_id.get(rum["id"]) or {}).get("validation_status", "—"),
                }
            )
        audit = pd.DataFrame(audit_rows)
        st.dataframe(
            audit,
            hide_index=True,
            width="stretch",
            column_config={
                "Confiance extraction": st.column_config.NumberColumn(format="%.0%%"),
            },
        )

    with tabs[1]:
        st.subheader("Validation humaine")
        selectable = [
            rum for rum in rums
            if rum["id"] in profiles_by_id and profiles_by_id[rum["id"]].get("validation_status") != "rejected"
        ]
        if not selectable:
            st.info("Aucun profil extrait pour l'instant. Lance d'abord l'extraction automatique.")
        else:
            selected_name = st.selectbox("Bouteille", [rum["name"] for rum in selectable])
            rum = next(item for item in selectable if item["name"] == selected_name)
            profile = profiles_by_id[rum["id"]]
            st.caption(
                f"Provenance : {profile.get('source_kind') or '—'} · méthode : {profile.get('extraction_method') or '—'} · "
                f"confiance extraction : {float(profile.get('confidence') or 0):.0%} · statut : {profile.get('validation_status')}"
            )
            if profile.get("source_text"):
                with st.expander("Voir le texte source"):
                    st.write(profile["source_text"])

            features: dict[str, float] = {}
            cols = st.columns(3)
            for idx, (key, label) in enumerate(SENSORY_FEATURES.items()):
                with cols[idx % 3]:
                    features[key] = float(
                        st.slider(
                            label,
                            min_value=0,
                            max_value=3,
                            value=int(round(float(profile.get(key) or 0))),
                            key=f"sensory_{rum['id']}_{key}",
                            help="0 = non mentionné/absent ; 1 = léger ; 2 = présent ; 3 = dominant.",
                        )
                    )

            if access.can_write:
                left, right = st.columns(2)
                if left.button("Valider ce profil", type="primary", use_container_width=True):
                    sensory.validate_profile(rum["id"], features, access)
                    st.success("Profil sensoriel validé.")
                    st.rerun()
                if right.button("Rejeter ce profil", use_container_width=True):
                    sensory.reject_profile(rum["id"], access)
                    st.warning("Profil rejeté : il ne sera pas utilisé comme donnée validée.")
                    st.rerun()

    with tabs[2]:
        st.subheader("Matrice sensorielle enregistrée")
        if not profiles:
            st.info("Aucun profil sensoriel enregistré.")
        else:
            frame = pd.DataFrame(profiles)
            columns = ["rum_name", "validation_status", "confidence", *SENSORY_FEATURES.keys()]
            display = frame[columns].rename(
                columns={"rum_name": "Rhum", "validation_status": "Statut", "confidence": "Confiance", **SENSORY_FEATURES}
            )
            st.dataframe(
                display,
                hide_index=True,
                width="stretch",
                column_config={"Confiance": st.column_config.NumberColumn(format="%.0%%")},
            )

    with tabs[3]:
        st.subheader("Pourquoi une échelle 0–3 ?")
        st.markdown(
            """
- **0** : non mentionné / absence de signal dans la source ;
- **1** : mention simple ;
- **2** : plusieurs indices ou mention renforcée ;
- **3** : dimension dominante / fortement répétée.

L'échelle courte évite une fausse précision. Une description commerciale ne permet pas de défendre un « 8,37/10 de vanille ».

**Provenance** et **statut de validation** restent stockés avec les features. Plus tard, une source fabricant ou une fiche produit externe pourra remplacer proprement un ancien texte sans perdre la traçabilité.
            """
        )
