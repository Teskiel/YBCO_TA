# -*- coding: utf-8 -*-
"""BDD tests for consolidate.py — 实验数据整合工具"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScanRun:
    """Given an experiment output directory, scan_run extracts parameters."""

    def test_given_manifest_when_scan_then_params_from_manifest(self):
        """有 manifest.json 时直接从 manifest 读取参数计划。"""
        from consolidate import scan_run, RunInfo

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "20260623_155113")
            os.makedirs(run_dir)
            manifest = {
                "experiment_id": "20260623_155113",
                "start_time": "2026-06-23T15:51:13",
                "temperature_plan": [50.0, 60.0, 70.0],
                "vna_power_plan": [-55, -45],
                "laser_power_plan": [0, 5, 9],
            }
            with open(os.path.join(run_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f)

            info = scan_run(run_dir)
            assert info is not None
            assert info.id == "20260623_155113"
            assert info.params_hash is not None
            assert 50.0 in info.target_temps
            assert 70.0 in info.target_temps
            assert info.timestamp is not None

    def test_given_status_json_when_scan_then_params_from_status(self):
        """有 status.json 但无 manifest 时从 status 读取。"""
        from consolidate import scan_run

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "20260617_193744")
            os.makedirs(run_dir)
            status = {
                "experiment_id": "20260617_193744",
                "start_time": "2026-06-17T19:37:44",
                "temperature_plan": [40.0, 50.0],
                "vna_power_plan": [-45, -35],
                "laser_power_plan": [0, 1, 3],
            }
            with open(os.path.join(run_dir, "status.json"), "w") as f:
                json.dump(status, f)

            info = scan_run(run_dir)
            assert info is not None
            assert info.id == "20260617_193744"
            assert info.target_temps == {40.0, 50.0}

    def test_given_no_metadata_when_scan_then_infer_from_dirs(self):
        """无任何元数据时从目录结构反推。"""
        from consolidate import scan_run

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "20260606_092046")
            os.makedirs(run_dir)
            os.makedirs(os.path.join(run_dir, "50K", "-55dBm", "00mW"))
            with open(os.path.join(run_dir, "50K", "-55dBm", "00mW",
                                     "YBCO_-55dBm_00mW_target_50K_actual_49.994K.s2p"), "w") as f:
                f.write("")

            info = scan_run(run_dir)
            assert info is not None
            assert 50.0 in info.target_temps
            assert info.s2p_count == 1
            assert not info.has_manifest

    def test_given_empty_dir_when_scan_then_returns_runinfo(self):
        """空目录仍然返回 RunInfo（后续归类为 junk）。"""
        from consolidate import scan_run

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "empty_run")
            os.makedirs(run_dir)

            info = scan_run(run_dir)
            assert info is not None
            assert info.s2p_count == 0
            assert not info.has_manifest
