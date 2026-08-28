from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
from typing import Any

from rhumlog.access import AccessContext, require_write
from rhumlog.db import db_session


SENSORY_FEATURES: dict[str, str] = {
    "vanilla": "Vanille",
    "caramel": "Caramel / crème brûlée",
    "honey": "Miel",
    "cocoa": "Cacao / chocolat",
    "coffee": "Café / torréfié",
    "tropical_fruit": "Fruits tropicaux",
    "dried_fruit": "Fruits secs / confits",
    "citrus": "Agrumes",
    "nuts": "Noix / amande",
    "tobacco": "Tabac / cuir",
    "spice": "Épices",
    "wood": "Boisé / chêne",
    "floral": "Floral",
    "roundness": "Rondeur / texture",
    "long_finish": "Finale longue",
}

# Vocabulaire volontairement compact. L'objectif v1.14 est une extraction déterministe,
# auditable et améliorable, pas une pseudo-compréhension sémantique parfaite.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "vanilla": ("vanille", "vanilla"),
    "caramel": ("caramel", "creme brulee", "crème brûlée", "toffee"),
    "honey": ("miel", "honey"),
    "cocoa": ("cacao", "chocolat", "chocolate"),
    "coffee": ("cafe", "café", "moka", "torrefie", "torréfié", "torrefiee", "torréfiée"),
    "tropical_fruit": (
        "fruit tropical", "fruits tropicaux", "fruit exotique", "fruits exotiques",
        "ananas", "banane", "mangue", "papaye", "goyave", "coco", "noix de coco",
    ),
    "dried_fruit": (
        "fruit sec", "fruits secs", "fruit confit", "fruits confits", "raisin sec",
        "raisins secs", "datte", "figue", "abricot sec", "pruneau", "cerise", "fruits rouges",
    ),
    "citrus": ("agrume", "agrumes", "orange", "citron", "citron vert", "pamplemousse"),
    "nuts": ("noix", "amande", "amandes", "noisette", "noisettes"),
    "tobacco": ("tabac", "cuir", "cigare"),
    "spice": (
        "epice", "épice", "epices", "épices", "cannelle", "muscade", "girofle",
        "poivre", "pain d'epices", "pain d’épices", "pain d'épices",
    ),
    "wood": ("bois", "boise", "boisé", "chene", "chêne", "oak"),
    "floral": ("floral", "fleur", "fleurs", "jasmin", "violette"),
    "roundness": (
        "rond", "ronde", "rondeur", "soyeux", "soyeuse", "veloute", "velouté",
        "huileux", "huileuse", "onctueux", "onctueuse", "sirupeux", "sirupeuse",
    ),
    "long_finish": (
        "finale longue", "longue finale", "finale persistante", "finale tres longue",
        "finale très longue", "long finish",
    ),
}

EMPHASIS_WORDS = (
    "intense", "intensément", "dominant", "dominante", "domine", "riche", "marqué",
    "marquee", "marquée", "puissant", "puissante", "profond", "profonde", "généreux", "genereux",
)

# Marqueurs qui indiquent que le texte bascule dans une recommandation/personnalisation
# postérieure à l'analyse du goût de l'utilisateur. On tronque avant cette zone.
LEAKAGE_SPLIT_PATTERNS = (
    r"\bce rhum correspond\b",
    r"\bce rhum s['’]aligne\b",
    r"\bce rhum est (?:un|une) (?:match|correspondance)\b",
    r"\bce rhum est .*?pour (?:votre|vos)\b",
    r"\bvotre adn\b",
    r"\bvos ar[oô]mes favoris\b",
    r"\bvotre profil\b",
    r"\bvotre cible\b",
)

PERSONAL_MARKERS = (
    "pas mon gout", "pas mon goût", "comme j'aime", "comme j’aime", "je pense",
    "je sais", "mon meilleur", "bof", "mouais", "decu", "déçu", "a revoir", "à revoir",
    "un regal", "un régal", "tres bon", "très bon", "achete au", "acheté au",
)


@dataclass(frozen=True)
class SensoryExtraction:
    source_text: str | None
    eligible: bool
    exclusion_reason: str | None
    features: dict[str, float]
    confidence: float
    mentioned_count: int


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def sanitize_legacy_description(value: Any) -> tuple[str | None, str | None]:
    """Retourne une portion de description pré-dégustation exploitable, ou la raison d'exclusion.

    Les anciens `legacy_notes` mélangent descriptions produits, commentaires personnels et textes
    de recommandation générés. Cette fonction est donc volontairement conservatrice.
    """
    if value is None:
        return None, "description absente"
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return None, "description absente"

    # Coupe les blocs de personnalisation générés, sans supprimer une vraie description qui
    # commencerait par « Ce rhum est élaboré... ».
    earliest: int | None = None
    for pattern in LEAKAGE_SPLIT_PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    if earliest is not None:
        text = text[:earliest].rstrip(" :.;")

    folded = _fold(text)
    # Les commentaires personnels courts ou manifestement évaluatifs sont exclus.
    if any(marker in folded for marker in (_fold(x) for x in PERSONAL_MARKERS)) and len(text) < 180:
        return None, "commentaire personnel / post-dégustation probable"
    if len(text) < 55:
        return None, "texte trop court pour une extraction fiable"

    return text, None


def _feature_intensity(text: str, keywords: tuple[str, ...]) -> float:
    folded = _fold(text)
    hits = 0
    emphasis = False
    for keyword in keywords:
        key = _fold(keyword)
        if key in folded:
            hits += 1
            # Une fenêtre locale permet de distinguer « vanille » d'« intense vanille ».
            for match in re.finditer(re.escape(key), folded):
                lo = max(0, match.start() - 35)
                hi = min(len(folded), match.end() + 35)
                window = folded[lo:hi]
                if any(_fold(word) in window for word in EMPHASIS_WORDS):
                    emphasis = True
    if hits == 0:
        return 0.0
    score = 1 + min(2, hits - 1)
    if emphasis:
        score = min(3, score + 1)
    return float(score)


def extract_sensory_features(value: Any) -> SensoryExtraction:
    text, reason = sanitize_legacy_description(value)
    if text is None:
        return SensoryExtraction(
            source_text=None,
            eligible=False,
            exclusion_reason=reason,
            features={key: 0.0 for key in SENSORY_FEATURES},
            confidence=0.0,
            mentioned_count=0,
        )

    features = {key: _feature_intensity(text, KEYWORDS[key]) for key in SENSORY_FEATURES}
    mentioned = sum(value > 0 for value in features.values())
    # Confiance = qualité de couverture du texte, pas probabilité d'exactitude scientifique.
    confidence = min(0.95, 0.42 + 0.035 * mentioned + (0.08 if len(text) >= 180 else 0.0))
    if mentioned == 0:
        confidence = min(confidence, 0.35)

    return SensoryExtraction(
        source_text=text,
        eligible=True,
        exclusion_reason=None,
        features=features,
        confidence=float(confidence),
        mentioned_count=int(mentioned),
    )


class SensoryService:
    def __init__(self, database_path: Path, source_owner_id: str):
        self.database_path = database_path
        self.source_owner_id = source_owner_id

    def list_profiles(self) -> list[dict[str, Any]]:
        with db_session(self.database_path) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT s.*, r.name AS rum_name, r.status AS rum_status
                    FROM sensory_profiles s
                    JOIN rums r ON r.id = s.rum_id
                    WHERE r.source_user_id = ?
                    ORDER BY r.name COLLATE NOCASE
                    """,
                    (self.source_owner_id,),
                ).fetchall()
            ]

    def get_profile(self, rum_id: str) -> dict[str, Any] | None:
        with db_session(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT s.*, r.name AS rum_name
                FROM sensory_profiles s
                JOIN rums r ON r.id = s.rum_id
                WHERE s.rum_id = ? AND r.source_user_id = ?
                """,
                (rum_id, self.source_owner_id),
            ).fetchone()
            return dict(row) if row else None

    def candidate_for_rum(self, rum: dict[str, Any]) -> SensoryExtraction:
        return extract_sensory_features(rum.get("legacy_notes"))

    def extract_all_drafts(
        self,
        rums: list[dict[str, Any]],
        access: AccessContext,
        overwrite_drafts: bool = False,
    ) -> dict[str, int]:
        require_write(access)
        stats = {"eligible": 0, "created": 0, "skipped": 0, "excluded": 0}
        for rum in rums:
            extraction = self.candidate_for_rum(rum)
            if not extraction.eligible:
                stats["excluded"] += 1
                continue
            stats["eligible"] += 1
            existing = self.get_profile(str(rum["id"]))
            if existing and existing.get("validation_status") == "validated":
                stats["skipped"] += 1
                continue
            if existing and not overwrite_drafts:
                stats["skipped"] += 1
                continue
            self._upsert(
                str(rum["id"]),
                extraction.features,
                source_text=extraction.source_text,
                source_kind="legacy_description",
                extraction_method="keyword_v1",
                confidence=extraction.confidence,
                validation_status="draft",
                access=access,
            )
            stats["created"] += 1
        return stats

    def validate_profile(
        self,
        rum_id: str,
        features: dict[str, float],
        access: AccessContext,
        source_text: str | None = None,
        source_kind: str | None = None,
    ) -> None:
        require_write(access)
        existing = self.get_profile(rum_id)
        self._upsert(
            rum_id,
            features,
            source_text=source_text if source_text is not None else (existing or {}).get("source_text"),
            source_kind=source_kind if source_kind is not None else (existing or {}).get("source_kind") or "manual",
            extraction_method=(existing or {}).get("extraction_method") or "manual",
            confidence=float((existing or {}).get("confidence") or 1.0),
            validation_status="validated",
            access=access,
        )

    def reject_profile(self, rum_id: str, access: AccessContext) -> None:
        require_write(access)
        with db_session(self.database_path) as conn:
            cur = conn.execute(
                """
                UPDATE sensory_profiles
                SET validation_status = 'rejected', updated_at = ?
                WHERE rum_id = ? AND EXISTS (
                    SELECT 1 FROM rums r WHERE r.id = sensory_profiles.rum_id AND r.source_user_id = ?
                )
                """,
                (datetime.now(timezone.utc).isoformat(), rum_id, self.source_owner_id),
            )
            if cur.rowcount != 1:
                raise LookupError("Profil sensoriel introuvable ou non autorisé.")

    def _upsert(
        self,
        rum_id: str,
        features: dict[str, float],
        source_text: str | None,
        source_kind: str,
        extraction_method: str,
        confidence: float,
        validation_status: str,
        access: AccessContext,
    ) -> None:
        require_write(access)
        if validation_status not in {"draft", "validated", "rejected"}:
            raise ValueError("Statut de validation sensorielle invalide.")
        values: dict[str, float] = {}
        for key in SENSORY_FEATURES:
            value = float(features.get(key, 0.0))
            if not 0 <= value <= 3:
                raise ValueError(f"{SENSORY_FEATURES[key]} doit être compris entre 0 et 3.")
            values[key] = value

        with db_session(self.database_path) as conn:
            owner = conn.execute(
                "SELECT 1 FROM rums WHERE id = ? AND source_user_id = ?",
                (rum_id, self.source_owner_id),
            ).fetchone()
            if owner is None:
                raise LookupError("Bouteille introuvable ou non autorisée.")
            conn.execute(
                f"""
                INSERT INTO sensory_profiles (
                    rum_id, {', '.join(SENSORY_FEATURES.keys())}, source_text, source_kind,
                    extraction_method, confidence, validation_status, updated_at
                ) VALUES (
                    ?, {', '.join('?' for _ in SENSORY_FEATURES)}, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(rum_id) DO UPDATE SET
                    {', '.join(f'{key}=excluded.{key}' for key in SENSORY_FEATURES)},
                    source_text=excluded.source_text,
                    source_kind=excluded.source_kind,
                    extraction_method=excluded.extraction_method,
                    confidence=excluded.confidence,
                    validation_status=excluded.validation_status,
                    updated_at=excluded.updated_at
                """,
                (
                    rum_id,
                    *(values[key] for key in SENSORY_FEATURES),
                    source_text,
                    source_kind,
                    extraction_method,
                    max(0.0, min(1.0, float(confidence))),
                    validation_status,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
