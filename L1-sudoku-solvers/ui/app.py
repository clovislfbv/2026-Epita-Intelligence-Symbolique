"""Streamlit UI: Playground to run solvers on a grid, Dashboard to read benchmarks.

Run with: streamlit run ui/app.py
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from sudoku.board import Grid
from sudoku.generator import BUCKET_ORDER, generate_puzzle, load_instances
from sudoku.solvers import SOLVERS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "benchmarks" / "results" / "results.csv"

st.set_page_config(page_title="Sudoku multi-solveurs", layout="wide")


# Rendering helpers
def render_grid(grid: Grid, clues: Grid | None = None) -> str:
    """Return an HTML table for a grid; cells present in ``clues`` are bold."""
    cells = []
    for r in range(9):
        row = []
        for c in range(9):
            v = grid.at(r, c)
            given = clues is not None and clues.at(r, c) != 0
            txt = str(v) if v != 0 else "&nbsp;"
            bt = "3px solid #222" if r % 3 == 0 else "1px solid #bbb"
            bl = "3px solid #222" if c % 3 == 0 else "1px solid #bbb"
            br = "3px solid #222" if c == 8 else "0"
            bb = "3px solid #222" if r == 8 else "0"
            color = "#111" if given else "#1a73e8"
            weight = "700" if given else "500"
            bg = "#f3f3f3" if given else "#fff"
            row.append(
                f'<td style="width:38px;height:38px;text-align:center;'
                f'font-size:20px;font-weight:{weight};color:{color};background:{bg};'
                f'border-top:{bt};border-left:{bl};border-right:{br};'
                f'border-bottom:{bb};">{txt}</td>'
            )
        cells.append("<tr>" + "".join(row) + "</tr>")
    return (
        '<table style="border-collapse:collapse;margin:auto;">'
        + "".join(cells)
        + "</table>"
    )


def grid_to_df(grid: Grid) -> pd.DataFrame:
    """9x9 DataFrame of nullable ints; empty cells are <NA> so they show blank."""
    data = [[grid.at(r, c) or pd.NA for c in range(9)] for r in range(9)]
    df = pd.DataFrame(data, columns=[str(c + 1) for c in range(9)])
    df.index = [str(r + 1) for r in range(9)]
    return df.astype("Int64")


def df_to_grid(df: pd.DataFrame) -> Grid:
    """Rebuild a Grid from the edited table; blanks / out-of-range -> empty."""
    cells = []
    for r in range(9):
        for c in range(9):
            v = df.iat[r, c]
            cells.append(int(v) if pd.notna(v) and 1 <= int(v) <= 9 else 0)
    return Grid(tuple(cells))


def fmt_mem(b) -> str:
    if b is None:
        return "n/a"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# Playground
def playground() -> None:
    st.header("Playground : résoudre une grille")
    instances = load_instances()
    by_id = {i.id: i for i in instances}

    st.session_state.setdefault("gen_token", 0)
    MANUAL = "(saisie manuelle)"

    col_in, col_out = st.columns([1, 1])

    with col_in:
        with st.expander("Générer une grille (unicité certifiée par DLX)"):
            gcol1, gcol2 = st.columns([2, 1])
            gbucket = gcol1.selectbox(
                "Difficulté",
                ["easy", "medium", "hard", "very_hard", "multi"],
                index=1,
                key="gen_bucket",
            )
            gseed = gcol2.number_input("Graine", value=0, step=1, key="gen_seed")
            if st.button("Générer", use_container_width=True):
                with st.spinner("génération…"):
                    g = generate_puzzle(gbucket, seed=int(gseed))
                st.session_state["gen_grid"] = g.to_line()
                st.session_state["gen_token"] += 1
                st.session_state["grid_choice"] = MANUAL
                st.rerun()
            st.caption("La grille générée est chargée dans la saisie manuelle.")

        choice = st.selectbox(
            "Grille prédéfinie",
            [MANUAL] + list(by_id.keys()),
            help="Choisir une instance du benchmark, puis éditer les cases ci-dessous.",
            key="grid_choice",
        )
        if choice in by_id:
            base = by_id[choice].grid
        elif "gen_grid" in st.session_state:
            base = Grid.parse(st.session_state["gen_grid"])
        else:
            base = Grid(tuple([0] * 81))

        st.caption("Cliquez une case et tapez un chiffre (1–9). Laissez vide sinon.")
        edited = st.data_editor(
            grid_to_df(base),
            key=f"grid_editor_{choice}_{st.session_state.gen_token}",
            use_container_width=True,
            column_config={
                str(c + 1): st.column_config.NumberColumn(
                    min_value=1, max_value=9, step=1, format="%d", width="small"
                )
                for c in range(9)
            },
        )
        col_clear, _ = st.columns([1, 2])
        if col_clear.button("Réinitialiser", use_container_width=True):
            st.session_state.pop(
                f"grid_editor_{choice}_{st.session_state.gen_token}", None
            )
            st.session_state.pop("gen_grid", None)
            st.rerun()

        try:
            grid = df_to_grid(edited)
            valid = grid.is_valid()
        except ValueError as exc:
            st.error(f"Grille invalide : {exc}")
            return
        if not valid:
            st.warning("La grille contient des doublons : elle n'est pas résoluble.")

        solver_names = st.multiselect(
            "Solveurs", list(SOLVERS.keys()), default=["dlx", "backtracking"]
        )
        if "genetic" in solver_names:
            seed = st.number_input("Graine (génétique)", value=42, step=1)
        else:
            seed = 42
        run = st.button("Résoudre", type="primary", use_container_width=True)

    with col_out:
        st.caption(f"Indices : **{grid.num_clues}** · valide : **{valid}**")
        st.markdown(render_grid(grid), unsafe_allow_html=True)

    if not run:
        return
    if not solver_names:
        st.info("Sélectionnez au moins un solveur.")
        return

    rows = []
    solutions = {}
    for name in solver_names:
        cls = SOLVERS[name]
        solver = cls(seed=int(seed)) if name == "genetic" else cls()
        with st.spinner(f"{name}…"):
            result = solver.solve(grid)
        rows.append(
            {
                "solveur": name,
                "résolu": "✅" if result.solved else "❌",
                "temps (s)": round(result.elapsed_s, 4),
                "nœuds": result.nodes,
                "mémoire": fmt_mem(result.peak_mem_bytes),
            }
        )
        if result.solved:
            solutions[name] = result.solution

    st.subheader("Métriques")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    if solutions:
        st.subheader("Solution")
        sols = list(solutions.items())
        # Complete solvers must agree on the unique solution.
        distinct = {g.to_line() for g in solutions.values()}
        if len(distinct) > 1:
            st.warning("Les solveurs ne s'accordent pas (grille à solutions multiples ?)")
        name, sol = sols[0]
        st.caption(f"(rendu : {name})")
        st.markdown(render_grid(sol, clues=grid), unsafe_allow_html=True)


# Dashboard
def dashboard() -> None:
    st.header("Dashboard : comparaison des solveurs")

    src = st.radio(
        "Source des résultats",
        ["Fichier par défaut", "Téléverser un CSV"],
        horizontal=True,
    )
    if src == "Téléverser un CSV":
        up = st.file_uploader("results.csv", type="csv")
        if up is None:
            st.info("Téléversez un CSV de benchmark, ou utilisez le fichier par défaut.")
            return
        df = pd.read_csv(up)
    else:
        if not DEFAULT_CSV.exists():
            st.warning(
                f"Aucun résultat trouvé en `{DEFAULT_CSV.relative_to(ROOT)}`. "
                "Lancez d'abord : `sudoku-bench benchmark --out benchmarks/results/results.csv`."
            )
            return
        df = pd.read_csv(DEFAULT_CSV)

    st.caption(f"{len(df)} exécutions · {df['solver'].nunique()} solveurs.")

    # Success rate per solver.
    succ = (
        df.groupby("solver")["solved"].mean().mul(100).round(1).reset_index(name="succès (%)")
    )
    st.subheader("Taux de succès par solveur")
    chart = (
        alt.Chart(succ)
        .mark_bar()
        .encode(
            x=alt.X("solver:N", title="solveur", sort="-y"),
            y=alt.Y("succès (%):Q", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("solver:N", legend=None),
            tooltip=["solver", "succès (%)"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)

    solved = df[df["solved"]].copy()
    if solved.empty:
        st.info("Aucune résolution réussie dans ce CSV.")
        return

    bucket_sort = [b for b in BUCKET_ORDER if b in solved["bucket"].unique()]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Temps moyen par bucket")
        time_df = solved[solved["elapsed_s"] > 0]
        if time_df.empty:
            st.info("Pas de temps mesuré.")
        else:
            st.altair_chart(
                _trend_chart(time_df, "elapsed_s", "temps (s)", bucket_sort),
                use_container_width=True,
            )
            st.caption("Échelle logarithmique.")
    with c2:
        st.subheader("Nœuds moyens par bucket")
        # Log scale needs > 0; drop runs reporting 0 nodes (e.g. CP-SAT/SAT).
        node_df = solved.dropna(subset=["nodes"])
        node_df = node_df[node_df["nodes"] > 0]
        if node_df.empty:
            st.info("Pas de comptage de nœuds disponible.")
        else:
            st.altair_chart(
                _trend_chart(node_df, "nodes", "nœuds", bucket_sort),
                use_container_width=True,
            )
            st.caption(
                "Échelle logarithmique. Les exécutions sans nœud rapporté (0) sont exclues."
            )

    with st.expander("Données brutes"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def _trend_chart(df: pd.DataFrame, value: str, title: str, bucket_sort) -> alt.Chart:
    """Log-scale point+line chart of ``value`` per bucket and solver.

    Points/lines, not bars: bars draw from a zero baseline, undefined on a log
    axis. Caller must filter values to > 0.
    """
    agg = df.groupby(["bucket", "solver"])[value].mean().reset_index()
    base = alt.Chart(agg).encode(
        x=alt.X("bucket:N", sort=bucket_sort, title="difficulté"),
        y=alt.Y(f"{value}:Q", title=title, scale=alt.Scale(type="log")),
        color=alt.Color("solver:N", title="solveur"),
        tooltip=["bucket", "solver", alt.Tooltip(f"{value}:Q", format=".4f")],
    )
    return (base.mark_line(point=False) + base.mark_point(size=80, filled=True)).properties(
        height=320
    )


def main() -> None:
    st.title("Sudoku : résolution par multiples solveurs")
    st.caption("Backtracking · Dancing Links · CP-SAT · SAT · Algorithme génétique")
    tab1, tab2 = st.tabs(["Playground", "Dashboard"])
    with tab1:
        playground()
    with tab2:
        dashboard()


main()
