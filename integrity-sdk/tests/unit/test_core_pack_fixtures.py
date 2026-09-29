from pathlib import Path

from integrity_sdk.core.packs import compile_pack


ROOT = Path(__file__).parents[3]
REQUIRED_CONTROLS = {
    "HIPAA-164.312(a)(1)",
    "HIPAA-164.312(b)",
    "HIPAA-164.502(b)",
    "SOC2-CC6.1",
    "SOC2-CC7.2",
    "ISO42001",
}


def test_base_and_hipaa_fixtures_compile_with_required_controls():
    for name in ("base", "hipaa"):
        pack_dir = ROOT / "packs" / name
        compiled = compile_pack(pack_dir)
        assert compiled.manifest["name"] == name
        assert set(compiled.manifest["event_classes"]) == {
            "agent.tool_call",
            "agent.read",
            "device.sensor",
        }
        controls = compiled.files["controls.yaml"].decode("utf-8")
        assert REQUIRED_CONTROLS <= {line.split(":", 1)[0] for line in controls.splitlines() if line and not line.startswith(" ")}
        assert compile_pack(pack_dir).pack_hash == compiled.pack_hash
