# -*- coding: utf-8 -*-
"""experiment_merger.py 单元测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import experiment_merger as em


@pytest.fixture
def mock_two_fragments(tmp_path):
    """
    创建两个模拟碎片文件夹：
    frag1 (20260611): 6K 有 2 s2p (不完整), 8K 有 1 s2p
    frag2 (20260612): 6K 有 4 s2p (完整), 8K 有 4 s2p
    预期 most_complete 策略选中 frag2 的文件
    """
    frag1 = tmp_path / "20260611"
    frag2 = tmp_path / "20260612"

    # frag1: 6K 不完整 (只有 -25dBm 下 00mW 和 01mW)
    for laser in ["00mW", "01mW"]:
        d = frag1 / "6K" / "-25dBm" / laser
        d.mkdir(parents=True)
        (d / "frag1_6K.s2p").write_text("frag1")

    # frag1: 8K 只有 1 个文件
    (frag1 / "8K" / "-25dBm" / "00mW").mkdir(parents=True)
    (frag1 / "8K" / "-25dBm" / "00mW" / "frag1_8K.s2p").write_text("frag1")

    # frag2: 6K 和 8K 各 4 文件 (2 VNA × 2 laser)
    for temp in ["6K", "8K"]:
        for vna in ["-25dBm", "-30dBm"]:
            for laser in ["00mW", "01mW"]:
                d = frag2 / temp / vna / laser
                d.mkdir(parents=True)
                (d / f"frag2_{temp}_{vna}_{laser}.s2p").write_text("frag2")

    return [frag1, frag2]


class TestScanFragments:
    """scan_fragments() 测试"""

    def test_finds_all_unique_combos(self, mock_two_fragments):
        """找到所有唯一的 (T, VNA, laser) 组合"""
        index = em.scan_fragments(mock_two_fragments)
        # 6K/-25dBm/00mW: frag1 + frag2 = 2
        # 6K/-25dBm/01mW: frag1 + frag2 = 2
        # 6K/-30dBm/00mW: frag2 only = 1
        # 6K/-30dBm/01mW: frag2 only = 1
        # 8K/-25dBm/00mW: frag1 + frag2 = 2
        # 8K/-25dBm/01mW: frag2 only = 1
        # 8K/-30dBm/00mW: frag2 only = 1
        # 8K/-30dBm/01mW: frag2 only = 1
        assert len(index) == 8
        assert len(index[(6, 25, 0)]) == 2  # 两个片段都有
        assert len(index[(6, 30, 0)]) == 1  # 仅 frag2

    def test_ignores_logs_and_discarded(self, tmp_path):
        """忽略 logs/ 和 discarded/ 目录"""
        frag = tmp_path / "frag"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "data.s2p").write_text("")
        (frag / "6K" / "logs").mkdir(parents=True)
        (frag / "6K" / "discarded").mkdir(parents=True)
        # 在 logs/ 和 discarded/ 下不应被扫描
        (frag / "6K" / "logs" / "ignored.s2p").write_text("")

        index = em.scan_fragments([frag])
        assert len(index) == 1
        assert (6, 25, 0) in index
        assert len(index[(6, 25, 0)]) == 1  # 仅 data.s2p, 不含 ignored.s2p

    def test_empty_input_returns_empty_index(self):
        """空输入列表返回空索引"""
        index = em.scan_fragments([])
        assert index == {}

    def test_non_existent_dir_skipped(self, tmp_path):
        """不存在的目录被跳过"""
        frag = tmp_path / "exists"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "d.s2p").write_text("")
        non_exist = tmp_path / "nope"

        index = em.scan_fragments([frag, non_exist])
        assert len(index) == 1

    def test_empty_fragment_dir(self, tmp_path):
        """空的碎片目录返回空索引"""
        frag = tmp_path / "empty_frag"
        frag.mkdir()
        index = em.scan_fragments([frag])
        assert index == {}


class TestResolveConflicts:
    """resolve_conflicts() 测试"""

    def test_most_complete_picks_larger_fragment(self, mock_two_fragments):
        """重叠温度选 S2P 总数更多的片段"""
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, strategy="most_complete")

        # 6K: frag1 有 2 s2p, frag2 有 4 s2p → 应选 frag2
        for key in [(6, 25, 0), (6, 25, 1)]:
            assert plan.mapping[key].fragment_dir == mock_two_fragments[1]

        # 8K/-25dBm/00mW: frag1 有 1 s2p(全在8K), frag2 有 4 s2p → 应选 frag2
        assert plan.mapping[(8, 25, 0)].fragment_dir == mock_two_fragments[1]

        # 确认冲突被记录
        overlapping_keys = {(6, 25, 0), (6, 25, 1), (8, 25, 0)}
        assert set(plan.conflicts) == overlapping_keys

    def test_single_fragment_no_conflicts(self, tmp_path):
        """单一片段无冲突"""
        frag = tmp_path / "frag"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "d.s2p").write_text("")

        index = em.scan_fragments([frag])
        plan = em.resolve_conflicts(index, strategy="most_complete")

        assert len(plan.conflicts) == 0
        assert len(plan.mapping) == 1
