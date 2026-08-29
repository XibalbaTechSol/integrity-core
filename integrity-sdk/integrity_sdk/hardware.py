"""
Host-machine fingerprinting utilities. NOTE: this is no longer used to
derive DID identity (see did.py's module docstring — identity is key-based,
not hardware-based, per docs/INTERFACE_CONTRACT.md §4.1). It remains useful
as informational metadata for telemetry/attestation payloads (e.g. the
software-fallback "attestation" reported when no real TEE is present — see
security/attestation.py) and is kept here as a small, real, dependency-light
utility module.
"""

from __future__ import annotations

import hashlib
import os
import re
import socket
import subprocess
import uuid


def get_machine_id() -> str:
    try:
        with open("/etc/machine-id", "r") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return ""


def get_mac_address() -> str:
    try:
        out = subprocess.check_output(
            ["ip", "-o", "link", "show"], stderr=subprocess.DEVNULL, timeout=2
        ).decode()
        for line in out.splitlines():
            if "link/ether" in line and "lo:" not in line:
                m = re.search(r"link/ether\s+([0-9a-f:]{17})", line)
                if m:
                    return m.group(1)
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass

    node = uuid.getnode()
    return ":".join(f"{(node >> (8 * i)) & 0xFF:02x}" for i in reversed(range(6)))


def get_hostname() -> str:
    return socket.gethostname()


def get_cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (FileNotFoundError, PermissionError):
        pass
    return ""


def generate_hardware_fingerprint() -> str:
    """SHA-256 over machine-id + MAC + hostname. CPU model is intentionally
    excluded so a microcode/BIOS update doesn't change the fingerprint."""
    canonical = f"{get_machine_id()}|{get_mac_address()}|{get_hostname()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_virtualization_env() -> str:
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "hypervisor" in line.lower():
                    return "virtualized"
    except Exception:
        pass
    if os.path.exists("/.dockerenv"):
        return "docker"
    return "none"


def get_hardware_attestation() -> dict:
    """A best-effort *software* fingerprinting report — NOT a cryptographic
    hardware attestation. Used as the fallback `type: "software"` report in
    security/attestation.py when no real TEE is detected."""
    return {
        "machine_id": get_machine_id(),
        "mac_address": get_mac_address(),
        "hostname": get_hostname(),
        "cpu_model": get_cpu_model(),
        "fingerprint": generate_hardware_fingerprint(),
        "virtualization": get_virtualization_env(),
    }
