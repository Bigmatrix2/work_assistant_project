"""
Agent récupérateur de référence (post-traitement déterministe).

Après que generation.py a produit une réponse citant des numéros d'articles,
ce module vérifie, pour chacun, si le texte de notre corpus local correspond
encore à la version actuellement en vigueur sur Légifrance. C'est la réponse
concrète à la question de réflexion 3 (fraîcheur) : plutôt que de simplement
afficher une date de corpus, on vérifie activement.

Design volontairement simple :
    - un appel Légifrance par article cité (pas de traitement en lot,
      l'API PISTE ne l'exige pas et ça garde le code lisible)
    - comparaison de texte normalisée (espaces/casse), pas de diff
      caractère par caractère : on veut détecter un changement de fond,
      pas une différence de mise en forme
    - dégradation silencieuse : si Légifrance est indisponible ou si les
      identifiants PISTE ne sont pas configurés, on ne bloque jamais la
      réponse principale, on ajoute juste une note discrète
"""

import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.legifrance_client import get_current_article_text, credentials_configured


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def check_article_freshness(article_id: str, local_texte: str) -> dict:
    """Compare le texte local d'un article à sa version actuelle sur
    Légifrance. Retourne un statut : 'identique', 'different', ou
    'indisponible' (API injoignable, article non trouvé, etc.)."""
    texte_actuel = get_current_article_text(article_id)
    if texte_actuel is None:
        return {"article_id": article_id, "statut": "indisponible", "texte_actuel": None}

    if _normalize(texte_actuel) == _normalize(local_texte):
        return {"article_id": article_id, "statut": "identique", "texte_actuel": texte_actuel}

    return {"article_id": article_id, "statut": "different", "texte_actuel": texte_actuel}


def check_references(article_ids: list, local_texts: dict) -> str:
    """Vérifie une liste d'articles cités et retourne une courte note à
    ajouter à la réponse finale. `local_texts` est un dict
    {article_id: texte_brut} tiré des métadonnées des chunks déjà retrouvés
    (pas besoin de recharger le corpus depuis le disque).

    Retourne une chaîne vide si aucune vérification n'a pu être faite
    (identifiants PISTE non configurés) - dans ce cas on ne mentionne même
    pas la fonctionnalité, pour ne pas alourdir la réponse pour les
    utilisateurs qui n'ont pas configuré Légifrance.
    """
    if not credentials_configured():
        return ""

    results = []
    for article_id in article_ids:
        local_texte = local_texts.get(article_id)
        if not local_texte:
            continue
        results.append(check_article_freshness(article_id, local_texte))

    if not results:
        return ""

    changed = [r for r in results if r["statut"] == "different"]
    unavailable = [r for r in results if r["statut"] == "indisponible"]
    confirmed = [r for r in results if r["statut"] == "identique"]

    lines = ["\n\n*Vérification en direct auprès de Légifrance :*"]
    if confirmed:
        lines.append(
            f"- {', '.join(r['article_id'] for r in confirmed)} : texte confirmé à jour."
        )
    if changed:
        lines.append(
            f"- ⚠️ {', '.join(r['article_id'] for r in changed)} : le texte semble avoir "
            "changé depuis l'indexation. Vérifiez la version actuelle sur legifrance.gouv.fr."
        )
    if unavailable:
        lines.append(
            f"- {', '.join(r['article_id'] for r in unavailable)} : vérification impossible "
            "pour le moment (API Légifrance indisponible ou article non retrouvé)."
        )

    return "\n".join(lines)


if __name__ == "__main__":
    # Test rapide : simule un article local legerement modifie pour verifier
    # que la detection de changement fonctionne (necessite PISTE_CLIENT_ID/
    # PISTE_CLIENT_SECRET configures dans .env).
    fake_local_texts = {
        "L3141-3": "Texte volontairement different pour tester la detection.",
    }
    note = check_references(["L3141-3"], fake_local_texts)
    print(note if note else "Aucune verification effectuee (identifiants PISTE absents ?).")
