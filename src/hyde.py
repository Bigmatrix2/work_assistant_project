"""
HyDE - Hypothetical Document Embeddings (Jalon 6, amélioration).

Principe : les questions des utilisateurs sont formulees en langage familier
("je peux me faire virer sans preavis ?"), alors que les articles de loi sont
rediges dans un style juridique très different. Cet ecart de style dégrade
la recherche vectorielle (l'embedding de la question "familiere" est loin de
l'embedding de l'article "juridique"), même quand le contenu correspond.

HyDE resout cela en generant d'abord une RÉPONSE hypothetique (fausse, mais
stylistiquement proche d'un article de loi) a la question, et en embeddant
cette réponse hypothetique plutot que la question brute. On recherche alors
"style juridique contre style juridique", ce qui améliore le rappel.

Attention : le document hypothetique n'est JAMAIS montre a l'utilisateur ni
utilise comme source ; il sert uniquement a orienter la recherche.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.groq_client import chat

HYDE_SYSTEM_PROMPT = (
    "Tu es un assistant qui redige un court extrait FICTIF de code du travail "
    "francais, dans un style juridique et factuel, en réponse a la question "
    "posee. Ce texte ne sera jamais montre a l'utilisateur : il sert uniquement "
    "a orienter une recherche documentaire. Reponds en 2 a 4 phrases maximum, "
    "sans numéro d'article invente, sans preambule, uniquement le style et le "
    "vocabulaire juridique attendus."
)


def generate_hypothetical_document(question: str) -> str:
    """Génère un court texte hypothetique stylistiquement proche d'un article
    de loi, utilise ensuite comme requete d'embedding a la place de la
    question brute (ou en complement)."""
    try:
        return chat(HYDE_SYSTEM_PROMPT, question, temperature=0.3, max_tokens=150)
    except Exception as exc:
        # Fallback : si l'appel LLM échoue (reseau, quota...), on retombe
        # simplement sur la question brute plutot que de bloquer la recherche.
        print(f"[HyDE] Appel LLM indisponible ({exc}), repli sur la question brute.")
        return question


if __name__ == "__main__":
    q = "Je peux me faire virer sans preavis ?"
    print(generate_hypothetical_document(q))
