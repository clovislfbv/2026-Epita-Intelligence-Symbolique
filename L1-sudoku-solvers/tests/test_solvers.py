import importlib

import pytest

from sudoku.board import Grid
from sudoku.solvers import BacktrackingSolver, DancingLinksSolver

PUZZLE = "53..7....6..195....98....6.8...6...34..8.3..17...2...6.6....28....419..5....8..79"
SOLUTION = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"

# Solvers that are guaranteed available (pure-Python).
CORE_SOLVERS = [BacktrackingSolver, DancingLinksSolver]


def _maybe(modpath, clsname):
    try:
        mod = importlib.import_module(modpath)
        # also check the heavy dependency imports
        return getattr(mod, clsname)
    except Exception:
        return None


@pytest.mark.parametrize("cls", CORE_SOLVERS)
def test_core_solver_solves_easy(cls):
    result = cls().solve(Grid.parse(PUZZLE))
    assert result.solved
    assert result.solution.to_line() == SOLUTION


@pytest.mark.parametrize("cls", CORE_SOLVERS)
def test_core_solver_reports_nodes(cls):
    result = cls().solve(Grid.parse(PUZZLE))
    assert result.nodes is not None and result.nodes > 0


def test_optional_solvers_agree():
    """CP-SAT and SAT, if their deps are installed, must match the known solution."""
    checked = 0
    for modpath, clsname, dep in [
        ("sudoku.solvers.cp_sat", "CpSatSolver", "ortools"),
        ("sudoku.solvers.sat", "SatSolver", "pysat"),
    ]:
        if importlib.util.find_spec(dep) is None:
            continue
        cls = _maybe(modpath, clsname)
        result = cls().solve(Grid.parse(PUZZLE))
        assert result.solved, f"{clsname} failed to solve"
        assert result.solution.to_line() == SOLUTION
        checked += 1
    if checked == 0:
        pytest.skip("neither ortools nor pysat installed")


def test_dlx_enumerates_multiple_solutions():
    empty = Grid.parse("." * 81)
    sols = DancingLinksSolver().solve_all(empty, limit=2)
    assert len(sols) == 2
    assert all(s.is_solved() for s in sols)
    assert sols[0].to_line() != sols[1].to_line()


def test_sat_enumerates_multiple_solutions():
    if importlib.util.find_spec("pysat") is None:
        pytest.skip("pysat not installed")
    from sudoku.solvers import SatSolver

    empty = Grid.parse("." * 81)
    sols = SatSolver().solve_all(empty, limit=3)
    assert len(sols) == 3
    assert all(s.is_solved() for s in sols)
    # Blocking clauses must yield distinct assignments.
    assert len({s.to_line() for s in sols}) == 3


def test_genetic_solves_easy():
    from sudoku.solvers import GeneticSolver

    # Easy grid with a small budget and fixed seed should converge.
    result = GeneticSolver(generations=200, population=150, seed=42).solve(Grid.parse(PUZZLE))
    assert result.solved
    assert result.solution.to_line() == SOLUTION
