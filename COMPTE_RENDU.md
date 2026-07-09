# Compte rendu (1 page)

*A adapter avec vos propres mots avant la soutenance - ce qui suit reflète les
tests reellement effectues sur le pipeline. Completez avec les elements
propres a votre binome (répartition du travail, temps passe, etc.).*

## Difficultes rencontrees

- **Clé API mal chargee au depart** : le fichier `.env` n'avait pas ete créé
  correctement (`Copy-Item .env.example .env` avait échoue silencieusement
  sous PowerShell et créé un fichier au nom litteral `.env.example .env`).
  Symptome : toutes les erreurs de HyDE/decomposition/génération tombaient en
  repli silencieux ("Appel LLM indisponible"), ce qui a masque le problème un
  moment. Lecon : toujours vérifier `Test-Path .env` et le contenu avec
  `Get-Content .env` avant de blamer le code.

- **Clé API exposee par erreur** : une capture d'ecran partagee pendant le
  debug affichait la clé Groq en clair. Revoquee et regeneree immédiatement
  sur console.groq.com. Rappel : même sans commit Git, une clé visible dans
  un partage d'ecran ou un message doit être considérée comme compromise.

- **Retrieval incomplet sur les questions composees** : sur "Quels sont mes
  droits en cas de licenciement economique et combien de temps de preavis
  dois-je avoir ?", le premier retrieval ne remontait que les articles de
  preavis (L1234-1) et ratait ceux du licenciement economique (L1233-3),
  pourtant bien presents dans le corpus. Cause : la fusion des chunks des
  deux sous-questions (issues de la decomposition) etait tronquee au
  top-k GLOBAL, et la sous-question au meilleur score RRF "mangeait" tout le
  budget de chunks avant l'appel au LLM. Corrige en reservant un quota
  minimum de chunks PAR sous-question avant fusion (voir
  `retrieval.py::hybrid_search`). Effet de bord assume : la réponse finale
  cite maintenant 8-9 articles au lieu de 3-4 sur une question composee, dont
  certains hors-sujet (ex: conges payes remontent parfois sur une question de
  licenciement) que le LLM doit lui-même filtrer dans sa réponse - un
  compromis rappel/precision assume plutot que résolu.

- **Le LLM peut digresser sur des articles absents du contexte** : sur la
  même question, la réponse commencait par "Je ne trouve pas les
  informations relatives aux articles L3121-27 et L3121-28...", des numéros
  qui n'avaient pourtant aucun rapport avec la question. Hypothèse : ces
  numéros apparaissaient en référence croisee dans le texte brut d'un autre
  article du contexte, et le modèle a cru (a tort) que la question les
  concernait. Ce n'est pas une violation de la contrainte de citation (les
  "articles sources" affiches viennent toujours des metadonnees des chunks
  retrouves, jamais du texte libre du LLM), mais ca montre que le corps de la
  réponse peut evoquer un numéro non fiable sans le citer comme source - une
  nuance a garder en tete si on voulait durcir davantage la contrainte.

- **Corpus initial trop réduit (26 articles)** : les premiers tests
  manquaient d'articles sur le licenciement economique (L1233-x) et
  echouaient donc a repondre complètement a certaines questions, non par bug
  mais par absence de données. Etoffe a 40 articles (3 a 8 par thème).

- **Metrique de distance Chroma non spécifiée (bug critique sur le score de
  confiance)** : la calibration (`tests/calibrate_confidence.py`) a révèle
  un "mur" de scores exactement a 0.0000, y compris sur des questions
  clairement dans le corpus ("Qu'est-ce que le SMIC ?"). Cause : Chroma
  utilise par defaut la distance euclidienne au carre (L2), pas une
  distance cosinus, sauf si on le précise explicitement a la création de la
  collection (`metadata={"hnsw:space": "cosine"}`). Notre calcul
  `similarity = 1 - dist` supposait une distance cosinus - le désaccord de
  metrique ecrasait les scores reels (~0.5 de similarite cosinus, fréquent
  entre phrases juridiques en francais même sans rapport de fond) pres de 0.
  Corrige dans `indexing.py::get_chroma_collection`. Point d'attention :
  cette metadonnee n'est appliquee qu'a la CRÉATION de la collection, donc
  la base persistee existante a du être entièrement reconstruite (suppression
  de `data/chroma_db/` puis `python -m src.cli index`) - une simple mise a
  jour incrementale n'aurait pas suffi. Une vérification automatique au
  chargement alerte désormais si ce désaccord se reproduit.

- **Calibration du seuil de confiance : recouvrement réel sur les "pieges"
  juridiques proches** - une fois le bug de metrique corrige, la
  calibration sur 16 questions dans le corpus et 12 hors corpus (6
  evidentes + 6 "pieges" : droit fiscal, fonction publique, divorce,
  retraite complementaire, delits routiers) a donne :
  - score minimum observe dans le corpus : **0.4035**
  - score maximum observe sur du hors-sujet évident : **0.2800** (bonne
    separation, marge confortable)
  - score maximum observe sur les "pieges" : **0.4969** (recouvrement réel
    avec le corpus - "retraite complementaire Agirc-Arrco" et "fonction
    publique territoriale" obtiennent un score plus élevé que la question
    la plus faible du corpus, "conge de fractionnement")

  Nous en concluons qu'un seuil de similarite seul ne peut pas séparer
  parfaitement le droit du travail des domaines juridiques adjacents sur un
  corpus de cette taille (40 articles) avec ce modèle d'embedding. Choix
  assume : `HARD_REFUSAL_THRESHOLD = 0.30`, place sous le minimum du corpus
  (jamais de refus a tort d'une vraie question) mais au-dessus du hors-sujet
  évident. Conséquence acceptee : certains "pieges" passent le seuil dur et
  sont transmis au LLM avec un avertissement de confiance faible plutot que
  d'être refuses sans appel - le prompt de génération sert alors de seconde
  ligne de defense (et s'est montre fiable sur nos tests, ex: "règles de
  circulation routiere" correctement refusee par le LLM lui-même).

- **Tests finaux de validation des questions 4 et 5 (réponses conditionnelles
  et frontiere du conseil juridique)** :
  - *"A partir de combien de salaries faut-il un CSE ?"* -> réponse correcte
    et sourcee (L2311-2, seuil de 11 salaries), sans reserve superflue - ce
    qui est le comportement attendu ici car ce seuil est une règle d'ordre
    public non modulable par accord d'entreprise, contrairement au preavis
    teste par ailleurs. Bemol : la liste "Articles sources" contenait 3
    articles sans rapport (harcelement sexuel, rupture conventionnelle),
    signe que le bruit de retrieval touche aussi les questions SIMPLES, pas
    seulement les questions composees (voir question 1 du README).
  - *"Mon licenciement est-il abusif si mon employeur ne m'a donne aucun
    motif ?"* -> comportement globalement conforme a la règle 4 (aucun
    verdict rendu, rappel des obligations procedurales L1232-2/L1232-6,
    mention du recours L1235-3, renvoi vers un professionnel). Limite
    observee : le LLM a intègre l'article L2311-2 (seuil CSE) dans son
    raisonnement de façon disproportionnee, suggerant qu'une absence de
    consultation du CSE "pourrait être considérée comme un manquement" alors
    que ce n'est pertinent que pour les licenciements economiques collectifs,
    pas un licenciement individuel sans motif énoncé. Le modèle étaye un
    chunk récupère mais marginal plutot que de l'ignorer - illustration
    concrete de la tension rappel/bruit déjà identifiée, cette fois avec un
    risque (atténue par le renvoi final vers un professionnel) de
    sur-interpretation plutot que de simple verbosite.

## Axes d'amélioration retenus (voir aussi README, section dediee)

Par ordre de priorite :
1. Filtrage post-génération des numéros d'articles hors contexte (regex sur
   la réponse finale, comparée aux metadonnees des chunks retrouves) - repond
   directement aux deux limites de digression/sur-interpretation observees.
2. Extension du corpus (Option A ou B) pour réduire le bruit et le
   recouvrement avec les domaines juridiques adjacents.
3. Reduction du bruit du quota par sous-question (ne l'elargir que si la
   première passe ne couvre pas déjà tous les thèmes de la question).

## Decisions de conception

- **Chunking hybride** (article + resume de thème, voir README Q1) plutot
  que du chunking par section : priorite donnée a la precision de citation.
- **Recherche hybride BM25 + vectoriel avec fusion RRF** plutot qu'une
  ponderation manuelle des scores (echelles non comparables directement).
- **Avertissement juridique assemble par le code**, pas seulement demande au
  LLM dans le prompt : garantit sa presence a 100 % des réponses.
- **Deux seuils de confiance distincts** (avertissement souple vs refus dur
  sans appel LLM) plutot qu'un seuil unique, pour fermer la faille du refus
  qui dependait entièrement du prompt.
- **Quota de chunks par sous-question** plutot qu'un pool global tronque,
  suite au bug de retrieval decrit ci-dessus.

## Ce que nous ferions avec plus de temps

- Étendre le corpus via l'API Legifrance (Option A) pour couvrir davantage
  d'articles par thème et réduire le bruit dans les chunks retrouves sur les
  questions composees.
- Resserrer le prompt de génération pour eviter les digressions sur des
  numéros d'articles mentionnes en référence croisee mais hors-sujet.
- Calibrer `HARD_REFUSAL_THRESHOLD` sur un jeu de test plus large que les 5
  questions du jalon 3 (voir `tests/calibrate_confidence.py`), avec des
  questions ambigues en plus des cas clairement dans/hors corpus.
- Mesurer et documenter la latence réelle du pipeline complet (HyDE +
  decomposition + recherche hybride + génération peut représenter 3 a 4
  appels LLM par question) pour decider si un mode "rapide" est nécessaire
  en demonstration.
