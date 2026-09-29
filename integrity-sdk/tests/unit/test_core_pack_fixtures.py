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
GOLDEN_HASHES = {
    "base": "sha256:407b27b472911d7aa3716119f9a1bdd7091f850043b60bbd43c8b8a4bad731c5",
    "hipaa": "sha256:5c3c1c2ed43d7cb472e9809e491b670ed2aa9383e278bdae2ee1f4679ea09c53",
}


def test_base_and_hipaa_fixtures_compile_with_required_controls():
    for name in ("base", "hipaa"):
        pack_dir = ROOT / "packs" / name
        compiled = compile_pack(pack_dir)
        assert compiled.manifest["name"] == name
        assert compiled.pack_hash == GOLDEN_HASHES[name]
        assert set(compiled.manifest["event_classes"]) == {
            "agent.tool_call",
            "agent.read",
            "device.sensor",
        }
        controls = compiled.files["controls.yaml"].decode("utf-8")
        assert REQUIRED_CONTROLS <= {line.split(":", 1)[0] for line in controls.splitlines() if line and not line.startswith(" ")}
        assert compile_pack(pack_dir).pack_hash == compiled.pack_hash
