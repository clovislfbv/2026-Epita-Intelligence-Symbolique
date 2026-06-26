# L1 : résolution de Sudoku par multiples solveurs

Implémentation et comparaison de **cinq paradigmes** de résolution de Sudoku
derrière une interface commune, avec un banc d'essai instrumenté (temps, nœuds
explorés, mémoire) et un générateur de rapport.

| Solveur (`--solver`) | Paradigme | Dépendance |
|----------------------|-----------|-----------|
| `backtracking` | Recherche arborescente, heuristique MRV + forward checking | pure Python |
| `dlx` | Dancing Links / Algorithme X (couverture exacte) | pure Python |
| `cp_sat` | Programmation par contraintes (OR-Tools CP-SAT, AllDifferent) | `ortools` |
| `sat` | Satisfiabilité booléenne, encodage 9·9·9 (PySAT/Glucose) | `python-sat` |
| `genetic` | Métaheuristique (algorithme génétique, perms de lignes) | pure Python |

## Installation

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Utilisation

```bash
# Résoudre une grille (chaîne de 81 caractères ou fichier)
sudoku-bench solve "53..7....6..195....98....6.8...6...34..8.3..17...2...6.6....28....419..5....8..79" --solver dlx

# Lancer le banc d'essai complet (timeout par exécution)
sudoku-bench benchmark --solvers all --buckets all --timeout 20 --out benchmarks/results/results.csv

# Générer le rapport comparatif (tableaux + graphiques + analyse théorique)
sudoku-bench report --in benchmarks/results/results.csv --out reports/report.md

# Générer des grilles (unicité certifiée par DLX ; 'multi' = non unique)
sudoku-bench generate --bucket hard --count 3 --seed 0
# ... et les ajouter directement à la batterie d'instances
sudoku-bench generate --bucket medium --count 2 --seed 0 --append data/instances.json
```

## Interface graphique (Streamlit)

```bash
pip install -e ".[ui]"
streamlit run ui/app.py
```

Deux onglets :
- **🧩 Playground** : choisir/saisir une grille (ou en **générer** une à la
  difficulté voulue), lancer un ou plusieurs solveurs, visualiser la solution
  (indices en noir, valeurs trouvées en bleu) et comparer les métriques (temps,
  nœuds, mémoire).
- **📊 Dashboard** : charger un CSV de benchmark (`benchmarks/results/results.csv`
  par défaut, ou téléversé) et explorer les taux de succès et les temps/nœuds par
  bucket via des graphiques interactifs.

## Architecture

```
src/sudoku/
  board.py          # modèle de grille (parse/format/validation)
  metrics.py        # SolveResult (temps, nœuds, mémoire)
  instrument.py     # mesure temps + pic mémoire (tracemalloc)
  solvers/          # un module par paradigme, interface Solver commune
  generator.py      # chargement des instances + génération (unicité certifiée par DLX)
                    #   exposée via `sudoku-bench generate` et l'UI
  benchmark.py      # exécution sous timeout (process isolé) -> CSV
  report.py         # agrégation pandas + graphiques matplotlib -> markdown
ui/app.py           # interface Streamlit (playground + dashboard)
data/instances.json # grilles de difficulté croissante (easy..very_hard, 17 indices, multi)
```

Chaque solveur dérive de `Solver` et renvoie un `SolveResult` uniforme, ce qui
permet au banc d'essai de rester agnostique et aux tests de vérifier que tous
les solveurs **s'accordent sur la solution**.

## Tests

```bash
pytest -q
```

## Évaluation

Le banc d'essai mesure, par grille et par solveur : temps de résolution, nombre
de nœuds explorés (ou conflits CDCL pour SAT/CP-SAT), et pic mémoire. Les
solveurs complets (backtracking, DLX, CP-SAT, SAT) trouvent toujours la
solution ; l'algorithme génétique, incomplet, réussit les grilles faciles mais
se dégrade sur les grilles difficiles, ce que le rapport met en évidence.

Voir [`reports/report.md`](reports/report.md) après exécution du benchmark.
