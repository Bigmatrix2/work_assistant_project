"""
Mise a jour du corpus (freshness, Q3 du README).

Le droit du travail change souvent (lois, ordonnances, jurisprudence qui fait
évoluer la portee d'un article). Ce script permet de relancer le pipeline de
preparation + chunking + indexation SANS tout reembedder : seuls les articles
dont le hash a change (texte modifié) ou qui sont nouveaux sont re-encodes.

Usage :
    python -m src.update_corpus                 # reconstruit depuis seed_corpus.json
    python -m src.update_corpus --source fichier.json   # depuis un autre corpus (option A/B)

Dans un vrai deploiement (option A, API Legifrance), on remplacerait la
lecture de seed_corpus.json par un appel a l'API pour récupérer les articles
dont la date de dernière modification est postérieure a la dernière
execution -- la logique de hash/upsert ci-dessous reste identique.
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import SEED_CORPUS_PATH, CORPUS_PATH
from src.corpus_builder import build_corpus
from src.chunking import build_chunks
from src.indexing import index_chunks, load_index_meta


def run_update(source_path: Path = SEED_CORPUS_PATH) -> None:
    print(f"--- Mise a jour du corpus depuis {source_path} ---")

    previous_meta = load_index_meta()
    if previous_meta:
        print(f"Derniere indexation : {previous_meta.get('last_index_run')} "
              f"({previous_meta.get('total_chunks')} chunks, "
              f"modèle {previous_meta.get('embedding_model')})")
    else:
        print("Aucun index existant : première indexation complète.")

    documents = build_corpus(seed_path=source_path, output_path=CORPUS_PATH)
    chunks = build_chunks(documents)
    stats = index_chunks(chunks)

    print(f"\nMise a jour terminee : {stats['embedded']} article(s) nouveau(x) ou modifie(s), "
          f"{stats['unchanged']} inchange(s) et donc non re-embedde(s).")
    print("Le système peut être relance immédiatement : la base est déjà persistee.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mise a jour incrementale du corpus.")
    parser.add_argument("--source", type=str, default=str(SEED_CORPUS_PATH),
                         help="Chemin vers un fichier corpus JSON (même format que seed_corpus.json).")
    args = parser.parse_args()
    run_update(Path(args.source))
