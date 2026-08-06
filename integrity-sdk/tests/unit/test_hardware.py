from __future__ import annotations

import builtins
import subprocess
from unittest import mock

import pytest

from integrity_sdk.hardware import get_virtualization_env


def test_get_virtualization_env_subprocess_success():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout="kvm\n")
        assert get_virtualization_env() == "kvm"
        mock_run.assert_called_once()

def test_get_virtualization_env_subprocess_failure_cpuinfo_success():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("command not found")

        with mock.patch("builtins.open", mock.mock_open(read_data="processor\nvendor_id : GenuineIntel\nflags : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ss ht syscall nx pdpe1gb rdtscp lm constant_tsc rep_good nopl xtopology cpuid tsc_known_freq pni pclmulqdq ssse3 fma cx16 pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand hypervisor lahf_lm abm 3dnowprefetch invpcid_single pti fsgsbase tsc_adjust bmi1 hle avx2 smep bmi2 erms invpcid rtm mpx avx512f avx512dq rdseed adx smap clflushopt clwb avx512cd avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves arat pku ospke avx512_vnni\n")) as mock_file:
            assert get_virtualization_env() == "virtualized"
            mock_file.assert_called_once_with("/proc/cpuinfo", "r")

def test_get_virtualization_env_subprocess_failure_cpuinfo_no_hypervisor_dockerenv_exists():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("command not found")

        with mock.patch("builtins.open", mock.mock_open(read_data="processor\nvendor_id : GenuineIntel\n")) as mock_file:
            with mock.patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                assert get_virtualization_env() == "docker"
                mock_exists.assert_called_once_with("/.dockerenv")

def test_get_virtualization_env_subprocess_failure_cpuinfo_failure_dockerenv_not_exists():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = Exception("command not found")

        with mock.patch("builtins.open") as mock_file:
            mock_file.side_effect = Exception("file not found")

            with mock.patch("os.path.exists") as mock_exists:
                mock_exists.return_value = False
                assert get_virtualization_env() == "none"

def test_get_virtualization_env_subprocess_returns_nonzero():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=1, stdout="none\n")

        with mock.patch("builtins.open") as mock_file:
            mock_file.side_effect = Exception("file not found")

            with mock.patch("os.path.exists") as mock_exists:
                mock_exists.return_value = False
                assert get_virtualization_env() == "none"
def test_get_virtualization_env_error_paths(monkeypatch):
    def mock_run(*args, **kwargs):
        raise Exception("systemd-detect-virt failed")

    def mock_open(*args, **kwargs):
        raise Exception("/proc/cpuinfo not found")

    def mock_exists(*args, **kwargs):
        return False

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(builtins, "open", mock_open)
    monkeypatch.setattr(os.path, "exists", mock_exists)

    assert get_virtualization_env() == "none"
