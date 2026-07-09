"""
Calibration du score de confiance (Jalon 6).

Les seuils CONFIDENCE_THRESHOLD et HARD_REFUSAL_THRESHOLD dans config.py sont
des valeurs de DEPART, pas des verites universelles : le bon seuil dépend de
votre corpus (taille, densite) et de votre modèle d'embedding. Ce script vous
aide a les calibrer empiriquement.

Usage :
    python -m tests.calibrate_confidence

Il affiche le meilleur score cosine pour :
  - des questions clairement DANS le corpus (devrait être élevé)
  - des questions clairement HORS corpus (devrait être bas)

Regardez l'ecart entre les deux groupes : HARD_REFUSAL_THRESHOLD doit se
situer sous le score minimum du groupe "dans le corpus", et au-dessus du
score maximum du groupe "hors corpus". S'il y a un recouvrement, c'est le
signe qu'il faut soit enrichir le corpus, soit changer de modèle
d'embedding, soit accepter un compromis (documentez le choix dans le
compte rendu).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.retrieval import hybrid_search
from src.config import CONFIDENCE_THRESHOLD, HARD_REFUSAL_THRESHOLD

IN_CORPUS_QUESTIONS = [
    # Durée du travail et heures supplémentaires
    "Quelle est la durée légale du travail par semaine ?",
    "Comment sont majorees les heures supplémentaires ?",
    # Conges payes
    "Combien de jours de conges payes acquiert-on par mois ?",
    "Qu'est-ce que le conge supplémentaire de fractionnement ?",
    # Contrat de travail (CDI, CDD)
    "Quelle est la durée maximale d'un CDD ?",
    "Dans quels cas peut-on conclure un CDD ?",
    # Licenciement
    "Quelle est la durée du preavis en cas de licenciement ?",
    "Comment se déroule l'entretien prealable a un licenciement ?",
    # Rupture conventionnelle
    "Comment fonctionne la rupture conventionnelle ?",
    "Quel est le délai de retractation après une rupture conventionnelle ?",
    # Salaire minimum (SMIC)
    "Qu'est-ce que le SMIC ?",
    "Le SMIC peut-il baisser d'une année sur l'autre ?",
    # Representation du personnel
    "Comment est compose le comite social et economique ?",
    "A partir de combien de salaries doit-on mettre en place un CSE ?",
    # Harcelement et discrimination
    "Qu'est-ce que le harcelement moral au travail ?",
    "Quelle est la définition du harcelement sexuel dans le Code du travail ?",
]

OUT_OF_CORPUS_QUESTIONS = [
    # Hors-sujet évident (aucun lien avec le droit ou le travail)
    "Quelles sont les règles de circulation routiere ?",
    "Comment faire une tarte aux pommes ?",
    "Quelle est la capitale de l'Australie ?",
    "Comment fonctionne un moteur a combustion ?",
    "Quel est le prix d'un billet d'avion Paris-Tokyo ?",
    "Quelle est la meilleure façon d'apprendre le piano ?",
    # "Pieges" : domaine juridique ou proche du travail, mais PAS couvert par
    # ce corpus (droit fiscal, droit des societes, secteur public, droit
    # pénal général, protection sociale hors droit du travail). Plus utiles
    # pour la calibration qu'un hors-sujet évident, car plus proches en
    # style/vocabulaire de nos articles.
    "Quel est le taux d'imposition sur les societes en France ?",
    "Comment créer une SARL ?",
    "Quelles sont les règles de la fonction publique territoriale ?",
    "Quelle est la procédure de divorce par consentement mutuel ?",
    "Comment fonctionne le regime de retraite complementaire Agirc-Arrco ?",
    "Quels sont les delits routiers passibles de prison ?",
]


def calibrate() -> None:
    print("=== Questions DANS le corpus (score attendu : élevé) ===")
    in_scores = []
    for q in IN_CORPUS_QUESTIONS:
        result = hybrid_search([q], use_hyde=False)  # sans HyDE : plus rapide, deterministe
        in_scores.append(result["confidence"])
        print(f"  {result['confidence']:.4f} | {q}")

    print("\n=== Questions HORS corpus (score attendu : bas) ===")
    out_scores = []
    trap_start_index = 6  # les 6 premieres sont evidentes, le reste = "pieges" juridiques proches
    for i, q in enumerate(OUT_OF_CORPUS_QUESTIONS):
        result = hybrid_search([q], use_hyde=False)
        out_scores.append(result["confidence"])
        tag = " [piege]" if i >= trap_start_index else ""
        print(f"  {result['confidence']:.4f} | {q}{tag}")

    trap_scores = out_scores[trap_start_index:]
    obvious_scores = out_scores[:trap_start_index]

    print(f"\nMin score (dans le corpus)          : {min(in_scores):.4f}")
    print(f"Max score (hors-sujet evident)       : {max(obvious_scores):.4f}")
    print(f"Max score (pieges juridiques proches) : {max(trap_scores):.4f}")
    print(f"\nSeuils actuels : CONFIDENCE_THRESHOLD={CONFIDENCE_THRESHOLD}, "
          f"HARD_REFUSAL_THRESHOLD={HARD_REFUSAL_THRESHOLD}")

    max_out = max(out_scores)
    if max_out < min(in_scores):
        gap_low, gap_high = max_out, min(in_scores)
        suggested = round((gap_low + gap_high) / 2, 3)
        print(f"\nBon signe : aucun recouvrement entre les deux groupes (pieges inclus). "
              f"Un HARD_REFUSAL_THRESHOLD autour de {suggested} separerait parfaitement "
              f"vos deux groupes de test.")
    else:
        print("\nATTENTION : recouvrement entre les scores in/out corpus "
              "(verifiez si le recouvrement vient des pieges ou du hors-sujet évident). "
              "Un seuil unique ne separera pas parfaitement tous les cas. "
              "A documenter dans le compte rendu comme limite connue.")


if __name__ == "__main__":
    calibrate()
