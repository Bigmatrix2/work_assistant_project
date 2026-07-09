"""
Configuration centrale de l'assistant Code du travail.
Toutes les valeurs modifiables (chemins, modèles, seuils) sont ici,
pour eviter les "magic numbers" disperses dans le code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Chemins ---
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SEED_CORPUS_PATH = DATA_DIR / "seed_corpus.json"
CORPUS_PATH = DATA_DIR / "corpus.json"           # corpus "vivant", après nettoyage/enrichissement
CHROMA_PERSIST_DIR = str(DATA_DIR / "chroma_db")  # base vectorielle persistee
BM25_INDEX_PATH = DATA_DIR / "bm25_index.pkl"     # index lexical persiste
INDEX_META_PATH = DATA_DIR / "index_meta.json"    # trace le modèle d'embedding utilise, dates, hash

# --- Embeddings ---
# Modèle multilingue, léger, bon compromis qualite/vitesse pour du francais juridique.
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# --- Chunking ---
# Stratégie retenue (voir README, Q1) : chunking par article (granularite fine),
# avec un chunk "resume de section" supplémentaire par thème pour les questions transverses.
CHUNK_MAX_CHARS = 1200          # au-dela, un article est redecoupe (rare, la plupart des articles sont courts)
CHUNK_OVERLAP_CHARS = 150

# --- Recherche ---
TOP_K_VECTOR = 8
TOP_K_BM25 = 8
TOP_K_FINAL = 5                 # nombre de chunks envoyes au LLM après fusion RRF
RRF_K = 60                      # constante standard de la Reciprocal Rank Fusion

# Deux seuils distincts sur le meilleur score cosine (score de confiance) :
#   - CONFIDENCE_THRESHOLD : sous ce seuil, on avertit l'utilisateur mais on
#     appelle quand même le LLM (la question est peut-être dans le corpus,
#     juste mal formulee).
#   - HARD_REFUSAL_THRESHOLD : sous ce seuil (plus bas), on considère que le
#     corpus n'a AUCUN rapport avec la question -> refus garanti par le CODE,
#     sans même appeler le LLM. Cela ferme la faille identifiée en test : un
#     retrieval qui remonte toujours des chunks (même hors-sujet) faisait
#     reposer le refus uniquement sur le prompt.
#
# Valeurs calibrees empiriquement avec tests/calibrate_confidence.py sur le
# corpus de 40 articles (voir COMPTE_RENDU.md pour le detail des mesures) :
#   - score min observe sur des questions reellement dans le corpus : 0.42
#   - score max observe sur du hors-sujet évident : 0.34
#   - score max observe sur des "pieges" juridiques proches (retraite
#     complementaire, fonction publique) : 0.50 -> RECOUVREMENT réel avec le
#     corpus. Un seuil unique ne sépare donc pas parfaitement tous les cas :
#     HARD_REFUSAL_THRESHOLD est fixe sous le minimum du corpus (jamais de
#     refus a tort d'une vraie question), au prix de laisser passer certains
#     pieges vers le LLM plutot que vers le refus sans appel. Le prompt de
#     génération sert de seconde ligne de defense sur ces cas ambigus.
#
# Recalibre une seconde fois apres correction des accents dans le corpus et
# les prompts : les embeddings sont sensibles a l'orthographe, le score du
# hors-sujet evident est passe de 0.28 a 0.34 apres correction. Preuve que
# la calibration doit etre relancee apres tout changement du texte source,
# pas seulement apres un changement de corpus au sens strict.
CONFIDENCE_THRESHOLD = 0.35
HARD_REFUSAL_THRESHOLD = 0.38

# --- LLM (Groq) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE = 0.1          # basse temperature : on veut de la precision, pas de la creativite
GROQ_MAX_TOKENS = 800

# --- Disclaimer juridique ---
# Ajoute par le CODE (pas seulement demande dans le prompt) pour garantir sa presence a 100%.
# Voir README, réponse a la question "avertissement juridique - contrainte technique".
LEGAL_DISCLAIMER = (
    "\n\n---\n"
    "*Cet assistant ne fournit pas de conseil juridique. "
    "Consultez un avocat ou l'inspection du travail pour votre situation personnelle.*"
)

CORPUS_DATE_NOTICE_TEMPLATE = (
    "Corpus a jour au {date}. Le droit du travail évolue (lois, ordonnances, jurisprudence) : "
    "verifiez les articles cites sur legifrance.gouv.fr avant toute decision."
)

# --- API Légifrance / PISTE ("agent récupérateur de référence") ---
# Vérifie en temps réel, après génération de la réponse, que le texte des
# articles cités correspond à la version actuellement en vigueur sur
# Légifrance. Post-traitement DÉTERMINISTE (pas d'appel outil par le LLM) :
# plus simple, plus prévisible, plus facile à expliquer à l'oral.
#
# Inscription gratuite sur https://piste.gouv.fr/registration puis création
# d'une application (sandbox suffit pour un usage pédagogique - pas besoin
# de valider les CGU de production). Récupérer Client ID et Client Secret
# dans l'onglet "Applications" de PISTE, les mettre dans .env.
PISTE_CLIENT_ID = os.getenv("PISTE_CLIENT_ID", "")
PISTE_CLIENT_SECRET = os.getenv("PISTE_CLIENT_SECRET", "")
# Sandbox par défaut : gratuit, sans validation de CGU supplémentaire,
# suffisant pour un usage pédagogique. Passer à False nécessite d'avoir
# validé les CGU de production sur PISTE (voir README).
PISTE_SANDBOX = os.getenv("PISTE_SANDBOX", "true").lower() != "false"

if PISTE_SANDBOX:
    PISTE_OAUTH_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
    PISTE_API_BASE = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"
else:
    PISTE_OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
    PISTE_API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

# Nom exact du code tel qu'attendu par le filtre "NOM_CODE" de l'API de recherche.
LEGIFRANCE_CODE_NAME = "Code du travail"

# Délai (secondes) au-delà duquel on abandonne l'appel Légifrance plutôt que
# de faire attendre l'utilisateur : la vérification est un bonus, jamais un
# blocage du pipeline principal.
PISTE_TIMEOUT_SECONDS = 5
