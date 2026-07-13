# N5 — Planification Oncologique Symbolique

> **Sujet** : Construire un système d'aide a la decision pour la planification
> de traitements oncologiques combinant trois couches symboliques : une
> ontologie OWL des protocoles de chimiotherapie (raisonnée par HermiT), un
> modèle de contraintes Z3/SMT encodant les règles cliniques, et un modèle
> probabiliste PyMC estimant les paramètres patient-spécifiques.

## Structure du projet

```
.
├── src/
│   ├── __init__.py          # Exports publics du package
│   ├── ontology_owl.py      # Ontologie OWL 2 DL (owlready2 + raisonneur HermiT)
│   ├── smt_planning.py      # Contraintes Z3/SMT pour la planification
│   ├── proba_toxicity.py    # Inférence probabiliste PyMC (MCMC/NUTS)
│   ├── pipeline.py          # Intégration des 3 couches (PipelineOncoPlan)
│   └── validation.py        # Validation sur les 8 patients du dataset
├── notebooks/
│   ├── N5_oncology_planning.ipynb   # Notebook d'analyse et de demonstration
│   └── figures/                      # Figures generées a l'éxécution
├── data/
│   └── patients_oncology.csv         # Dataset CoursIA (CaseStudies/Oncology-Planning/)
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

Nécéssite également un JRE (Java) installé pour le raisonneur HermiT
(vérifier avec `which java`).

## Utilisation

Le notebook est le point d'entrée principal. Depuis le dossier `notebooks/` :

```bash
jupyter lab N5_oncology_planning.ipynb
```

La librairie `src/` peut aussi etre utilisée directement :

```python
import sys
sys.path.insert(0, '..')   # depuis notebooks/, remonte a la racine

from src import (
    build_ontology, populate_ontology, run_reasoner, verifier_prescription,
    planifier_chimio,
    inferer_profil, simuler_risque_futur, recommander_dose,
    PipelineOncoPlan, run_validation,
)

pipeline = PipelineOncoPlan()
resultat = pipeline.recommander(
    protocole_nom="FOLFOX",
    patient_pathologies=[],
    doses_historique=[85.0, 85.0, 0.0, 0.0, 70.0, 70.0],
    observations_gb=[7200.0, 6800.0, 3900.0, 5200.0, 5500.0, 5100.0],
    dose_prevue=85.0,
)
print(resultat["statut_final"])
```

## Architecture

### Séparation des responsabilités

| Composant | Role |
|-----------|------|
| `src/ontology_owl.py` | Ontologie OWL (agents, protocoles, pathologies, contre-indications), raisonnement HermiT, verification SPARQL |
| `src/smt_planning.py` | Contraintes Z3/SMT (espacement cycles, capacite, dose cumulee), diagnostic `unsat_core` |
| `src/proba_toxicity.py` | Inference MCMC/NUTS du profil de toxicite latent, simulation de risque, recommandation de dose |
| `src/pipeline.py` | Orchestration des 3 couches (`PipelineOncoPlan.recommander()`) |
| `src/validation.py` | Validation sur les 8 patients reels du dataset |
| `notebooks/N5_oncology_planning.ipynb` | Analyse, demonstrations, figures |

### Pourquoi ces outils plutôt que le squelette CoursIA (RDFLib + OR-Tools + Pyro) ?

Le sujet N5 demande explicitement OWL/HermiT, Z3/SMT et PyMC/MCMC — des
outils plus riches theoriquement que le squelette CoursIA :

- **OWL/HermiT** vs RDFLib : raisonnement de description logique reel
  (classification automatique via classes inferees, detection
  d'incoherence logique), pas seulement un graphe de triplets interroge
  par recherche directe.
- **Z3/SMT** vs OR-Tools/CP-SAT : diagnostic d'infaisabilite via
  `unsat_core`, qui explique *pourquoi* aucun calendrier valide n'existe.
- **PyMC/MCMC** vs Pyro/SVI : inference bayesienne complete (echantillon
  du posterior, diagnostics R-hat), permettant une decision qui integre
  toute l'incertitude residuelle plutot qu'un simple point estimate.

### Trois corrections empiriques (documentées dans le notebook, Section IV)

En réimplementant la dynamique de toxicité du squelette CoursIA à l'échelle
réelle du dataset, trois problèmes ont été identifiés et corrigés :

1. Délai d'effet PK/PD absent (le nadir hematologique survient ~1 pas de
   temps après l'administration, pas au même pas).
2. Doses brutes non comparables entre protocoles (normalisation par dose
   de référence nécessaire).
3. Prior Dirichlet trop contraignant (masquait le signal des données
   réelles pour les patients a dose nominale élevée mais bien tolérée).

### Robustesse et généralisation (au-dela du dataset)

- **20 agents / 9 familles pharmacologiques** (extension au-delà des 15
  nécessaires aux 8 protocoles du dataset), incluant des agents au profil
  contrastant volontairement (ex: Trastuzumab cardiotoxique vs Rituximab
  non-cardiotoxique, tous deux anticorps monoclonaux).
- **Généralisation démontrée** : l'ontologie détecte correctement une
  contre-indication sur un protocole construit a la voleé (TCH) jamais vu
  pendant sa construction.
- **Validation explicite des entrées** dans les trois couches (protocole/
  pathologie inconnus, dose negative, nombre de cycles nul) : `ValueError`
  avec message actionnable plutot que `KeyError`/`AssertionError` bruts.
  Le pipeline d'intégration capture ces erreurs avec leur contexte
  d'origine (statut `ERREUR_ENTREE`).
- **Analyse de sensibilité** sur le ratio ANC/WBC (le seuil de neutropenie
  sévère repose sur l'ANC, mais le dataset ne fournit que le WBC total) :
  quantifie explicitement que l'incertitude sur ce paramètre pèse le plus
  précisément pour les patients à risque élevé (cf. notebook, Section IV).

## Références

- Sujet CoursIA : `CaseStudies/Oncology-Planning/` (EPITA, Intelligence Symbolique)
- owlready2 / HermiT : https://owlready2.readthedocs.io/
- Z3 SMT Solver : https://z3prover.github.io/api/html/namespacez3py.html
- PyMC : https://www.pymc.io/
