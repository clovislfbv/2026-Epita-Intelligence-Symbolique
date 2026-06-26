"""
Recherche d'une extension complète via réduction SAT résolue par CP-SAT.

Définition : S ⊆ A est une extension complète de AF = (A, R) ssi :
  1. Admissible : S est conflict-free et défend tous ses membres
  2. Complétude : Tous les arguments défendus par S appartiennent à S
"""

import networkx as nx
from ortools.sat.python import cp_model

def complete_extension(af: nx.DiGraph) -> set:
    """
    Trouve et retourne une extension complète du graphe d'argumentation de Dung `af`.
    """
    model = cp_model.CpModel()
    arguments = list(af.nodes())

    in_vars = {a: model.new_bool_var(f"in_{a}") for a in arguments}
    defended_vars = {a: model.new_bool_var(f"def_{a}") for a in arguments}

    for a in arguments:
        attackers = list(af.predecessors(a))
        
        # Conflict-free
        for b in attackers:
            model.add(in_vars[a] + in_vars[b] <= 1)
            
        # Définition de defended_vars[a]
        if not attackers:
            model.add(defended_vars[a] == 1)
        else:
            defended_by_S_conditions = []
            for b in attackers:
                defenders_of_b = list(af.predecessors(b))
                b_is_attacked_by_S = model.new_bool_var(f"b_attacked_{a}_{b}")
                if defenders_of_b:
                    model.add(sum(in_vars[c] for c in defenders_of_b) >= 1).only_enforce_if(b_is_attacked_by_S)
                    model.add(sum(in_vars[c] for c in defenders_of_b) == 0).only_enforce_if(b_is_attacked_by_S.Not())
                else:
                    model.add(b_is_attacked_by_S == 0)
                defended_by_S_conditions.append(b_is_attacked_by_S)
            
            model.add_min_equality(defended_vars[a], defended_by_S_conditions)
            
        # Sémantique Complète: in_a <==> defended_vars[a]
        model.add(in_vars[a] == defended_vars[a])

    solver = cp_model.CpSolver()
    status = solver.solve(model)

    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {a for a in arguments if solver.value(in_vars[a]) == 1}

    return set()
