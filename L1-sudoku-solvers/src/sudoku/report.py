"""Aggregate benchmark CSV into a markdown report with plots."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .generator import BUCKET_ORDER

_THEORY = """\
## Analyse théorique (complexité & propagation)

| Paradigme | Espace de recherche | Mécanisme de propagation | Complexité (pire cas) |
|-----------|---------------------|--------------------------|-----------------------|
| Backtracking (MRV + forward checking) | arbre des affectations cellule→valeur | élimination de candidats chez les 20 pairs | O(9^k) sur k cases vides, fortement élagué |
| Dancing Links (Algorithme X) | couverture exacte, 729 lignes × 324 colonnes | cover/uncover en O(1) amorti par lien | exponentiel, mais constantes très faibles |
| CP-SAT (OR-Tools) | modèle entier + AllDifferent | filtrage d'arc-consistance + apprentissage de clauses | NP-complet, résolu par CDCL hybride |
| SAT (Glucose, encodage 9·9·9) | ~729 variables booléennes, milliers de clauses | propagation unitaire (BCP) + CDCL | NP-complet, dépend de l'encodage |
| Algorithme génétique | population d'individus (perms de lignes) | aucune (recherche stochastique guidée par fitness) | pas de garantie de complétude |

Le Sudoku est NP-complet dans sa généralisation n²×n² (Yato & Seta, 2002). Les
solveurs complets (backtracking, DLX, CP-SAT, SAT) garantissent de trouver la
solution ; l'algorithme génétique est une métaheuristique incomplète, ce qui
explique sa dégradation sur les grilles difficiles.
"""


def generate_report(csv_path: Path, out_path: Path, plots_dir: Optional[Path] = None) -> Path:
    import pandas as pd

    csv_path = Path(csv_path)
    out_path = Path(out_path)
    plots_dir = Path(plots_dir) if plots_dir else out_path.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)

    lines = ["# Rapport comparatif : solveurs de Sudoku\n"]
    lines.append(f"Source: `{csv_path.name}` ({len(df)} exécutions).\n")

    # Success rate per solver.
    succ = df.groupby("solver")["solved"].mean().mul(100).round(1)
    lines.append("## Taux de succès global par solveur\n")
    lines.append("| Solveur | Succès (%) | Exécutions |")
    lines.append("|---------|-----------|------------|")
    for solver, rate in succ.items():
        n = int((df["solver"] == solver).sum())
        lines.append(f"| {solver} | {rate} | {n} |")
    lines.append("")

    # Mean solve time per solver x bucket.
    solved = df[df["solved"]]
    if not solved.empty:
        pivot = solved.pivot_table(
            index="bucket", columns="solver", values="elapsed_s", aggfunc="mean"
        )
        pivot = pivot.reindex([b for b in BUCKET_ORDER if b in pivot.index])
        lines.append("## Temps moyen de résolution (s) par bucket\n")
        lines.append(_df_to_md(pivot.round(4)))
        lines.append("")

    # Multi-solution enumeration.
    if "solutions_found" in df.columns:
        multi = df[df["solutions_found"].notna()]
        if not multi.empty:
            lines.append("## Énumération des grilles à solutions multiples\n")
            lines.append(
                "Les grilles du bucket `multi` n'ont pas de solution unique : "
                "seuls les solveurs sachant énumérer (`supports_multi`) sont "
                "lancés (DLX, CP-SAT, SAT), et l'on rapporte le nombre de solutions trouvées "
                "(plafonné juste au-dessus du minimum attendu pour prouver la "
                "non-unicité à moindre coût).\n"
            )
            lines.append("| Grille | Solveur | Solutions trouvées | Temps (s) | Mémoire (octets) |")
            lines.append("|--------|---------|--------------------|-----------|------------------|")
            for _, r in multi.iterrows():
                t = "" if _isnan(r["elapsed_s"]) else f"{float(r['elapsed_s']):.4f}"
                mem = "" if _isnan(r["peak_mem_bytes"]) else int(r["peak_mem_bytes"])
                n = "timeout" if r["timed_out"] else int(r["solutions_found"])
                lines.append(
                    f"| {r['instance_id']} | {r['solver']} | {n} | {t} | {mem} |"
                )
            lines.append("")

    # Per-solver strengths / weaknesses by grid class.
    lines.append(_strengths_section(df))

    # Plots.
    plot_paths = _make_plots(solved, plots_dir, out_path.parent)
    if plot_paths:
        lines.append("## Graphiques\n")
        for title, rel in plot_paths:
            lines.append(f"### {title}\n\n![{title}]({rel})\n")

    lines.append(_THEORY)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


def _strengths_section(df) -> str:
    """Per solver: fastest class, costliest class, and classes it fails.

    excelle = lowest mean time, coûteuse = highest (flagged only if >=3x the
    best), échoue = success rate < 100%.
    """
    lines = ["## Forces et faiblesses par classe de grille\n"]
    lines.append(
        "Lecture directe des mesures empiriques : pour chaque solveur on relève "
        "la classe la plus facile (temps moyen minimal), la classe la plus "
        "coûteuse, et les classes qu'il échoue à résoudre (taux de succès < 100 %).\n"
    )
    lines.append("| Solveur | Excelle sur | Classe la plus coûteuse | Échoue sur |")
    lines.append("|---------|-------------|-------------------------|------------|")
    for solver in sorted(df["solver"].unique()):
        sdf = df[df["solver"] == solver]
        rate = sdf.groupby("bucket")["solved"].mean()
        failed = [b for b, r in rate.items() if r < 1.0]
        # Only fully-solved classes count as a strength.
        full = {b for b, r in rate.items() if r == 1.0}
        ok = sdf[sdf["solved"] & sdf["bucket"].isin(full)]
        times = ok.groupby("bucket")["elapsed_s"].mean().sort_values()
        if times.empty:
            best = worst = "n/a"
        else:
            best = f"{times.index[0]} ({times.iloc[0]:.4f}s)"
            # Flag a costly class only if >=3x the best.
            if len(times) > 1 and times.iloc[-1] >= 3 * max(times.iloc[0], 1e-9):
                worst = f"{times.index[-1]} ({times.iloc[-1]:.4f}s)"
            else:
                worst = "n/a"
        failed_txt = ", ".join(failed) if failed else "aucune"
        lines.append(f"| {solver} | {best} | {worst} | {failed_txt} |")
    lines.append("")
    lines.append(
        "Synthèse : les solveurs complets (backtracking, DLX, CP-SAT, SAT) "
        "résolvent toutes les grilles à solution unique ; le backtracking naïf "
        "se dégrade fortement sur les grilles minimales à 17 indices (espace de "
        "recherche peu contraint), tandis que DLX et SAT restent quasi insensibles "
        "à la difficulté. CP-SAT paie un coût de démarrage fixe élevé mais constant. "
        "L'algorithme génétique, métaheuristique incomplète, ne résout au mieux "
        "que les grilles faciles (et seulement pour certaines graines) et échoue "
        "dès que la grille exige une recherche profonde. "
        "DLX, CP-SAT et SAT savent énumérer et traiter le bucket `multi` à "
        "solutions multiples (SAT par ajout de clauses de blocage) ; backtracking "
        "et génétique n'y sont pas applicables.\n"
    )
    return "\n".join(lines)


def _df_to_md(df) -> str:
    cols = list(df.columns)
    header = "| bucket | " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    rows = [header, sep]
    for idx, row in df.iterrows():
        cells = " | ".join("" if _isnan(v) else str(v) for v in row)
        rows.append(f"| {idx} | {cells} |")
    return "\n".join(rows)


def _isnan(v) -> bool:
    try:
        return v != v  # NaN
    except Exception:
        return False


def _make_plots(solved, plots_dir: Path, report_dir: Path):
    if solved.empty:
        return []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import os

    paths = []

    # Mean time per solver x bucket.
    fig, ax = plt.subplots(figsize=(8, 5))
    pivot = solved.pivot_table(
        index="bucket", columns="solver", values="elapsed_s", aggfunc="mean"
    ).reindex([b for b in BUCKET_ORDER if b in solved["bucket"].unique()])
    pivot.plot(kind="bar", ax=ax, logy=True)
    ax.set_ylabel("temps moyen (s, échelle log)")
    ax.set_title("Temps de résolution par difficulté")
    fig.tight_layout()
    p = plots_dir / "time_by_bucket.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    paths.append(("Temps par bucket", os.path.relpath(p, report_dir)))

    # Mean nodes per solver (where available).
    node_df = solved.dropna(subset=["nodes"])
    if not node_df.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        pivot = node_df.pivot_table(
            index="bucket", columns="solver", values="nodes", aggfunc="mean"
        ).reindex([b for b in BUCKET_ORDER if b in node_df["bucket"].unique()])
        pivot.plot(kind="bar", ax=ax, logy=True)
        ax.set_ylabel("nœuds explorés (échelle log)")
        ax.set_title("Nœuds explorés par difficulté")
        fig.tight_layout()
        p = plots_dir / "nodes_by_bucket.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(("Nœuds par bucket", os.path.relpath(p, report_dir)))

    return paths
