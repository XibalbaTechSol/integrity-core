from __future__ import annotations

import builtins
import os
from unittest import mock

import pytest

from integrity_sdk.hardware import get_virtualization_env


def test_get_virtualization_env_hypervisor():
    with mock.patch("builtins.open", mock.mock_open(read_data="processor\nvendor_id : GenuineIntel\nflags : fpu vme hypervisor lahf_lm\n")) as mock_file:
        assert get_virtualization_env() == "virtualized"
        mock_file.assert_called_once_with("/proc/cpuinfo", "r")

def test_get_virtualization_env_docker():
    with mock.patch("builtins.open", mock.mock_open(read_data="processor\nvendor_id : GenuineIntel\n")) as mock_file:
        with mock.patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            assert get_virtualization_env() == "docker"
            mock_file.assert_called_once_with("/proc/cpuinfo", "r")
            mock_exists.assert_called_once_with("/.dockerenv")

def test_get_virtualization_env_none():
    with mock.patch("builtins.open") as mock_file:
        mock_file.side_effect = Exception("file not found")
        with mock.patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            assert get_virtualization_env() == "none"
            mock_file.assert_called_once_with("/proc/cpuinfo", "r")
            mock_exists.assert_called_once_with("/.dockerenv")

def test_get_virtualization_env_error_paths(monkeypatch):
    def mock_open(*args, **kwargs):
        raise Exception("/proc/cpuinfo not found")

    def mock_exists(*args, **kwargs):
        return False

    monkeypatch.setattr(builtins, "open", mock_open)
    monkeypatch.setattr(os.path, "exists", mock_exists)

    assert get_virtualization_env() == "none"
