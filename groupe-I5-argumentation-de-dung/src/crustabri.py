"""
Wrapper Python pour crustabri via la C API IPAFAIR (libcrustabri_ipafair.dylib).

Utilisation
-----------
    from crustabri_wrapper import compute_some_extension
    import networkx as nx

    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 0)])
    ext = compute_some_extension(G, "ST")   # set vide si pas d'extension stable

API IPAFAIR C utilisée
----------------------
Les fonctions exposées par libcrustabri_ipafair.dylib suivent le standard IPAFAIR
(Incremental Argumentation Framework API for Reentrant solvers) :

    void* ipafair_init(const char* semantics)
        Crée et retourne un solver pour la sémantique donnée.
        Sémantiques reconnues : "GR", "PR", "ST" (et d'autres non utilisées ici).

    void ipafair_release(void* solver)
        Libère toutes les ressources du solver.

    void ipafair_add_argument(void* solver, int arg)
        Ajoute l'argument `arg` au framework. Les identifiants sont des entiers >= 1.

    void ipafair_add_attack(void* solver, int from, int to)
        Ajoute l'arête d'attaque from -> to.

    int ipafair_solve(void* solver)
        Lance le solveur. Retourne :
          10  (SAT)   — une extension a été trouvée
          20  (UNSAT) — aucune extension n'existe (possible pour ST)

    int ipafair_val_arg(void* solver, int arg)
        Après un appel réussi à ipafair_solve (retour == 10), indique si l'argument
        `arg` est dans l'extension calculée :
          1   — l'argument EST dans l'extension
         -1   — l'argument N'EST PAS dans l'extension

Notes importantes
-----------------
- Les identifiants IPAFAIR sont des entiers >= 1 (convention 1-indexée, comme IPASIR).
  Les nœuds NetworkX, qui peuvent être n'importe quel entier, sont remappés en 1..N
  en interne, puis retraduits dans l'espace d'origine avant d'être retournés.
- La lib est chargée une seule fois (singleton module-level) pour éviter les coûts
  de rechargement répétés si la fonction est appelée en boucle.
- La gestion des sémantiques "GR" (grounded) et "PR" (preferred) est identique côté
  appel : ipafair_solve retourne toujours 10 pour ces deux sémantiques car une
  extension existe toujours. "ST" peut légitimement retourner 20.
"""

import ctypes
import os
import pathlib
from typing import Literal

import networkx as nx

# ---------------------------------------------------------------------------
# Chargement de la bibliothèque (une seule fois)
# ---------------------------------------------------------------------------

def _load_lib() -> ctypes.CDLL:
    """Charge libcrustabri_ipafair.dylib depuis le même répertoire que ce script."""
    script_dir = pathlib.Path(__file__).parent.resolve()
    lib_path = script_dir / "bin" / "libcrustabri_ipafair.so" # / libcrustabri_ipafair.dylib

    if not lib_path.exists():
        raise FileNotFoundError(
            f"Impossible de trouver la bibliothèque : {lib_path}\n"
            "Placez libcrustabri_ipafair.dylib dans le même répertoire que ce script."
        )

    lib = ctypes.CDLL(str(lib_path))

    # --- Signatures des fonctions C ---

    # void* ipafair_init(const char* semantics)
    lib.ipafair_init.restype = ctypes.c_void_p
    lib.ipafair_init.argtypes = [ctypes.c_char_p]

    # void ipafair_release(void* solver)
    lib.ipafair_release.restype = None
    lib.ipafair_release.argtypes = [ctypes.c_void_p]

    # void ipafair_add_argument(void* solver, int arg)
    lib.ipafair_add_argument.restype = None
    lib.ipafair_add_argument.argtypes = [ctypes.c_void_p, ctypes.c_int]

    # void ipafair_add_attack(void* solver, int from, int to)
    lib.ipafair_add_attack.restype = None
    lib.ipafair_add_attack.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

    # int ipafair_solve(void* solver)
    lib.ipafair_solve.restype = ctypes.c_int
    lib.ipafair_solve.argtypes = [ctypes.c_void_p]

    # int ipafair_val_arg(void* solver, int arg)
    lib.ipafair_val_arg.restype = ctypes.c_int
    lib.ipafair_val_arg.argtypes = [ctypes.c_void_p, ctypes.c_int]

    return lib


# Chargement paresseux : la lib n'est chargée qu'au premier appel.
_LIB: ctypes.CDLL | None = None


def _get_lib() -> ctypes.CDLL:
    global _LIB
    if _LIB is None:
        _LIB = _load_lib()
    return _LIB


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

_VALID_SEMANTICS = {"GR", "PR", "ST"}
_SAT   = 10   # ipafair_solve : extension trouvée
_UNSAT = 20   # ipafair_solve : pas d'extension (possible pour ST)


def compute_some_extension(
    G: nx.DiGraph,
    semantics: Literal["GR", "PR", "ST"],
) -> set[int]:
    """
    Calcule une extension (tâche SE) d'un graphe d'argumentation via crustabri.

    Paramètres
    ----------
    G : nx.DiGraph
        Graphe d'argumentation. Les nœuds doivent être des entiers.
    semantics : "GR" | "PR" | "ST"
        Sémantique souhaitée :
          "GR"  — grounded (toujours unique, toujours une extension)
          "PR"  — preferred (toujours au moins une extension)
          "ST"  — stable (peut ne pas en avoir)

    Retour
    ------
    set[int]
        Ensemble des nœuds appartenant à l'extension trouvée.
        Ensemble vide si aucune extension n'existe (uniquement possible pour "ST").

    Exceptions
    ----------
    ValueError
        Si `semantics` n'est pas dans {"GR", "PR", "ST"}.
    TypeError
        Si les nœuds de G ne sont pas des entiers.
    RuntimeError
        Si le solver retourne un code inattendu.
    """
    if semantics not in _VALID_SEMANTICS:
        raise ValueError(
            f"Sémantique invalide : {semantics!r}. Valeurs attendues : {_VALID_SEMANTICS}"
        )

    nodes = list(G.nodes())
    if not all(isinstance(n, int) for n in nodes):
        raise TypeError("Tous les nœuds du digraphe doivent être des entiers.")

    if len(nodes) == 0:
        return set()

    lib = _get_lib()

    # --- Remapping 1-indexé -----------------------------------------------
    # IPAFAIR exige des identifiants >= 1.
    # node_to_ipafair[node] = id IPAFAIR (1..N)
    # ipafair_to_node[id]   = nœud NetworkX d'origine
    node_to_ipafair: dict[int, int] = {node: idx + 1 for idx, node in enumerate(nodes)}
    ipafair_to_node: dict[int, int] = {v: k for k, v in node_to_ipafair.items()}

    # --- Création du solver ------------------------------------------------
    sem_bytes = semantics.encode("ascii")
    solver = lib.ipafair_init(sem_bytes)
    if solver is None:
        raise RuntimeError(
            f"ipafair_init a retourné NULL pour la sémantique {semantics!r}."
        )

    try:
        # --- Ajout des arguments -------------------------------------------
        for node in nodes:
            lib.ipafair_add_argument(solver, node_to_ipafair[node])

        # --- Ajout des attaques --------------------------------------------
        for src, dst in G.edges():
            lib.ipafair_add_attack(
                solver,
                node_to_ipafair[src],
                node_to_ipafair[dst],
            )

        # --- Résolution ----------------------------------------------------
        result = lib.ipafair_solve(solver)

        if result == _UNSAT:
            # Aucune extension stable — retour d'un ensemble vide
            return set()

        if result != _SAT:
            raise RuntimeError(
                f"ipafair_solve a retourné le code inattendu {result} "
                f"(attendu {_SAT} ou {_UNSAT})."
            )

        # --- Lecture de l'extension ----------------------------------------
        extension: set[int] = set()
        for ipafair_id in range(1, len(nodes) + 1):
            val = lib.ipafair_val_arg(solver, ipafair_id)
            if val == 1:
                extension.add(ipafair_to_node[ipafair_id])

        return extension

    finally:
        # Libération systématique même en cas d'exception
        lib.ipafair_release(solver)


# ---------------------------------------------------------------------------
# Exemple d'utilisation (exécution directe)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Exemple classique : cycle à 3 arguments
    #   0 -> 1 -> 2 -> 0
    # Extensions stables : aucune (cycle impair)
    # Extension grounded : {} (vide)
    # Extension preferred : {0}, {1} ou {2}
    G = nx.DiGraph()
    G.add_nodes_from([0, 1, 2])
    G.add_edges_from([(0, 1), (1, 2), (2, 0)])

    print("Graphe :", list(G.nodes()), "->", list(G.edges()))

    for sem in ("GR", "PR", "ST"):
        try:
            ext = compute_some_extension(G, sem)
            print(f"  SE-{sem} : {ext}")
        except FileNotFoundError as e:
            print(f"  [ERREUR] {e}")
            break