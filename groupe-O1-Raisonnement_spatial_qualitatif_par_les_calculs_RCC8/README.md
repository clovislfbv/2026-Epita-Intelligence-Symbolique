# Sujet O1 - Raisonnement spatial qualitatif par les calculs RCC8

## Rappel des consignes

Implémenter le calcul relationnel spatial RCC8 (*Region Connection Calculus*),
qui définit huit relations de base entre régions spatiales :

- `DC` : disconnected ;
- `EC` : externally connected ;
- `PO` : partially overlapping ;
- `EQ` : equal ;
- `TPP` : tangential proper part ;
- `NTPP` : non-tangential proper part ;
- `TPPI` : inverse de `TPP` ;
- `NTPPI` : inverse de `NTPP`.

Le raisonneur par contraintes doit propager les relations connues, inférer des
relations implicites et détecter les incohérences dans des configurations
spatiales. L'application porte sur la vérification de descriptions spatiales ou
sur la planification robotique.

## Objectifs

- Implémenter les huit relations RCC8.
- Implémenter la table de composition RCC8.
- Construire un raisonneur par contraintes.
- Propager les relations spatiales implicites.
- Détecter les incohérences dans un réseau de contraintes.
- Appliquer le raisonneur à des exemples concrets.
- Évaluer la scalabilité sur des réseaux de taille croissante.

## Définition de RCC8

RCC8 est un modèle de raisonnement spatial qualitatif. Il permet de décrire la
relation topologique entre deux régions sans utiliser de coordonnées
géométriques précises.

Les régions sont considérées comme des objets abstraits. Le système ne calcule
pas leurs formes exactes : il raisonne uniquement sur les relations possibles
entre elles.

| Relation | Signification |
|----------|---------------|
| `DC` | Les deux régions sont séparées. |
| `EC` | Les régions se touchent par leur frontière. |
| `PO` | Les régions se chevauchent partiellement. |
| `EQ` | Les régions sont identiques. |
| `TPP` | La première région est incluse dans la seconde et touche son bord. |
| `NTPP` | La première région est strictement à l'intérieur de la seconde. |
| `TPPI` | Inverse de `TPP`. |
| `NTPPI` | Inverse de `NTPP`. |

## Implémentation

Le projet implémente un raisonneur spatial basé sur la composition des
relations RCC8. Le solveur maintient un réseau de contraintes binaires :
pour chaque paire de régions `(A, B)`, il stocke l'ensemble des relations RCC8
encore possibles entre `A` et `B`.

La propagation utilise une approche inspirée de PC-2. Pour chaque triplet de
régions `(i, j, k)`, le solveur raffine la contrainte directe entre `i` et `k`
à partir de la composition des contraintes entre `i`, `j` et `k` :

```text
R(i, k) <- R(i, k) ∩ (R(i, j) o R(j, k))
```

Si un ensemble de relations devient vide, le réseau est incohérent. Sinon, la
propagation continue jusqu'à atteindre un point fixe.

Le solveur maintient aussi automatiquement les relations inverses :

```text
si A --TPP-- B, alors B --TPPI-- A
```

Cette propagation permet de détecter des contradictions qui ne sont pas visibles
directement sur une seule paire de régions, mais qui apparaissent après
composition de plusieurs contraintes.

## Cohérence par chemins

Le solveur calcule une fermeture par cohérence de chemins
(*path consistency*). Cela signifie que les contraintes directes entre deux
régions restent compatibles avec les contraintes qui passent par une troisième
région.

Cette propriété est utile pour détecter de nombreuses incohérences
structurelles, mais elle ne constitue pas une preuve complète de satisfiabilité
globale pour tous les réseaux RCC8 possibles.

## Complexité

Une passe complète du solveur parcourt les triplets de régions. Pour `n`
régions, cela représente un coût en `O(n^3)` par passe.

Comme plusieurs passes peuvent être nécessaires avant convergence, la complexité
temporelle de cette implémentation est :

```text
O(passes x n^3)
```

La mémoire est principalement utilisée par la matrice des contraintes entre
paires de régions :

```text
O(n^2)
```

## Structure du projet

```text
.
├── README.md
├── pyproject.toml
├── requirements.txt
├── rcc8/
│   ├── __init__.py
│   ├── relations.py
│   ├── composition_table.py
│   ├── rcc8solver.py
│   └── test.py
└── notebook/
    ├── 01_relations.ipynb
    ├── 02_composition_table.ipynb
    ├── 03_constraint_propagation.ipynb
    ├── 04_inconsistency_detection.ipynb
    ├── 05_robot_planning.ipynb
    └── 06_scalability.ipynb
```

## Notebooks

### 1. `01_relations.ipynb`

Présentation des huit relations RCC8, de leur signification géométrique et
d'exemples visuels simples.

### 2. `02_composition_table.ipynb`

Présentation de la table de composition RCC8 et de la règle :

```text
R(A, B) o R(B, C)
```

### 3. `03_constraint_propagation.ipynb`

Propagation étape par étape, réduction des domaines et obtention d'un réseau
stable par cohérence de chemins.

### 4. `04_inconsistency_detection.ipynb`

Détection de contradictions directes et indirectes dans des configurations
spatiales.

### 5. `05_robot_planning.ipynb`

Application à un exemple de planification robotique avec zones interdites,
obstacles, objectif et contraintes spatiales.

### 6. `06_scalability.ipynb`

Benchmark du raisonneur sur des réseaux de taille croissante. Le notebook
mesure notamment le temps de propagation, la mémoire estimée et le nombre de
contraintes manipulées.

## Exemple de propagation

Si l'on impose :

```text
A --TPP-- B
B --TPP-- C
```

alors le solveur déduit que `A` est une partie propre de `C` :

```text
A --{TPP, NTPP}-- C
```

Si une contrainte incompatible est ajoutée, par exemple :

```text
A --DC-- C
```

le réseau devient incohérent et le solveur détecte la contradiction.

## Limites

- Le raisonnement est qualitatif : aucune géométrie numérique exacte n'est
  calculée.
- La cohérence par chemins ne garantit pas la satisfiabilité globale de tous les
  réseaux RCC8.
- Le coût augmente rapidement avec le nombre de régions, car la propagation
  parcourt des triplets.


## Lien des slides

lien : https://docs.google.com/presentation/d/1YhMuNr2YvPKRfWq70yBaB17QkWQ45P8iWE7z0v-mdvA/edit?usp=sharing