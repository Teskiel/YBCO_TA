# -*- coding: utf-8 -*-
"""completeness_checker.py 单元测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from pathlib import Path
import completeness_checker as cc


@pytest.fixture
def mock_merged_dir(tmp_path):
    """
    创建模拟合并目录：
    6K, 8K, 10K × -25dBm, -30dBm × 00mW, 01mW, 03mW
    故意缺失:
      - 8K/-30dBm/01mW (isolated — 周围完整)
      - 10K/-30dBm/00mW, 01mW, 03mW (连续3个 → block)
    """
    data = tmp_path
    files_to_create = [
        (6, 25, 0), (6, 25, 1), (6, 25, 3),
        (6, 30, 0), (6, 30, 1), (6, 30, 3),
        (8, 25, 0), (8, 25, 1), (8, 25, 3),
        # 故意缺失: 8K/-30dBm/01mW
        (8, 30, 0), (8, 30, 3),
        (10, 25, 0), (10, 25, 1), (10, 25, 3),
        # 故意缺失全部: 10K/-30dBm/*
    ]
    for temp, vna, laser in files_to_create:
        d = data / f"{temp}K" / f"-{vna}dBm" / f"{laser:02d}mW"
        d.mkdir(parents=True)
        (d / "data.s2p").write_text("")
    return data


class TestBuildCompletenessMatrix:
    """build_completeness_matrix() 测试"""

    def test_correct_shape(self, mock_merged_dir):
        """返回正确形状的 3D 布尔数组"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        assert matrix.shape == (3, 2, 3)
        assert matrix.dtype == bool

    def test_found_and_missing_cells(self, mock_merged_dir):
        """正确标记存在和缺失的格子"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        # 6K 全部完整
        assert matrix[0, :, :].all()
        # 8K/-30dBm/01mW 缺失
        assert matrix[1, 1, 0]     # 8K/-30dBm/00mW ✓
        assert not matrix[1, 1, 1] # 8K/-30dBm/01mW ✗
        assert matrix[1, 1, 2]     # 8K/-30dBm/03mW ✓
        # 10K/-30dBm 全部缺失
        assert matrix[2, 0, :].all()   # 10K/-25dBm 完整
        assert not matrix[2, 1, :].any()  # 10K/-30dBm 全缺

    def test_total_found_count(self, mock_merged_dir):
        """sum(matrix) 等于实际文件数"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        n_expected = 3 * 2 * 3  # 18
        assert int(matrix.sum()) == 18 - 1 - 3  # 14 (缺4个)


class TestDiagnoseMissing:
    """diagnose_missing() 测试"""

    def test_classifies_isolated_edge_block(self, mock_merged_dir):
        """分类: isolated / edge / block"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        # 8K/-30dBm/01mW → isolated
        isolated = [m for m in missing if m.category == "isolated"]
        assert len(isolated) == 1
        assert isolated[0].temp == 8
        assert isolated[0].vna_power == 30
        assert isolated[0].laser_power == 1

        # 10K/-30dBm/* → block (连续3个)
        blocks = [m for m in missing if m.category == "block"]
        assert len(blocks) == 3

    def test_edge_temperature_classified_as_edge(self, tmp_path):
        """温度边缘缺失标记为 edge"""
        data = tmp_path
        # 只建 8K 的数据，6K 和 10K 完全缺失 → edge
        for vna in [25, 30]:
            for laser in [0, 1]:
                d = data / "8K" / f"-{vna}dBm" / f"{laser:02d}mW"
                d.mkdir(parents=True)
                (d / "d.s2p").write_text("")

        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1]
        matrix = cc.build_completeness_matrix(data, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        edges = [m for m in missing if m.category == "edge"]
        for m in edges:
            assert m.temp in [6, 10]

    def test_complete_dataset_returns_empty(self, tmp_path):
        """完全完整的数据返回空缺失列表"""
        for temp in [6, 8]:
            for vna in [25, 30]:
                for laser in [0, 1]:
                    d = tmp_path / f"{temp}K" / f"-{vna}dBm" / f"{laser:02d}mW"
                    d.mkdir(parents=True)
                    (d / "d.s2p").write_text("")

        temps = [6, 8]
        vna_powers = [25, 30]
        laser_powers = [0, 1]
        matrix = cc.build_completeness_matrix(tmp_path, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        assert len(missing) == 0
