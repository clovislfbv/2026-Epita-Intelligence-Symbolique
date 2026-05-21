 # VM Allocation Optimization

## Instructions

Le VM Scheduling Problem consiste a allouer des machines virtuelles (VMs) avec des caracteristiques heterogenes (CPU, RAM, stockage, bande passante) sur des serveurs physiques, sous des contraintes de capacite, d'affinite (certaines VMs doivent etre co-localisees ou separees pour des raisons de securite/performance), et de resilience (anti-affinite pour la tolerance aux pannes). C'est un probleme de Bin Packing multi-dimensionnel avec des contraintes d'affinite, directement modelisable en CP-SAT.

### Objectifs
- Modeliser le VM Scheduling comme un Bin Packing multi-dimensionnel avec contraintes d'affinite en CP-SAT
- Implementer les contraintes de capacite (CPU, RAM, stockage), d'affinite/anti-affinite, et de resilience
- Ajouter la consolidation dynamique (migration de VMs) et la minimisation de la fragmentation
- Evaluer sur des instances reelles (Google Cluster Trace) et des benchmarks synthetiques
- Comparer avec le First Fit Decreasing (FFD) et un modele PLNE sur les memes instances

### Notebooks CoursIA pertinents

| Notebook | Chemin | Pertinence |
|----------|--------|------------|
| CSP-5 Optimization | [Search/Part2-CSP/CSP-5-Optimization.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/Search/Part2-CSP/CSP-5-Optimization.ipynb) | Bin Packing, Knapsack |
| CSP-1 Fondamentaux | [Search/Part2-CSP/CSP-1-Fundamentals.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/Search/Part2-CSP/CSP-1-Fundamentals.ipynb) | Modelisation CSP |
| Search-9 Programmation lineaire | [Search/Part1-Foundations/Search-9-LinearProgramming.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/Search/Part1-Foundations/Search-9-LinearProgramming.ipynb) | PLNE, relaxation |
| CSP-7 Soft Constraints | [Search/Part2-CSP/CSP-7-Soft.ipynb](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/Search/Part2-CSP/CSP-7-Soft.ipynb) | Preferences, penalites |

### References externes
- Mann, Z.A. (2015). "Allocation of Virtual Machines in Cloud Data Centers - A Survey." *European Journal of Operational Research*, 246(3), 779-798. [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0377221715003633)
- Google Cluster Trace. [GitHub](https://github.com/google/cluster-data)
- Beloglazov, A., & Buyya, R. (2012). "Optimal Online Deterministic Algorithms and Adaptive Heuristics for Energy and Performance Efficient Dynamic Consolidation." *Future Generation Computer Systems*, 28(5), 753-768. [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0167739X11000689)
- Salimian, A., et al. (2017). "A Survey of Energy-Aware Scheduling in Cloud Computing." *The Journal of Supercomputing*. [Springer](https://link.springer.com/article/10.1007/s11227-017-2190-3)

### Difficulte : 3/5

## Défrichage

- Une VM est définie par 4 grandeurs: CPU, RAM, Stockage, Bande passante
- Un serveur est défini par 4 grandeurs: CPU, RAM, Stockage, Bande passante
- La somme des grandeurs des VMs d'un serveur ne doit pas dépasser les grandeurs du dit serveur
- Certaines VMs doivent être sur le même serveur
- Certaines VMs ne doivent pas être sur le même serveur
- On doit favoriser l'aggrégation des espaces libres restants pour économiser les ressources
- Dans le cadre d'une situation initiale de VM active, trouver la solution optimale pour mettre les VMs en format optimal sans downtime

Pour l'utilisation de ortools pour le CP-SAT: [CSP-3 Advanced](https://github.com/jsboige/CoursIA/blob/main/MyIA.AI.Notebooks/Search/Part2-CSP/CSP-3-Advanced.ipynb)

## Installation

Pour installer la bibliothèque, un appel à pip à la racine suffit
```console
pip install .
```

## Usage type

Cette bibliothèque permet une abstraction de la gestion de l'allocation de
VM sur des serveurs. Pour l'utiliser, il faut utiliser les classes `VM`,
`Server` et `Context` pour monter une abstraction des infrasructures techniques
du Datacenter et des VMs qu'elle accueille. Le positionnement optimal des VMs
peut être calculée grâce à un `Solver`, les opérations de déplacement relevant
de l'architecture spécifique de l'utilisateur, celui-ci devra appliqué les
déplacements conseillés sur son architecture. Pour une utilisation en temps
réel, la manipulation en continu d'un `Context` créé, avec appel à un solver
lors d'ajouts ou mises à jour des VMs, est la méthode prévue (les suppressions
peuvent s'effectuer sans appel à un solver).

## Diaporama de présentation

Le lien pour le diaporama de présentation est disponible en consultation
[ici](https://epitafr-my.sharepoint.com/:p:/g/personal/brendan_martin_epita_fr/IQByf0xdDWQ4QJWC3TpNiXV2AU_Rgv12vXkdPk73j7No7os?e=ycYdHZ). Celui-ci est encore
en cours de construction et sera complété pour le jour de la présentation.

## Modélisation du problème

On va chercher ici à représenter ce problème par un problème de programmation
linéaire pour pouvoir le résoudre par CP-SAT et PLNE.

La première partie du problème, à savoir la recherche de la configuration
optimale, s'apparente à un Bin Packing Problem (BPP). La seconde reposera sur
l'ajout d'une notion de transition d'un état de départ vers cet état optimal.

Supposons `NB_SERVER` le nombre maximal de serveurs et `NB_VM` le nombre de VMs.

### Variables de décision

Pour chaque VM, on peut choisir à quel serveur on l'associe. On a donc comme
variables de décision les valeurs $x_{i,j}$ avec $i \in [[1;\text{NB\_VM}]]$ et
$j \in [[1;\text{NB\_SERVER}]]$ avec $x_{i,j} \in \{0;1\}$.

### Fonction objectif

On cherche à minimiser les coûts d'exploitation du centre de données, on veut
donc minimiser le nombre de serveur avec une VM active dessus pour pouvoir les
mettre dans un mode d'économie d'énergie. Autrement dit, on cherche:
$$min \; \sum_j \max_{i} x_{i,j}$$

Pour transformer ce problème en problème linéaire, on va ruser en introduisant
une variable intermédiaire $y_j \in \{0;1\}$ avec de nouvelles contraintes
telles que $\forall i, y_j \ge x_{i,j}$ (ce qui donne l'opération max). On
obtient alors:
$$min \; \sum_j y_j$$

### Contraintes d'unicité

On veut que les VMs soient présentes sur exactement un serveur. On peut traduire cette contrainte par:
$$\sum_j x_{i,j} = 1$$

### Contraintes de capacités

On veut que les VMs aient leurs ressources adéquates, donc on ne veut pas
surcharger un serveur et lui assigner plus de VMs que sa capacité ne permettent.
Pour ce faire, on définit les capacités `CPU`, `RAM`, `STOCKAGE` et `RESEAU`
pour les `VM` et les `SERVER`.
On veut pour chaque serveur $j$ que:
$$\sum_i \text{VM\_CPU}_i \; x_{i,j} \le \text{SERVER\_CPU}_j y_j$$

et de même pour les autres capacités.

### Contraintes d'affinité / anti-affinité

On veut que certaines VMs soient sur le même serveur ou, au contraire, sur des
serveurs différents. Autrement dit, avec deux vms $i$ et $k$, pour un serveur
$j$ fixé, on a la contrainte d'affinité:
$$x_{i,j} = x_{k,j}$$

et d'anti-affinité:
$$x_{i,j} + x_{k,j} \le 1$$
Pour qu'une seule des deux soit à 1 sans pour autant empêcher que les deux
soient à 0.

### Contraintes souples de consolidation dynamique

Jusqu'ici on est parti sur un contexte statique, les serveurs sont vides et on
souhaite remplir avec des VMs. On veut ici permettre la transition entre une
configuration ancienne vers une configuration nouvelle. La contrainte
principale que l'on va vouloir traiter ici et de pénaliser les hot swaps qui
sont couteux en ressources. Pour le représenter, on peut avoir les anciennes
assignations $x_{i,j}'$ et on applique une pénalité sur changements de valeur
en fonction d'un facteur.

Pour être précis, on est dans un contexte où, pour une VM donnée, on veut
l'ajouter ou optimiser son placement. Si $x_{i,j} = 1$ et $x_{i,j}' = 0$, on
vient de rajouter la VM sur ce serveur. Si au contraire $x_{i,j} = 0$ et
$x_{i,j}' = 1$, on a eu hot swap. Avec $\lambda_{hot}$ le facteur de
pénalisation, on peut ajouter le terme $\lambda_{hot} \sum_i \sum_j
x_{i,j}'(1 - x_{i,j})$ avec ici les $x_{i,j}'$ constants dans le problème d'optimisation. Ca fonctionne car $x_{i,j}'(1 - x_{i,j})$ vaut 1 seulement si
$x_{i,j} = 0$ et $x_{i,j}' = 1$.

On peut optimiser un peu la formule en posant
$\mathcal{A} = \{(i, j) | x_{i,j}' = 1\}$ l'ensemble des VMs qui
ne sont pas nouvelles. On peut réécrire
$$\begin{align}
\sum_i \sum_j x_{i,j}'(1 - x_{i,j}) &= \sum_i \sum_j x_{i,j}' - \sum_i \sum_j
x_{i,j}' x_{i,j} \\
&= \sum_{(i, j) \in \mathcal{A}} 1 - \sum_{(i, j) \in \mathcal{A}} x_{i,j} \\
&= |\mathcal{A}| - \sum_{(i, j) \in \mathcal{A}} x_{i,j}
\end{align}$$

Avec $|\mathcal{A}|$ une constante, on peut juste ne pas la considérer dans le
problème et garder le terme $- \lambda_{hot} \sum_{(i, j) \in \mathcal{A}}
x_{i,j}$. On peut l'interpréter comme une maximisation de conservation des
emplacements déjà utilisés, ce qui est ce que l'on veut.

 ### Contraintes souples de minimisation de la fragmentation

 Ici on va vouloir minimiser la fragmentation des serveurs allumés. Autrement
 dit, si la somme des besoins des VMs n'est pas exactement égale à la somme des
 capacités des serveurs et qu'il y a de la marge, on veut que cette marge soit
 concentrée le plus possible sur un serveur. On veut donc minimiser le nombre
 de serveur fragmentés, donc avec de la marge.

 Posons $f_j \in \{0;1\}$ pour si le serveur $j$ est fragmenté ou non. On
 rajoutera à la fonction objectif le terme $\lambda_{frag} \sum_j f_j$ pour
 favoriser la baisse de fragmentation. D'un point de vue contraintes, on sait
 déjà que $f_j \le y_j$ (un serveur vide n'est pas fragmenté). Un serveur n'est
 pas fragmenté si la somme des capacités de ses VMs est égale à sa capacité
 totale, sachant qu'elle doit rester inférieure de toute manière. On peut le
 reformuler en disant que la marge restante est 0 si $f_j = 0$. On peut donc
 établir la contrainte suivante:
 $$\text{SERVER\_CPU}_j y_j - \sum_i \text{VM\_CPU}_i \; x_{i,j} \le f_j \;
 \text{SERVER\_CPU}_j$$

 et de même pour les autres capacités. Ainsi, on a le terme de gauche toujours
 positif avec la contrainte de capacités, le terme de droite est soit la valeur
 maximale possible de la marge, soit 0. Avec la minimisation de la somme des
 $f_j$, le $f_j$ sera à 0 seulement si la marge l'est.

 Sachant que si $f_j = 1$, on a l'expression qui devient
 $$\text{SERVER\_CPU}_j y_j - \sum_i \text{VM\_CPU}_i \; x_{i,j} \le
 \text{SERVER\_CPU}_j$$
 Ce qui est trivialement vrai (un serveur aura toujours plus ou exactement sa
 capacité avec les contraintes de capacités), on peut contraindre uniquement le
 cas où $f_j = 0$, ce qui donne
$$\text{SERVER\_CPU}_j y_j - \sum_i \text{VM\_CPU}_i \; x_{i,j} \le 0 \\
\iff \text{SERVER\_CPU}_j y_j -  \le \sum_i \text{VM\_CPU}_i \; x_{i,j}$$