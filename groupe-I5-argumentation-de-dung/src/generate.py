import networkx as nx


def generate_af(
    n_arguments: int,
    n_themes: int,
    p_intra: float,
    p_inter: float,
    seed: int | None = None,
) -> tuple[nx.DiGraph, list[int]]:
    if n_arguments < 1:
        raise ValueError(f"n_arguments doit être >= 1, reçu {n_arguments}.")
    if not (1 <= n_themes <= n_arguments):
        raise ValueError(
            f"n_themes doit être dans [1, n_arguments={n_arguments}], reçu {n_themes}."
        )
    for name, p in [("p_intra", p_intra), ("p_inter", p_inter)]:
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"{name} doit être dans [0, 1], reçu {p}.")

    # Répartition équilibrée des arguments dans les thèmes
    base, remainder = divmod(n_arguments, n_themes)
    sizes = [base + (1 if i < remainder else 0) for i in range(n_themes)]

    # Matrice de probabilités n_themes × n_themes
    p_matrix = [
        [p_intra if r == s else p_inter for s in range(n_themes)]
        for r in range(n_themes)
    ]

    G = nx.stochastic_block_model(
        sizes, p_matrix, seed=seed, directed=True, selfloops=False
    )

    return G