from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from rhumlog.access import AccessContext, require_write
from rhumlog.db import db_session


VALID_STATUSES = {"owned", "wishlist", "tasted", "finished", "trash"}
VALID_ACQUISITION_TYPES = {None, "bought", "gifted"}


@dataclass(frozen=True)
class RumUpdate:
    """Petite mise à jour utilisée par des écrans simples."""

    fill_level: float | None = None
    status: str | None = None
    is_favorite: bool | None = None


@dataclass(frozen=True)
class RumDetailsUpdate:
    """Toutes les informations métier éditables d'une bouteille."""

    name: str
    distillery: str | None
    origin: str | None
    type: str | None
    abv: float | None
    price: float | None
    age: str | None
    status: str
    fill_level: float | None
    legacy_notes: str | None
    image_url: str | None
    is_favorite: bool
    date_added: str | None
    acquisition_type: str | None


@dataclass(frozen=True)
class FlavorProfileUpdate:
    fruity: float
    spicy: float
    woody: float
    sweet: float
    floral: float
    dry: float


@dataclass(frozen=True)
class TastingUpdate:
    tasting_date: str | None
    location: str | None
    notes: str | None
    nose: float | None
    palate: float | None
    finish: float | None
    balance: float | None


class RumService:
    def __init__(self, database_path: Path, source_owner_id: str):
        self.database_path = database_path
        self.source_owner_id = source_owner_id

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def list_rums(self, include_trash: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM rums WHERE source_user_id = ?"
        params: list[Any] = [self.source_owner_id]
        if not include_trash:
            sql += " AND status <> 'trash'"
        sql += " ORDER BY COALESCE(date_added, created_at) DESC, name COLLATE NOCASE"
        with db_session(self.database_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def list_trashed_rums(self) -> list[dict[str, Any]]:
        """Retourne uniquement les bouteilles présentes dans la corbeille."""
        with db_session(self.database_path) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM rums
                    WHERE source_user_id = ? AND status = 'trash'
                    ORDER BY COALESCE(date_added, created_at) DESC, name COLLATE NOCASE
                    """,
                    (self.source_owner_id,),
                ).fetchall()
            ]

    def get_rum(self, rum_id: str) -> dict[str, Any] | None:
        with db_session(self.database_path) as conn:
            row = conn.execute(
                "SELECT * FROM rums WHERE id = ? AND source_user_id = ?",
                (rum_id, self.source_owner_id),
            ).fetchone()
            return dict(row) if row else None

    def list_tastings(self, rum_id: str) -> list[dict[str, Any]]:
        # On vérifie aussi l'appartenance du rhum. Ainsi un id provenant d'une
        # autre cave ne permet pas de lire ses dégustations.
        with db_session(self.database_path) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT t.*
                    FROM tastings t
                    JOIN rums r ON r.id = t.rum_id
                    WHERE t.rum_id = ? AND r.source_user_id = ?
                    ORDER BY t.tasting_date DESC, t.tasting_index DESC
                    """,
                    (rum_id, self.source_owner_id),
                ).fetchall()
            ]

    # ------------------------------------------------------------------
    # Bouteilles
    # ------------------------------------------------------------------
    def create_rum(self, update: RumDetailsUpdate, access: AccessContext) -> str:
        """Crée une bouteille et retourne son UUID."""
        require_write(access)
        values = self._validate_rum_details(update)
        rum_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        with db_session(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO rums (
                    id, source_user_id, name, distillery, origin, type,
                    abv, price, age, status, fill_level, legacy_notes,
                    image_url, is_favorite, date_added, created_at,
                    acquisition_type, legacy_rating,
                    flavor_fruity, flavor_spicy, flavor_woody,
                    flavor_sweet, flavor_floral, flavor_dry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rum_id,
                    self.source_owner_id,
                    values["name"],
                    values["distillery"],
                    values["origin"],
                    values["type"],
                    values["abv"],
                    values["price"],
                    values["age"],
                    values["status"],
                    values["fill_level"],
                    values["legacy_notes"],
                    values["image_url"],
                    values["is_favorite"],
                    values["date_added"],
                    created_at,
                    values["acquisition_type"],
                    None,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        return rum_id

    def update_rum(self, rum_id: str, update: RumUpdate, access: AccessContext) -> None:
        """Compatibilité avec les petits formulaires déjà présents."""
        require_write(access)
        values = asdict(update)
        allowed = {k: v for k, v in values.items() if v is not None}
        if not allowed:
            return

        if "fill_level" in allowed:
            self._validate_range("Niveau", allowed["fill_level"], 0, 100)
        if "status" in allowed and allowed["status"] not in VALID_STATUSES:
            raise ValueError("Statut invalide.")
        if "is_favorite" in allowed:
            allowed["is_favorite"] = int(bool(allowed["is_favorite"]))

        setters = ", ".join(f"{key} = ?" for key in allowed)
        params = list(allowed.values()) + [rum_id, self.source_owner_id]
        with db_session(self.database_path) as conn:
            cur = conn.execute(
                f"UPDATE rums SET {setters} WHERE id = ? AND source_user_id = ?",
                params,
            )
            if cur.rowcount != 1:
                raise LookupError("Bouteille introuvable ou non autorisée.")

    def update_rum_details(
        self,
        rum_id: str,
        update: RumDetailsUpdate,
        access: AccessContext,
    ) -> None:
        """Met à jour les informations générales après validation côté service."""
        require_write(access)
        values = self._validate_rum_details(update)

        with db_session(self.database_path) as conn:
            cur = conn.execute(
                """
                UPDATE rums
                SET name = ?,
                    distillery = ?,
                    origin = ?,
                    type = ?,
                    abv = ?,
                    price = ?,
                    age = ?,
                    status = ?,
                    fill_level = ?,
                    legacy_notes = ?,
                    image_url = ?,
                    is_favorite = ?,
                    date_added = ?,
                    acquisition_type = ?
                WHERE id = ? AND source_user_id = ?
                """,
                (
                    values["name"],
                    values["distillery"],
                    values["origin"],
                    values["type"],
                    values["abv"],
                    values["price"],
                    values["age"],
                    values["status"],
                    values["fill_level"],
                    values["legacy_notes"],
                    values["image_url"],
                    values["is_favorite"],
                    values["date_added"],
                    values["acquisition_type"],
                    rum_id,
                    self.source_owner_id,
                ),
            )
            if cur.rowcount != 1:
                raise LookupError("Bouteille introuvable ou non autorisée.")

    def move_rum_to_trash(self, rum_id: str, access: AccessContext) -> None:
        """Déplace une bouteille dans la corbeille et mémorise son statut précédent."""
        require_write(access)
        with db_session(self.database_path) as conn:
            row = conn.execute(
                "SELECT status FROM rums WHERE id = ? AND source_user_id = ?",
                (rum_id, self.source_owner_id),
            ).fetchone()
            if row is None:
                raise LookupError("Bouteille introuvable ou non autorisée.")

            current_status = str(row["status"])
            if current_status == "trash":
                return

            conn.execute(
                """
                UPDATE rums
                SET status_before_trash = ?, status = 'trash'
                WHERE id = ? AND source_user_id = ?
                """,
                (current_status, rum_id, self.source_owner_id),
            )

    def restore_rum_from_trash(self, rum_id: str, access: AccessContext) -> str:
        """Restaure une bouteille dans son statut antérieur et retourne ce statut."""
        require_write(access)
        with db_session(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT status, status_before_trash
                FROM rums
                WHERE id = ? AND source_user_id = ?
                """,
                (rum_id, self.source_owner_id),
            ).fetchone()
            if row is None:
                raise LookupError("Bouteille introuvable ou non autorisée.")
            if row["status"] != "trash":
                raise ValueError("Cette bouteille n'est pas dans la corbeille.")

            previous_status = row["status_before_trash"]
            if previous_status not in {"owned", "wishlist", "tasted", "finished"}:
                previous_status = "owned"

            conn.execute(
                """
                UPDATE rums
                SET status = ?, status_before_trash = NULL
                WHERE id = ? AND source_user_id = ?
                """,
                (previous_status, rum_id, self.source_owner_id),
            )
            return str(previous_status)

    def update_flavor_profile(
        self,
        rum_id: str,
        update: FlavorProfileUpdate,
        access: AccessContext,
    ) -> None:
        """Met à jour les six dimensions du profil aromatique (échelle 0 à 10)."""
        require_write(access)
        values = asdict(update)
        for label, value in values.items():
            self._validate_range(f"Profil aromatique ({label})", value, 0, 10)

        with db_session(self.database_path) as conn:
            cur = conn.execute(
                """
                UPDATE rums
                SET flavor_fruity = ?,
                    flavor_spicy = ?,
                    flavor_woody = ?,
                    flavor_sweet = ?,
                    flavor_floral = ?,
                    flavor_dry = ?
                WHERE id = ? AND source_user_id = ?
                """,
                (
                    update.fruity,
                    update.spicy,
                    update.woody,
                    update.sweet,
                    update.floral,
                    update.dry,
                    rum_id,
                    self.source_owner_id,
                ),
            )
            if cur.rowcount != 1:
                raise LookupError("Bouteille introuvable ou non autorisée.")

    # ------------------------------------------------------------------
    # Dégustations
    # ------------------------------------------------------------------
    def create_tasting(
        self,
        rum_id: str,
        update: TastingUpdate,
        access: AccessContext,
    ) -> int:
        """Ajoute une dégustation et retourne son identifiant SQLite."""
        require_write(access)
        values = self._validate_tasting(update)

        with db_session(self.database_path) as conn:
            self._require_owned_rum(conn, rum_id)
            next_index = conn.execute(
                "SELECT COALESCE(MAX(tasting_index), -1) + 1 FROM tastings WHERE rum_id = ?",
                (rum_id,),
            ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO tastings (
                    rum_id, tasting_index, tasting_date, location, notes,
                    nose, palate, finish, balance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rum_id,
                    next_index,
                    values["tasting_date"],
                    values["location"],
                    values["notes"],
                    values["nose"],
                    values["palate"],
                    values["finish"],
                    values["balance"],
                ),
            )
            return int(cur.lastrowid)

    def update_tasting(
        self,
        rum_id: str,
        tasting_id: int,
        update: TastingUpdate,
        access: AccessContext,
    ) -> None:
        require_write(access)
        values = self._validate_tasting(update)

        with db_session(self.database_path) as conn:
            self._require_owned_rum(conn, rum_id)
            cur = conn.execute(
                """
                UPDATE tastings
                SET tasting_date = ?, location = ?, notes = ?,
                    nose = ?, palate = ?, finish = ?, balance = ?
                WHERE id = ? AND rum_id = ?
                """,
                (
                    values["tasting_date"],
                    values["location"],
                    values["notes"],
                    values["nose"],
                    values["palate"],
                    values["finish"],
                    values["balance"],
                    tasting_id,
                    rum_id,
                ),
            )
            if cur.rowcount != 1:
                raise LookupError("Dégustation introuvable ou non autorisée.")

    def delete_tasting(
        self,
        rum_id: str,
        tasting_id: int,
        access: AccessContext,
    ) -> None:
        require_write(access)
        with db_session(self.database_path) as conn:
            self._require_owned_rum(conn, rum_id)
            cur = conn.execute(
                "DELETE FROM tastings WHERE id = ? AND rum_id = ?",
                (tasting_id, rum_id),
            )
            if cur.rowcount != 1:
                raise LookupError("Dégustation introuvable ou non autorisée.")

    # ------------------------------------------------------------------
    # Validation / helpers privés
    # ------------------------------------------------------------------
    def _validate_rum_details(self, update: RumDetailsUpdate) -> dict[str, Any]:
        name = update.name.strip()
        if not name:
            raise ValueError("Le nom de la bouteille est obligatoire.")
        if update.status not in VALID_STATUSES:
            raise ValueError("Statut invalide.")
        if update.acquisition_type not in VALID_ACQUISITION_TYPES:
            raise ValueError("Mode d'acquisition invalide.")

        self._validate_range("Degré d'alcool", update.abv, 0, 100)
        self._validate_range("Prix", update.price, 0, None)
        self._validate_range("Niveau", update.fill_level, 0, 100)

        return {
            "name": name,
            "distillery": self._clean_text(update.distillery),
            "origin": self._clean_text(update.origin),
            "type": self._clean_text(update.type),
            "abv": update.abv,
            "price": update.price,
            "age": self._clean_text(update.age),
            "status": update.status,
            "fill_level": update.fill_level,
            "legacy_notes": self._clean_text(update.legacy_notes),
            "image_url": self._clean_text(update.image_url),
            "is_favorite": int(bool(update.is_favorite)),
            "date_added": update.date_added,
            "acquisition_type": update.acquisition_type,
        }

    def _validate_tasting(self, update: TastingUpdate) -> dict[str, Any]:
        for label, value in {
            "Nez": update.nose,
            "Bouche": update.palate,
            "Finale": update.finish,
            "Équilibre": update.balance,
        }.items():
            self._validate_range(label, value, 0, 10)

        return {
            "tasting_date": update.tasting_date,
            "location": self._clean_text(update.location),
            "notes": (update.notes or "").strip(),
            "nose": update.nose,
            "palate": update.palate,
            "finish": update.finish,
            "balance": update.balance,
        }

    def _require_owned_rum(self, conn: Any, rum_id: str) -> None:
        exists = conn.execute(
            "SELECT 1 FROM rums WHERE id = ? AND source_user_id = ?",
            (rum_id, self.source_owner_id),
        ).fetchone()
        if exists is None:
            raise LookupError("Bouteille introuvable ou non autorisée.")

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _validate_range(
        label: str,
        value: float | int | None,
        minimum: float | None,
        maximum: float | None,
    ) -> None:
        if value is None:
            return
        number = float(value)
        if minimum is not None and number < minimum:
            raise ValueError(f"{label} doit être supérieur ou égal à {minimum}.")
        if maximum is not None and number > maximum:
            raise ValueError(f"{label} doit être inférieur ou égal à {maximum}.")
