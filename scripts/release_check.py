from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED = {
    ".env",
    ".streamlit/secrets.toml",
}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".sql"}
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def _fail(message: str) -> None:
    raise SystemExit(f"RELEASE CHECK FAILED · {message}")


def _tracked_files() -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _check_tracked_files() -> None:
    tracked = _tracked_files()
    for name in tracked:
        path = Path(name)
        if name in FORBIDDEN_TRACKED:
            _fail(f"fichier privé suivi par Git : {name}")
        if path.suffix.casefold() in FORBIDDEN_SUFFIXES and not name.startswith("demo_data/"):
            _fail(f"artefact privé potentiellement suivi par Git : {name}")
        if name.startswith("private_exports/"):
            _fail(f"export privé suivi par Git : {name}")


def _read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / "demo_data" / name
    if not path.exists():
        _fail(f"snapshot incomplet : {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _check_public_snapshot() -> tuple[int, int, int]:
    rums = _read_csv("rums.csv")
    tastings = _read_csv("tastings.csv")
    profiles = _read_csv("sensory_profiles.csv")

    if not rums:
        _fail("aucune référence dans demo_data/rums.csv")
    if any(row.get("source_user_id") != "demo" for row in rums):
        _fail("source_user_id public différent de 'demo'")
    if any(not row.get("id", "").startswith("demo-rum-") for row in rums):
        _fail("identifiant de bouteille non remappé")
    if any(row.get("status") == "trash" for row in rums):
        _fail("élément de corbeille présent dans le snapshot")
    if any(row.get("location", "").strip() or row.get("notes", "").strip() for row in tastings):
        _fail("champ libre de dégustation présent dans le snapshot")
    if any(row.get("source_text", "").strip() for row in profiles):
        _fail("texte source sensoriel présent dans le snapshot")

    for path in sorted((ROOT / "demo_data").glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        if UUID_RE.search(text):
            _fail(f"UUID historique détecté dans {path.name}")
        if EMAIL_RE.search(text):
            _fail(f"email détecté dans {path.name}")

    return len(rums), len(tastings), len(profiles)


def _check_version() -> str:
    namespace: dict[str, object] = {}
    exec((ROOT / "rhumlog" / "__init__.py").read_text(encoding="utf-8"), namespace)
    version = str(namespace.get("__version__", ""))
    if not re.fullmatch(r"3\.0\.0(?:-rc\d+)?", version):
        _fail(f"version inattendue pour la release portfolio : {version!r}")
    return version


def main() -> None:
    _check_tracked_files()
    rums, tastings, profiles = _check_public_snapshot()
    version = _check_version()

    print(f"Version : {version}")
    print(f"Snapshot public : {rums} références · {tastings} dégustations · {profiles} profils sensoriels")
    print("Fichiers privés suivis : aucun détecté")
    print("UUID / emails dans demo_data : aucun détecté")
    print("Release check : OK")


if __name__ == "__main__":
    main()
