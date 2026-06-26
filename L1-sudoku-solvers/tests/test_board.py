from sudoku.board import Grid

PUZZLE = "53..7....6..195....98....6.8...6...34..8.3..17...2...6.6....28....419..5....8..79"
SOLUTION = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"


def test_parse_roundtrip():
    g = Grid.parse(PUZZLE)
    assert g.to_line() == PUZZLE
    assert g.num_clues == sum(ch.isdigit() for ch in PUZZLE)


def test_parse_ignores_formatting():
    pretty = Grid.parse(PUZZLE).to_pretty()
    assert Grid.parse(pretty).to_line() == PUZZLE


def test_solution_is_valid_and_solved():
    g = Grid.parse(SOLUTION)
    assert g.is_complete()
    assert g.is_valid()
    assert g.is_solved()


def test_detects_invalid_grid():
    bad = Grid.parse("11" + "." * 79)
    assert not bad.is_valid()


def test_wrong_length_rejected():
    import pytest

    with pytest.raises(ValueError):
        Grid.parse("123")
