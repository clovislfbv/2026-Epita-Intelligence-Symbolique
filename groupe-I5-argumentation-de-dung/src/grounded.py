import networkx as nx
from collections import deque


import networkx as nx
from collections import deque


def grounded_extension(af: nx.DiGraph) -> list:
    """
    Calcule la grounded extension d'un framework d'argumentation (AF)
    en complexité O(n + m), via propagation par compteurs (proche de
    l'algorithme de Kahn pour le tri topologique).

    Principe :
    - Chaque argument a un compteur d'attaquants "actifs" (ni accepté,
      ni rejeté) initialisé à son degré entrant.
    - Un argument dont le compteur tombe à 0 est immédiatement accepté
      (il est "défendu" : plus aucun attaquant actif ne le menace).
    - Quand un argument est accepté, tous ceux qu'il attaque sont
      rejetés ; et pour chaque argument rejeté, on décrémente le
      compteur des arguments qu'IL attaquait (puisqu'un attaquant
      neutralisé ne compte plus).
    - Chaque nœud et chaque arc n'est traité qu'un nombre constant de
      fois -> O(n + m).

    Args:
        af: graphe orienté représentant l'AF (nœuds = arguments,
            arcs (a, b) = "a attaque b")

    Returns:
        list: liste des arguments appartenant à la grounded extension.
    """
    status: dict = {n: "undecided" for n in af.nodes()}
    active_attackers_count = {n: af.in_degree(n) for n in af.nodes()}

    queue = deque(n for n, c in active_attackers_count.items() if c == 0)
    in_extension: set = set()

    while queue:
        arg = queue.popleft()
        if status[arg] != "undecided":
            continue

        status[arg] = "in"
        in_extension.add(arg)

        for attacked in af.successors(arg):
            if status[attacked] == "undecided":
                status[attacked] = "out"
                for grand_target in af.successors(attacked):
                    if status[grand_target] == "undecided":
                        active_attackers_count[grand_target] -= 1
                        if active_attackers_count[grand_target] == 0:
                            queue.append(grand_target)

    return in_extension