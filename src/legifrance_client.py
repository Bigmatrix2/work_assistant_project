"""
Client pour l'API Légifrance (plateforme PISTE).

Implémente l'"agent récupérateur de référence" recommandé : après que le
LLM a produit une réponse citant des numéros d'articles, ce module va
chercher le texte OFFICIEL ACTUELLEMENT EN VIGUEUR de ces articles
directement sur Légifrance, pour verifier la fraîcheur de notre corpus local
(voir README, question de réflexion 3).

Choix de conception : post-traitement déterministe, pas d'appel outil par
le LLM (pas de "function calling" Groq). Après génération de la réponse,
NOTRE code Python appelle l'API Légifrance directement - aucune fusion
technique n'est nécessaire entre l'API Groq et l'API Légifrance, ce sont
deux appels HTTP indépendants orchestrés l'un après l'autre.

Flux d'authentification : OAuth2 "client credentials" (RFC 6749 §4.4).
    1. POST PISTE_OAUTH_URL avec client_id/client_secret -> jeton d'accès
    2. Le jeton est joint a chaque appel de l'API Légifrance (Bearer token)
    3. Pour retrouver un article par son NUMÉRO (ex: "L3121-27"), il faut
       d'abord une recherche (POST /search) qui renvoie l'identifiant
       interne Légifrance (LEGIARTI...), puis un second appel
       (POST /consult/getArticle) qui renvoie le texte.

Toute erreur (identifiants absents, API indisponible, article introuvable)
est interceptée et renvoie None plutôt que de lever une exception : cette
vérification est un bonus, elle ne doit jamais bloquer le pipeline principal
si Légifrance est indisponible ou si l'utilisateur n'a pas encore configuré
de compte PISTE.
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import (
    PISTE_CLIENT_ID, PISTE_CLIENT_SECRET, PISTE_OAUTH_URL, PISTE_API_BASE,
    LEGIFRANCE_CODE_NAME, PISTE_TIMEOUT_SECONDS,
)

_token_cache = {"access_token": None, "expires_at": 0}


def credentials_configured() -> bool:
    return bool(PISTE_CLIENT_ID and PISTE_CLIENT_SECRET)


def get_access_token():
    """Récupère un jeton OAuth2 (mis en cache jusqu'à expiration).

    Retourne None si les identifiants ne sont pas configurés ou si
    l'authentification échoue (réseau, identifiants invalides...).
    """
    if not credentials_configured():
        print(
            "[Légifrance] PISTE_CLIENT_ID ou PISTE_CLIENT_SECRET manquant dans .env "
            "(vérification effectuée sans afficher les valeurs)."
        )
        return None

    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    # Diagnostic minimal (une seule fois par session, uniquement lors d'une
    # vraie requete de jeton), sans jamais afficher le secret en clair :
    # aide a detecter un identifiant vide, tronque, ou entoure de
    # guillemets/espaces accidentels lors de la copie depuis PISTE.
    masked_id = PISTE_CLIENT_ID[:4] + "..." if len(PISTE_CLIENT_ID) > 4 else "(vide ou trop court)"
    print(f"[Légifrance] Authentification PISTE (Client ID : {masked_id}...).")

    import requests
    try:
        response = requests.post(
            PISTE_OAUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": PISTE_CLIENT_ID,
                "client_secret": PISTE_CLIENT_SECRET,
                "scope": "openid",
            },
            timeout=PISTE_TIMEOUT_SECONDS,
        )
        if not response.ok:
            # Affiche le corps de la reponse : PISTE y met le vrai motif
            # (identifiants invalides, application non activee, etc.),
            # bien plus utile que le code HTTP seul pour diagnostiquer.
            print(
                f"[Légifrance] Authentification refusée (HTTP {response.status_code}). "
                f"Détail du serveur : {response.text[:500]}"
            )
            return None
        data = response.json()
        _token_cache["access_token"] = data["access_token"]
        # Marge de securite de 30s avant l'expiration reelle du jeton.
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 30
        return _token_cache["access_token"]
    except Exception as exc:
        print(f"[Légifrance] Authentification impossible ({exc}).")
        return None


def search_article_internal_id(article_number: str, code_name: str = LEGIFRANCE_CODE_NAME):
    """Étape 1 : retrouve l'identifiant interne Légifrance (LEGIARTI...)
    correspondant à un numéro d'article (ex: "L3121-27") dans un code donné.

    Retourne None si le jeton est indisponible, si l'appel échoue, ou si
    aucun résultat n'est trouvé.
    """
    token = get_access_token()
    if not token:
        return None

    import requests
    payload = {
        "recherche": {
            "champs": [{
                "typeChamp": "NUM_ARTICLE",
                "criteres": [{"typeRecherche": "EXACTE", "valeur": article_number, "operateur": "ET"}],
                "operateur": "ET",
            }],
            "filtres": [{"facette": "NOM_CODE", "valeurs": [code_name]}],
            "pageNumber": 1,
            "pageSize": 1,
            "operateur": "ET",
            "sort": "PERTINENCE",
            "typePagination": "DEFAUT",
        },
        "fond": "CODE_DATE",
    }
    try:
        response = requests.post(
            f"{PISTE_API_BASE}/search",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=PISTE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or []
        if not results:
            print(f"[Légifrance] Recherche de {article_number} : aucun résultat. "
                  f"Réponse brute (300 premiers caractères) : {str(data)[:300]}")
            return None

        # L'identifiant LEGIARTI (article precis) est niche dans
        # results[].sections[].extracts[], pas au niveau racine du resultat
        # (qui ne contient que l'identifiant LEGITEXT du CODE entier). On
        # parcourt tous les extraits de tous les resultats/sections, on ne
        # garde que ceux dont le numero correspond exactement a l'article
        # recherche, et on privilegie la version actuellement en vigueur
        # (dateFin absente/null = toujours applicable) si plusieurs versions
        # historiques du meme article apparaissent.
        matching_extracts = []
        for result in results:
            for section in (result.get("sections") or []):
                for extract in (section.get("extracts") or []):
                    if extract.get("num") == article_number and extract.get("id"):
                        matching_extracts.append(extract)

        if not matching_extracts:
            print(f"[Légifrance] Aucun extrait correspondant exactement a {article_number} "
                  f"trouve dans les sections/extraits de la reponse.")
            return None

        # Priorite aux extraits sans date de fin (version actuellement en
        # vigueur) ; a defaut, on prend le premier trouve.
        currently_in_force = [e for e in matching_extracts if not e.get("dateFin")]
        chosen = currently_in_force[0] if currently_in_force else matching_extracts[0]
        return chosen["id"]
    except Exception as exc:
        print(f"[Légifrance] Recherche de l'article {article_number} impossible ({exc}).")
        return None


def get_article_text_by_internal_id(legiarti_id: str):
    """Étape 2 : récupère le texte actuel d'un article à partir de son
    identifiant interne Légifrance (LEGIARTI...). Retourne le dict
    "article" de la réponse (contient notamment "texte"), ou None."""
    token = get_access_token()
    if not token:
        return None

    import requests
    try:
        response = requests.post(
            f"{PISTE_API_BASE}/consult/getArticle",
            json={"id": legiarti_id},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=PISTE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        article = response.json().get("article")
        if not article:
            print(f"[Légifrance] Réponse getArticle sans clé 'article' pour {legiarti_id}. "
                  f"Réponse brute (300 premiers caractères) : {str(response.json())[:300]}")
        return article
    except Exception as exc:
        print(f"[Légifrance] Récupération du texte de {legiarti_id} impossible ({exc}).")
        return None


def get_current_article_text(article_number: str):
    """Fonction de haut niveau utilisée par le reste du pipeline : à partir
    d'un numéro d'article tel qu'utilisé dans notre corpus (ex: "L3121-27"),
    renvoie le texte actuellement en vigueur sur Légifrance, ou None si
    indisponible pour n'importe quelle raison (identifiants absents, article
    introuvable, API indisponible...).
    """
    if not credentials_configured():
        return None
    internal_id = search_article_internal_id(article_number)
    if not internal_id:
        return None
    article = get_article_text_by_internal_id(internal_id)
    if not article:
        return None
    return article.get("texte")


if __name__ == "__main__":
    test_article = "L3141-3"
    texte = get_current_article_text(test_article)
    if texte:
        print(f"Texte actuel de l'article {test_article} :\n{texte}")
    else:
        print(
            "Aucun résultat (vérifiez PISTE_CLIENT_ID/PISTE_CLIENT_SECRET dans .env, "
            "ou que l'API Légifrance est accessible)."
        )