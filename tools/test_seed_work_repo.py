import tempfile
from pathlib import Path

from seed_work_repo import collect


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    history = root / "history"
    current = root / "current"
    history.mkdir()
    current.mkdir()
    (history / "adv_dear_hume_001.csv").touch()
    (current / "adv_dear_hume_029.csv").touch()

    plan = collect(["adv_dear_hume"], "", 0, current)
    assert [name for name, _ in plan["adv_dear_hume"]] == [
        "adv_dear_hume_029.csv"
    ]
