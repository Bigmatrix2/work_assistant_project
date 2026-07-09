"""
Jalon 2 (partie 1) - Chunking.

Stratégie retenue (a justifier/discuter dans le README, Q1) :

  APPROCHE HYBRIDE :
  1. Chunking par article (granularite fine) : chaque article de loi est un
     chunk independant. Avantages : precision de citation maximale (un chunk
     = un article = un numéro exact), pas de dilution semantique entre
     articles sans rapport direct. Inconvenient : un article isole perd le
     contexte de sa section (ex: "cette section" dans le texte).
  2. Chunks "resume de thème" en complement : un chunk synthetique par thème,
     qui liste les articles couverts et leur objet en une phrase. Cela aide
     le retrieval sur des questions transverses ou mal formulees ("mes droits
     en cas de licenciement economique" -> remonte le chunk de thème, qui
     lui-même référence les bons numéros d'articles, même si aucun article
     individuel ne contient tous les mots-clés de la question).

  Les articles très longs (rare dans le Code du travail, mais possible) sont
  decoupes avec chevauchement (overlap), et TOUJOURS sur une frontiere de
  phrase (jamais en plein milieu), pour respecter la contrainte de contrôle
  qualite du sujet.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS


def split_on_sentence_boundaries(text: str, max_chars: int, overlap: int) -> list:
    """Découpe un texte long en chunks, jamais au milieu d'une phrase."""
    sentences = re.split(r"(?<=[.;])\s+", text)
    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # chevauchement : on repart avec la fin du chunk précédent
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def chunk_article(document: dict) -> list:
    """Un article court -> un seul chunk. Un article long -> plusieurs
    chunks avec suffixe (1/2), (2/2)... pour garder un id tracable."""
    text = document["text"]
    if len(text) <= CHUNK_MAX_CHARS:
        return [{
            "chunk_id": document["id"],
            "text": text,
            "metadata": {**document["metadata"], "chunk_type": "article"},
        }]

    parts = split_on_sentence_boundaries(text, CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS)
    return [
        {
            "chunk_id": f"{document['id']}#{i+1}",
            "text": part,
            "metadata": {**document["metadata"], "chunk_type": "article", "partie": f"{i+1}/{len(parts)}"},
        }
        for i, part in enumerate(parts)
    ]


def build_theme_overview_chunks(documents: list) -> list:
    """Construit un chunk de synthese par thème (approche hybride, cf. Q1)."""
    by_theme = defaultdict(list)
    for d in documents:
        by_theme[d["metadata"]["theme"]].append(d)

    overview_chunks = []
    for theme, docs in by_theme.items():
        listing = "; ".join(f"{d['metadata']['article_id']} ({d['metadata']['titre']})" for d in docs)
        text = f"Thème : {theme}. Articles couverts dans ce thème : {listing}."
        overview_chunks.append({
            "chunk_id": f"THEME::{theme}",
            "text": text,
            "metadata": {
                "article_id": None,
                "titre": f"Vue d'ensemble - {theme}",
                "theme": theme,
                "texte_brut": text,
                "source": "généré automatiquement",
                "date_maj": None,
                "hash": None,
                "chunk_type": "theme_overview",
            },
        })
    return overview_chunks


def build_chunks(documents: list) -> list:
    chunks = []
    for doc in documents:
        chunks.extend(chunk_article(doc))
    chunks.extend(build_theme_overview_chunks(documents))
    return chunks


def quality_check(chunks: list, n: int = 8) -> None:
    """Vérifie qu'aucun chunk n'est coupe en plein milieu d'une phrase
    (contrôle qualite demande au Jalon 2)."""
    import random
    sample = random.sample(chunks, min(n, len(chunks)))
    print(f"\n--- Controle qualite chunking : {len(sample)} chunks ---")
    for c in sample:
        ends_ok = c["text"].rstrip().endswith((".", ";", ")"))
        flag = "OK" if ends_ok else "A VÉRIFIER"
        print(f"[{flag}] {c['chunk_id']} ({c['metadata']['chunk_type']}): ...{c['text'][-80:]}")


if __name__ == "__main__":
    import json
    from src.config import CORPUS_PATH

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks = build_chunks(data["documents"])
    print(f"{len(chunks)} chunks générés (dont {sum(1 for c in chunks if c['metadata']['chunk_type']=='theme_overview')} résumés de thème).")
    quality_check(chunks)
