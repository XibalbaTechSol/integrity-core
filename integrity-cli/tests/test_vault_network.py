"""`vault sync` resolves its RPC and deployments file through the --network profile."""
from __future__ import annotations

from typer.testing import CliRunner

from integrity_cli import config, vault
from integrity_cli.main import app

runner = CliRunner()


def test_vault_sync_honors_the_network_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("RPC_URL", raising=False)
    monkeypatch.delenv("DEPLOYMENTS_FILE", raising=False)
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n")
    seen = {}

    def fake_sync(agent_name, transcript_path, rpc_url, deployments_file):
        seen.update(rpc_url=rpc_url, deployments_file=deployments_file)
        return {"memory_file": "m", "state_root": "0x00", "anchored_on_chain": False}

    monkeypatch.setattr(vault, "sync_vault", fake_sync)
    result = runner.invoke(app, ["--network", "base-sepolia", "vault", "sync", "agent", "--transcript", str(transcript)])
    assert result.exit_code == 0, result.stdout
    profile = config.NETWORK_PROFILES["base-sepolia"]
    assert seen == {"rpc_url": profile["RPC_URL"], "deployments_file": profile["DEPLOYMENTS_FILE"]}


def test_vault_sync_explicit_flags_still_win_over_the_profile(tmp_path, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n")
    seen = {}
    monkeypatch.setattr(vault, "sync_vault", lambda a, t, r, d: seen.update(r=r, d=d) or {"memory_file": "m", "state_root": "0x00"})
    result = runner.invoke(app, [
        "--network", "base-sepolia", "vault", "sync", "agent", "--transcript", str(transcript),
        "--rpc-url", "http://flag:1", "--deployments-file", "flag.json",
    ])
    assert result.exit_code == 0, result.stdout
    assert seen == {"r": "http://flag:1", "d": "flag.json"}
