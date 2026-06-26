from rcc8.composition_table import COMPOSE
from rcc8.relations import ALL_RELATIONS, inverse_relation, inverse_relations, normalize_relations


class RCC8Solver:

    def __init__(self, vars, R, inverse_relation_func=inverse_relation):
        self.vars = list(vars)
        self.R = {}
        self.COMPOSE = COMPOSE
        self.inverse_relation = inverse_relation_func

        for i in self.vars:
            for j in self.vars:
                if i == j:
                    continue
                self.R[(i, j)] = normalize_relations(R.get((i, j), set(ALL_RELATIONS)))

    def _normalize_network(self):
        for key, relations in self.R.items():
            self.R[key] = normalize_relations(relations)

    def _enforce_converse_pair(self, i, j):
        """
        Maintient R(j,i) = inverse(R(i,j)) par intersection.
        """
        old_ij = self.R[(i, j)]
        old_ji = self.R[(j, i)]

        new_ij = old_ij & inverse_relations(old_ji)
        if not new_ij:
            raise ValueError(f"Inconsistency detected between {i} and {j}")

        new_ji = old_ji & inverse_relations(new_ij)
        if not new_ji:
            raise ValueError(f"Inconsistency detected between {j} and {i}")

        self.R[(i, j)] = new_ij
        self.R[(j, i)] = new_ji

        return new_ij != old_ij or new_ji != old_ji

    def _enforce_all_converses(self):
        changed = False

        for i in self.vars:
            for j in self.vars:
                if i == j:
                    continue
                if self._enforce_converse_pair(i, j):
                    changed = True

        return changed

    def add_constraint(self, i, j, relations):
        """
        Ajoute une contrainte en raffinant R(i,j) et son inverse R(j,i).
        """
        if i not in self.vars or j not in self.vars:
            raise ValueError(f"Unknown variable in constraint: {i!r}, {j!r}")
        if i == j:
            raise ValueError("A constraint must relate two distinct variables")

        new_relations = normalize_relations(relations)
        self.R[(i, j)] = self.R[(i, j)] & new_relations

        if not self.R[(i, j)]:
            raise ValueError(f"Inconsistency detected between {i} and {j}")

        self._enforce_converse_pair(i, j)

    # -----------------------------
    # REVISE (PC-2 core)
    # -----------------------------
    def revise(self, i, j, k):
        """
        R(i,k) ← R(i,k) ∩ (R(i,j) ∘ R(j,k))
        """

        old = self.R[(i, k)]
        possible = set()

        for rij in self.R[(i, j)]:
            for rjk in self.R[(j, k)]:
                try:
                    possible |= self.COMPOSE[rij][rjk]
                except KeyError as exc:
                    raise ValueError(f"Unknown RCC8 composition: {rij} o {rjk}") from exc

        new = old & possible

        # incohérence globale
        if not new:
            raise ValueError(f"Inconsistency detected between {i} and {k}")

        if new != old:
            self.R[(i, k)] = new

            # maintenir cohérence inverse
            self._enforce_converse_pair(i, k)

            return True

        return False

    # -----------------------------
    # PC-2 (path consistency global)
    # -----------------------------
    def pc2(self):
        """
        PC-2 classique :
        boucle jusqu'à point fixe sur tous les triplets
        """

        self._normalize_network()
        self._enforce_all_converses()
        changed = True

        while changed:
            changed = False

            for i in self.vars:
                for j in self.vars:
                    if i == j:
                        continue

                    for k in self.vars:
                        if k in (i, j):
                            continue

                        # propagation i -> k via j
                        if self.revise(i, j, k):
                            changed = True

        return self.R