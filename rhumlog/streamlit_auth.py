from __future__ import annotations

import streamlit as st

from rhumlog.access import AccessContext
from rhumlog.config import Settings


def get_access(settings: Settings) -> AccessContext:
    # Le mode public est toujours lecture seule, même si une variable de développement
    # ou un fournisseur OIDC était configuré par erreur.
    if settings.public_demo:
        return AccessContext(is_authenticated=False, can_write=False, email=None)

    # Local development escape hatch. Never enable in production.
    if settings.dev_owner:
        return AccessContext(is_authenticated=True, can_write=True, email=settings.owner_email)

    is_logged_in = bool(getattr(st.user, "is_logged_in", False))
    email = None
    if is_logged_in:
        try:
            email = st.user.get("email")
        except Exception:
            email = getattr(st.user, "email", None)

    can_write = bool(
        is_logged_in
        and settings.owner_email
        and email
        and email.casefold() == settings.owner_email.casefold()
    )
    return AccessContext(is_authenticated=is_logged_in, can_write=can_write, email=email)


def auth_is_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False
