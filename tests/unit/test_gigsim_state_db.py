"""GigSim stand-in keeps its state in a database when GIGSIM_STATE_DB is set (hosts without a persistent disk)."""

from gigsim_standin.sim import Simulator


def test_state_survives_restart_in_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGSIM_STATE_DB", f"sqlite:///{tmp_path / 'sim.db'}")
    first = Simulator(state_path=tmp_path / "unused.json")
    first.state["tick"] = 7
    first._save()
    second = Simulator(state_path=tmp_path / "unused.json")
    assert second.state["tick"] == 7
    assert not (tmp_path / "unused.json").exists()
