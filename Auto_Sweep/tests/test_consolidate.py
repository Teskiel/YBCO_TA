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


class TestIsJunk:
    """is_junk 判定空壳/失败启动。"""

    def test_given_no_s2p_and_no_metadata_when_is_junk_then_true(self):
        from consolidate import is_junk, RunInfo
        info = RunInfo(id="empty", path="/tmp/empty")
        info.s2p_count = 0
        info.has_manifest = False
        info.has_status = False
        assert is_junk(info) is True

    def test_given_few_s2p_and_no_metadata_when_is_junk_then_true(self):
        from consolidate import is_junk, RunInfo
        info = RunInfo(id="tiny", path="/tmp/tiny")
        info.s2p_count = 3
        info.has_manifest = False
        info.has_status = False
        assert is_junk(info) is True

    def test_given_few_s2p_but_has_manifest_when_is_junk_then_false(self):
        from consolidate import is_junk, RunInfo
        info = RunInfo(id="tiny_but_real", path="/tmp/tiny")
        info.s2p_count = 2
        info.has_manifest = True
        assert is_junk(info) is False

    def test_given_many_s2p_when_is_junk_then_false(self):
        from consolidate import is_junk, RunInfo
        info = RunInfo(id="big", path="/tmp/big")
        info.s2p_count = 50
        info.has_manifest = False
        assert is_junk(info) is False


class TestGroupRuns:
    """group_runs 按 (Pv, Pl) 一致 + 温度相邻/重叠 分组。"""

    def test_given_same_params_contiguous_temps_when_group_then_one_group(self):
        """相同参数、温度互补的碎片归为一组。"""
        from consolidate import group_runs, RunInfo

        r1 = RunInfo(id="run1", path="/tmp/run1")
        r1.params_hash = "abc123"
        r1.target_temps = {10.0, 12.0, 14.0}
        r1.vna_power_plan = [-55, -45]
        r1.laser_power_plan = [0, 5]

        r2 = RunInfo(id="run2", path="/tmp/run2")
        r2.params_hash = "abc123"
        r2.target_temps = {16.0, 18.0, 20.0}
        r2.vna_power_plan = [-55, -45]
        r2.laser_power_plan = [0, 5]

        groups = group_runs([r1, r2])
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_given_different_params_when_group_then_separate_groups(self):
        """不同参数分开。"""
        from consolidate import group_runs, RunInfo

        r1 = RunInfo(id="run1", path="/tmp/run1")
        r1.params_hash = "aaa111"
        r1.target_temps = {50.0}
        r1.vna_power_plan = [-55, -45]
        r1.laser_power_plan = [0, 5]

        r2 = RunInfo(id="run2", path="/tmp/run2")
        r2.params_hash = "bbb222"
        r2.target_temps = {50.0}
        r2.vna_power_plan = [-45, -35]  # different VNA range
        r2.laser_power_plan = [0, 5]

        groups = group_runs([r1, r2])
        assert len(groups) == 2

    def test_given_same_params_large_temp_gap_when_group_then_separate(self):
        """温度差距超过 1 个 step 的数据分开。"""
        from consolidate import group_runs, RunInfo

        r1 = RunInfo(id="run1", path="/tmp/run1")
        r1.params_hash = "same"
        r1.target_temps = {10.0, 12.0}
        r1.vna_power_plan = [-55]
        r1.laser_power_plan = [0]

        r2 = RunInfo(id="run2", path="/tmp/run2")
        r2.params_hash = "same"
        r2.target_temps = {50.0, 52.0}  # gap from 12 to 50 >> 2 steps
        r2.vna_power_plan = [-55]
        r2.laser_power_plan = [0]

        groups = group_runs([r1, r2])
        assert len(groups) == 2  # gap too large, separate groups
