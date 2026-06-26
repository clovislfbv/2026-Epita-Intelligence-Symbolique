"""
Recherche d'une extension stable dans un graphe d'argumentation de Dung
via réduction SAT résolue par CP-SAT (OR-Tools).

Définition : S ⊆ A est une extension stable de AF = (A, R) ssi :
  1. Conflict-free  : ∀ (a, b) ∈ R,  ¬(in(a) ∧ in(b))
  2. Range complet  : ∀ b ∉ S, ∃ a ∈ S t.q. (a, b) ∈ R
     (tout argument hors de S est attaqué par S)

Encodage SAT :
  - Variable booléenne in_a ∈ {0, 1} pour chaque argument a.
  - Conflict-free  : ∀ (a, b) ∈ R  →  in_a + in_b ≤ 1
  - Range complet  : ∀ b ∈ A, (¬in_b) → (∑_{a:(a,b)∈R} in_a ≥ 1)
    Reformulé en contrainte linéaire :
      in_b + ∑_{a:(a,b)∈R} in_a ≥ 1   (si b n'est pas dans S, il faut un attaquant)
"""

import networkx as nx
from ortools.sat.python import cp_model


def stable_extension(af: nx.DiGraph) -> set :
    """
    Trouve et retourne une extension stable du graphe d'argumentation de Dung `af`.

    Paramètres
    ----------
    af : nx.DiGraph
        Graphe orienté dont les nœuds sont des strings représentant les arguments
        et les arêtes représentent la relation d'attaque (a → b signifie a attaque b).

    Retour
    ------
    set[str] | None
        Un set contenant les nœuds de la première extension stable trouvée,
        ou None si le graphe n'admet pas d'extension stable.
    """
    model = cp_model.CpModel()
    arguments = list(af.nodes())

    # --- Variables : in[a] = 1 ssi a appartient à l'extension stable ---
    in_vars = {a: model.new_bool_var(f"in_{a}") for a in arguments}

    for a, b in af.edges():
        # Contrainte 1 — Conflict-free : a et b ne peuvent pas être tous les deux dans S
        model.add(in_vars[a] + in_vars[b] <= 1)

    for b in arguments:
        attackers = list(af.predecessors(b))

        # Contrainte 2 — Range complet :
        #   in(b) = 0  →  ∑ in(attaquants de b) ≥ 1
        #   Équivalent à : in(b) + ∑ in(attaquants) ≥ 1
        if attackers:
            model.add(
                in_vars[b] + sum(in_vars[a] for a in attackers) >= 1
            )
        else:
            # b n'a aucun attaquant → b doit être dans S (sinon range non complet)
            model.add(in_vars[b] == 1)

    # --- Résolution ---
    solver = cp_model.CpSolver()
    status = solver.solve(model)

    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {a for a in arguments if solver.value(in_vars[a]) == 1}

    return set()  # INFEASIBLE ou UNKNOWN → pas d'extension stable