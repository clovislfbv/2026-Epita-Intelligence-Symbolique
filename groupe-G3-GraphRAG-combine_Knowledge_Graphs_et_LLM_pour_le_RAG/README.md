# EPITA 2026 — Intelligence Symbolique
> Groupe de Matteo Atkinson et Paul Witkowski

## G3 — GraphRAG — combine Knowledge Graphs et LLM pour le RAG

Le GraphRAG (Graph-based Retrieval-Augmented Generation) represente une evolution majeure des systemes RAG en integrant la structure relationnelle des graphes de connaissances avec les capacites de generation des grands modeles de langage. Contrairement au RAG vectoriel classique qui s'appuie uniquement sur la similarite cosinus entre embeddings, le GraphRAG exploite les relations structurelles entre entites pour enrichir le contexte de generation, permettant ainsi de repondre a des questions necessitant du raisonnement multi-sauts. Ce sujet propose d'implementer un pipeline complet : extraction d'entites et de relations a partir de documents, construction du graphe, community detection pour le partitionnement thematique, et requetage combine graphe + LLM. L'evaluation comparative avec un RAG vectoriel classique sur un jeu de donnees de reference (HotpotQA, MuSiQue) mettra en evidence les gains en precision et en coherence des reponses.

### Objectifs
- Implementer un pipeline d'extraction d'entites et de relations depuis des documents textuels vers un graphe RDF ou property graph
- Integrate la structure du graphe dans le processus de retrieval (traversals, community summaries, subgraph extraction)
- Comparer les performances de GraphRAG vs. RAG vectoriel sur un benchmark de QA multi-hop
- Evaluer l'impact du partitionnement en communautes (Leiden, Louvain) sur la qualite des reponses
- Analyser les compromis entre cout de construction du graphe, latence de requetage et qualite des reponses

### Notebooks CoursIA pertinents

| Notebook | Chemin | Pertinence |
|----------|--------|------------|
| SW-11 Knowledge Graphs | [SymbolicAI/SemanticWeb/SW-11-Knowledge-Graphs.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/SymbolicAI/SemanticWeb/SW-11-Knowledge-Graphs.ipynb) | Construction de KG |
| SW-12 GraphRAG | [SymbolicAI/SemanticWeb/SW-12-GraphRAG.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/SymbolicAI/SemanticWeb/SW-12-GraphRAG.ipynb) | Pipeline GraphRAG |
| SW-3 SPARQL Basics | [SymbolicAI/SemanticWeb/SW-3-SPARQL-Basics.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/SymbolicAI/SemanticWeb/SW-3-SPARQL-Basics.ipynb) | Requetage du graphe |
| Argument Analysis | [SymbolicAI/Argument_Analysis/](https://github.com/jsboige/CoursIA/tree/main/MyIA.AI.Notebooks/SymbolicAI/Argument_Analysis) | Extraction d'arguments |

### References externes
- Edge, D., et al. (2024). "From Local to Global: A Graph RAG Approach to Query-Focused Summarization." *Microsoft Research*. [arXiv](https://arxiv.org/abs/2404.16130)
- Wu, L., et al. (2025). "Neural-Symbolic Reasoning over Knowledge Graphs." *ACM Computing Surveys*. [ACM](https://doi.org/10.1145/3638529)
- Lewis, P., et al. (2020). "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." *NeurIPS*. [NeurIPS](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc2694567247b7f-Abstract.html)
- Hogan, A., et al. (2022). "Knowledge Graphs." *ACM Computing Surveys*, 54(4). [ACM](https://doi.org/10.1145/3447772)

---

### Livrables attendus

- **Code source** documente dans un sous-dossier dedie (`groupe-XX-nom-sujet/`)
- **Notebook Jupyter** explicatif avec analyse et visualisations **OU** **UI/demo fonctionnelle** (au choix — un notebook tres complet peut tenir lieu de demo, et inversement)
- **Slides de soutenance** (PDF ou lien)
- **Pull Request** soumise au plus tard **2 jours avant la soutenance**

---

## Structure du projet

```
groupe-G3-GraphRAG-combine_Knowledge_Graphs_et_LLM_pour_le_RAG/
├── app/                     # Serveur FastAPI + interface web
│   ├── main.py              # Endpoints REST et streaming SSE
│   ├── models.py            # Schemas Pydantic
│   └── static/              # Interface (index.html / style.css / app.js)
├── graphrag_core/           # Bibliotheque GraphRAG
│   ├── extractor.py         # Extraction triplets entite-relation-entite (LLM)
│   ├── graph.py             # Construction et requetage du KG (RDF + NetworkX)
│   ├── llm.py               # Client LLM unifie (OpenAI / Anthropic / Ollama)
│   ├── pipeline.py          # Pipeline QA — BFS multi-hop + LLM
│   └── retriever.py         # Retrieval hybride (BFS + embeddings)
├── notebooks/               # Notebooks Jupyter (benchmark, KG, GraphRAG, SPARQL)
├── tests/                   # Tests unitaires pytest
├── data/                    # Donnees auto-generees au runtime
│   ├── custom/              # Documents uploades via l'interface
│   └── hotpotqa/            # Echantillons HotpotQA (telecharges automatiquement)
├── docs/                    # Design docs et visualisations
├── .env.example             # Gabarit de configuration
├── pyproject.toml           # Dependances et config projet (uv)
└── requirements.txt         # Dependances pip
```

## Lancement

### Prerequis

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recommande) ou pip
- Une cle API : OpenAI, Anthropic, ou Ollama en local

### Installation

```bash
cd groupe-G3-GraphRAG-combine_Knowledge_Graphs_et_LLM_pour_le_RAG

# Avec uv (recommande)
uv sync

# Ou avec pip
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
```

Editer `.env` et renseigner au minimum :

```env
LLM_PROVIDER=openai          # openai | anthropic | ollama
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...        # ou ANTHROPIC_API_KEY / OLLAMA_BASE_URL
```

### Demarrage du serveur

```bash
# Avec uv
uv run uvicorn app.main:app --reload

# Ou directement (dans le venv active)
uvicorn app.main:app --reload
```

Interface disponible sur **http://localhost:8000**

### Notebooks

```bash
uv run jupyter notebook notebooks/
```

### Tests

```bash
uv run pytest
```

---

## Ressources communes a tous les sujets

### Solveurs et outils
- **Z3 SMT Solver** : solveur SMT de reference pour verification formelle et raisonnement symbolique. [Documentation](https://z3prover.github.io/api/html/namespacez3py.html), [Tutoriel Python](https://ericpony.github.io/z3py-tutorial/guide-examples.htm)
- **Google OR-Tools CP-SAT** : solveur CP pour problemes combinatoires. [Documentation](https://developers.google.com/optimization/cp/cp_solver)
- **CVC5 SMT Solver** : solveur SMT alternatif. [Documentation](https://cvc5.github.io/)
- **TweetyProject** : librairie Java pour logique formelle, argumentation et raisonnement probabiliste. [Documentation](https://tweetyproject.org/)

### Frameworks et plateformes
- **Semantic Kernel** : orchestration d'agents IA avec plugins. [GitHub](https://github.com/microsoft/semantic-kernel)
- **Fast Downward** : planificateur PDDL de reference. [Site](https://www.fast-downward.org/)
- **Solidity / Foundry** : developpement et test de smart contracts. [Documentation](https://docs.soliditylang.org/)
- **PySAT** : interface Python pour solveurs SAT. [Documentation](https://pysathq.github.io/)
- **QuantConnect Lean** : plateforme de backtest et trading algorithmique (partenariat educatif sponsorise par Jared Broad, CEO QC). [Site](https://www.quantconnect.com/), [Documentation](https://www.quantconnect.com/docs/)

### Notebooks du cours CoursIA
Les notebooks suivants sont disponibles dans le depot CoursIA ([jsboige/CoursIA](https://github.com/jsboige/CoursIA)) et constituent des prerequis ou des points de depart pour les projets :

#### Demonstration automatique et typage dependant (Lean 4)
- **SymbolicAI/Lean/** : 12 notebooks — Lean-1 (Setup), Lean-2 (Dependent Types), Lean-3 (Propositions & Proofs), Lean-4 (Quantifiers), Lean-5 (Tactics), Lean-6 (Mathlib), Lean-7 (LLM Integration), Lean-8 (Agentic Proving), Lean-9 (Semantic Kernel Multi-Agents), Lean-10 (LeanDojo), Lean-11 (Neural Theorem Proving)

#### Logique formelle, SAT/SMT et solveurs
- **SymbolicAI/Linq2Z3.ipynb** : Z3 SMT Solver en C#
- **SymbolicAI/OR-tools-Stiegler.ipynb** : OR-Tools CP en C#
- **Sudoku/** : 18 notebooks couvrant Sudoku avec multiples solveurs (backtracking, DLX, GA, SA, PSO, Norvig, OR-Tools, Choco, Z3, BDD, neural, LLM)

#### TweetyProject — Logique et Argumentation
- **SymbolicAI/Tweety/** : 11 notebooks — Tweety-1 (Setup), Tweety-2 (Basic Logics), Tweety-3 (Advanced Logics), Tweety-4 (Belief Revision/AGM), Tweety-5 (Abstract Argumentation/Dung), Tweety-6 (Structured Argumentation/ASPIC+), Tweety-7a (Extended Frameworks), Tweety-7b (Ranking & Probabilistic), Tweety-8 (Agent Dialogues), Tweety-9 (Preferences)

#### Web Semantique et Graphes de Connaissances
- **SymbolicAI/SemanticWeb/** : 13 notebooks — SW-1 (Setup C#/Python), SW-2 (RDF), SW-3 (Graph Operations), SW-4 (SPARQL), SW-5 (Linked Data), SW-6 (RDFS), SW-7 (OWL), SW-8 (SHACL), SW-9 (JSON-LD), SW-10 (RDF*), SW-11 (Knowledge Graphs), SW-12 (GraphRAG), SW-13 (Reasoners)

#### Smart Contracts et Blockchain
- **SymbolicAI/SmartContracts/** : 27 notebooks (SC-0 a SC-26) — cypherpunk, Solidity, Foundry, ERC-20/721, DeFi, DAO Governance, Account Abstraction, LLM-assisted contracts, fuzz testing (SC-13), formal verification (SC-14), ZKP (SC-15), homomorphic encryption (SC-16), voting, Vyper, Bitcoin Script, Move/Sui, Solana/Anchor, cross-chain, deployment

#### Analyse d'Argumentation (Agentic)
- **SymbolicAI/Argument_Analysis/** : 7 notebooks — Agentic-0 (Init), Agentic-1 (Informal Argument Agent), Agentic-2 (Planning-Based Agent), Agentic-3 (Orchestration multi-agent)

#### Planification
- **SymbolicAI/Planners/** : 12 notebooks — Planners-1 (Intro), Planners-2 (PDDL), Planners-3 (State Space), Planners-4 (Fast Downward), Planners-5 (Heuristics), Planners-6 (Domains), Planners-7 (OR-Tools), Planners-8 (Temporal), Planners-9 (HTN), Planners-10 (LLM Planning), Planners-11 (Unified Planning), Planners-12 (LOOP)

#### Theorie des Jeux et Choix Social
- **GameTheory/** : 27 notebooks — forme normale, equilibres de Nash, zero-sum/minimax, evolution & trust, forme extensive, jeux combinatoires, induction, jeux bayesiens, reputation, information imparfaite/CFR, jeux cooperatifs/Shapley, mechanism design, choix social (Arrow SAT/Z3), multi-agent RL

#### Recherche et Metaheuristiques
- **Search/Part1-Foundations/** : 11 notebooks — StateSpace, uninformed, A*/heuristiques, local search, GA, adversarial/minimax, MCTS, Dancing Links, PL, automates symboliques, metaheuristiques

#### Programmation par Contraintes
- **Search/Part2-CSP/** : 9 notebooks — CSP-1 (Fondamentaux), CSP-2 (Consistency), CSP-3 (Advanced), CSP-4 (Scheduling), CSP-5 (Optimization), CSP-6 (Hybridation CP+SAT, LLM+CSP), CSP-7 (Soft Constraints), CSP-8 (Temporal CSP), CSP-9 (Distributed CSP)
- **Search/Applications/CSP/** : 11 notebooks — N-Queens, Graph Coloring, Nurse Scheduling, Job-Shop, Timetabling, Minesweeper, Wordle, MiniZinc, Picross, Sports Scheduling, Crossword
- **Search/Applications/Hybrid/** : 7 notebooks — Edge Detection, Portfolio Optimization, Connect Four, TSP Metaheuristics, VRP Logistics

#### Raisonnement Probabiliste et Decision

- **Research/** : 20 notebooks — Infer.NET (programmation probabiliste), melanges gaussiens, graphes de facteurs, reseaux bayesiens, modeles de Markov caches, LDA, crowdsourcing, recommandation, reseaux de decision, MDP/bandits/POMDP, TrueSkill, IRT

#### Reinforcement Learning

- **RL/** : 6 notebooks — MDP, Q-learning, DQN, policy gradient, multi-agent RL (NFSP, PSRO), Stable Baselines3, Gym wrappers, HER

#### Trading Algorithmique (QuantConnect)

- **QuantConnect/Python/** : 40+ notebooks — QC-Py-01 a QC-Py-34 couvrant la plateforme, backtesting, indicateurs techniques, modeles alpha, ML (classification, regression, LSTM, Transformer, RL DQN/PPO/SAC), detection de regimes, LLM trading signals, et paper trading Binance/IBKR

