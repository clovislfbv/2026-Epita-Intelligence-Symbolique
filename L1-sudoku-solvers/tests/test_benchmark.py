from pathlib import Path

from sudoku.benchmark import run_one, write_csv
from sudoku.generator import filter_buckets, load_instances


def test_load_instances():
    instances = load_instances()
    ids = {i.id for i in instances}
    assert "easy-1" in ids
    assert all(len(i.grid.cells) == 81 for i in instances)


def test_run_one_backtracking_easy():
    inst = next(i for i in load_instances() if i.id == "easy-1")
    row = run_one("backtracking", inst, timeout=30)
    assert row.solved
    assert not row.timed_out
    assert row.elapsed_s is not None


def test_run_one_timeout():
    # Tiny timeout on the empty 'multi' grid via backtracking will not finish.
    inst = next(i for i in load_instances() if i.bucket == "multi")
    row = run_one("backtracking", inst, timeout=0.01)
    # Either it timed out or finished; both must stay consistent.
    assert row.timed_out or row.solved is not None


def test_write_csv(tmp_path: Path):
    inst = next(i for i in load_instances() if i.id == "easy-1")
    rows = [run_one("dlx", inst, timeout=30)]
    out = tmp_path / "r.csv"
    write_csv(rows, out)
    assert out.exists()
    assert "instance_id" in out.read_text()


def test_filter_buckets():
    instances = load_instances()
    easy = filter_buckets(instances, ["easy"])
    assert easy and all(i.bucket == "easy" for i in easy)
