# -*- coding: utf-8 -*-
"""
实验数据完整性检查器。

分析合并后的数据目录，生成完整性报告和补测建议清单。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import numpy as np


@dataclass
class MissingPoint:
    """单个缺失数据点"""
    temp: int
    vna_power: int       # 正值, 如 25 表示 -25dBm
    laser_power: int
    category: str        # "isolated" | "edge" | "block"


def build_completeness_matrix(
    data_dir: Path,
    temps: List[int],
    vna_powers: List[int],    # 正值, 如 25 表示 -25dBm
    laser_powers: List[int],
) -> np.ndarray:
    """
    构建完整性矩阵。

    遍历 data_dir/{temp}K/-{vna}dBm/{laser:02d}mW/，
    检查是否存在至少一个 .s2p 文件。
    返回 shape (len(temps), len(vna_powers), len(laser_powers)) 的 bool 数组。
    """
    n_t, n_v, n_l = len(temps), len(vna_powers), len(laser_powers)
    matrix = np.zeros((n_t, n_v, n_l), dtype=bool)

    for ti, temp in enumerate(temps):
        temp_dir = data_dir / f"{temp}K"
        if not temp_dir.is_dir():
            continue
        for vi, vna in enumerate(vna_powers):
            vna_dir = temp_dir / f"-{vna}dBm"
            if not vna_dir.is_dir():
                continue
            for li, laser in enumerate(laser_powers):
                laser_dir = vna_dir / f"{laser:02d}mW"
                if laser_dir.is_dir() and list(laser_dir.glob("*.s2p")):
                    matrix[ti, vi, li] = True

    return matrix


def _is_edge(ti: int, num_temps: int) -> bool:
    """温度索引是否在边缘 (首/尾)"""
    return ti == 0 or ti == num_temps - 1


def _is_laser_edge(li: int, num_lasers: int) -> bool:
    """激光功率索引是否在边缘 (首/尾)"""
    return li == 0 or li == num_lasers - 1


def _group_consecutive(indices: List[int]) -> List[List[int]]:
    """将索引列表按连续性分组"""
    if not indices:
        return []
    groups = []
    group = [indices[0]]
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            group.append(indices[i])
        else:
            groups.append(group)
            group = [indices[i]]
    groups.append(group)
    return groups


def diagnose_missing(
    matrix: np.ndarray,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
) -> List[MissingPoint]:
    """
    分类缺失原因 (双维度扫描 + 优先级合并):
    - "block"    — 同一 (vna, laser) 沿温度轴连续缺失 >=3 个,
                    或同一 (temp, vna) 沿激光轴连续缺失 >=3 个
    - "edge"     — 温度边缘缺失 (首/尾温度)
    - "isolated" — 孤立偶发缺失
    优先级: block > edge > isolated
    """
    n_t, n_v, n_l = matrix.shape
    # 用字典累积每个缺失格子的最佳分类
    best: dict[tuple, str] = {}

    def _set(ti: int, vi: int, li: int, cat: str):
        key = (ti, vi, li)
        order = {"block": 3, "edge": 2, "isolated": 1}
        if key not in best or order[cat] > order[best[key]]:
            best[key] = cat

    # 维度1: 沿温度轴 — 对每个 (vna, laser) 扫描
    for vi in range(n_v):
        for li in range(n_l):
            missing_tis = [ti for ti in range(n_t) if not matrix[ti, vi, li]]
            for g in _group_consecutive(missing_tis):
                if len(g) >= 3:
                    cat = "block"
                elif _is_edge(g[0], n_t):
                    cat = "edge"
                else:
                    cat = "isolated"
                for ti in g:
                    _set(ti, vi, li, cat)

    # 维度2: 沿激光轴 — 对每个 (temp, vna) 扫描
    for ti in range(n_t):
        for vi in range(n_v):
            missing_lis = [li for li in range(n_l) if not matrix[ti, vi, li]]
            for g in _group_consecutive(missing_lis):
                if len(g) >= 3:
                    cat = "block"
                elif _is_laser_edge(g[0], n_l):
                    cat = "edge"
                else:
                    cat = "isolated"
                for li in g:
                    _set(ti, vi, li, cat)

    # 构建 MissingPoint 列表
    missing: List[MissingPoint] = []
    for (ti, vi, li), cat in best.items():
        missing.append(MissingPoint(
            temp=temps[ti],
            vna_power=vna_powers[vi],
            laser_power=laser_powers[li],
            category=cat,
        ))

    return missing


@dataclass
class RetestPlan:
    """补测计划"""
    temps: List[int]
    vna_powers: List[int]       # 负值 (原始 VNA 功率)
    laser_powers: List[int]
    missing_combos: List[dict]


@dataclass
class CompletenessReport:
    """完整性分析报告"""
    expected: int
    found: int
    missing: int
    missing_breakdown: Dict[str, int]
    details: List[dict]
    retest_plan: RetestPlan


def generate_retest_plan(missing: List[MissingPoint]) -> RetestPlan:
    """从缺失列表生成补测计划，按温度→VNA功率→激光功率排序"""
    if not missing:
        return RetestPlan(temps=[], vna_powers=[], laser_powers=[], missing_combos=[])

    temps = sorted(set(m.temp for m in missing))
    vna_powers_pos = sorted(set(m.vna_power for m in missing))
    laser_powers = sorted(set(m.laser_power for m in missing))

    missing_combos = [
        {"temp": m.temp, "vna_power": -m.vna_power, "laser_power": m.laser_power}
        for m in sorted(missing, key=lambda m: (m.temp, m.vna_power, m.laser_power))
    ]

    return RetestPlan(
        temps=temps,
        vna_powers=[-v for v in vna_powers_pos],
        laser_powers=laser_powers,
        missing_combos=missing_combos,
    )


def build_report(
    matrix: np.ndarray,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
    missing: List[MissingPoint],
) -> CompletenessReport:
    """组装完整报告"""
    n_expected = len(temps) * len(vna_powers) * len(laser_powers)
    n_found = int(matrix.sum())

    breakdown: Dict[str, int] = {"isolated": 0, "edge": 0, "block": 0}
    for m in missing:
        breakdown[m.category] += 1

    details = [
        {
            "temp": m.temp,
            "vna_power": -m.vna_power,
            "laser_power": m.laser_power,
            "status": "missing",
            "category": m.category,
        }
        for m in sorted(missing, key=lambda m: (m.temp, m.vna_power, m.laser_power))
    ]

    return CompletenessReport(
        expected=n_expected,
        found=n_found,
        missing=n_expected - n_found,
        missing_breakdown=breakdown,
        details=details,
        retest_plan=generate_retest_plan(missing),
    )


def format_report_json(report: CompletenessReport) -> str:
    """JSON 格式输出"""
    import json
    return json.dumps({
        "summary": {
            "expected": report.expected,
            "found": report.found,
            "missing": report.missing,
            "missing_breakdown": report.missing_breakdown,
        },
        "retest_plan": {
            "temps": report.retest_plan.temps,
            "vna_powers": report.retest_plan.vna_powers,
            "laser_powers": report.retest_plan.laser_powers,
            "missing_combos": report.retest_plan.missing_combos,
        },
        "details": report.details,
    }, indent=2, ensure_ascii=False)


def format_report_table(
    report: CompletenessReport,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
    matrix: np.ndarray,
) -> str:
    """表格格式输出"""
    lines = []
    lines.append(f"{'Temperature':<13} {'VNA Power':<11} {'Laser Power':<13} Status")
    lines.append("-" * 58)

    for ti, temp in enumerate(temps):
        for vi, vna in enumerate(vna_powers):
            for li, laser in enumerate(laser_powers):
                if matrix[ti, vi, li]:
                    status = "✓"
                else:
                    cat = next(
                        (d["category"] for d in report.details
                         if d["temp"] == temp and d["vna_power"] == -vna
                         and d["laser_power"] == laser),
                        "unknown"
                    )
                    status = f"✗ (missing — {cat})"
                lines.append(
                    f"{temp}K           -{vna}dBm      {laser:02d}mW         {status}"
                )

    lines.append("-" * 58)
    lines.append(
        f"Summary: {report.expected} expected, {report.found} found, "
        f"{report.missing} missing"
    )
    cats = ", ".join(f"{k}: {v}" for k, v in report.missing_breakdown.items())
    lines.append(f"Missing: {cats}")
    if report.retest_plan.temps:
        lines.append(
            f"Suggested retest: {len(report.retest_plan.temps)} temperature points"
        )

    return "\n".join(lines)


def main():
    """命令行入口：实验数据完整性检查器"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="分析合并后数据目录的完整性，生成补测建议")
    parser.add_argument("--input", type=Path, required=True,
                        help="合并后的数据目录")
    parser.add_argument("--temps-start", type=int, required=True,
                        help="起始温度 (K)")
    parser.add_argument("--temps-stop", type=int, required=True,
                        help="终止温度 (K)")
    parser.add_argument("--temps-step", type=int, required=True,
                        help="温度步长 (K)")
    parser.add_argument("--vna-powers", type=str, default="-25,-30,-45",
                        help="VNA 功率列表 (默认: -25,-30,-45)")
    parser.add_argument("--laser-powers", type=str, default="0,1,3,5,7,9",
                        help="激光功率列表 (默认: 0,1,3,5,7,9)")
    parser.add_argument("--format", choices=["json", "table"],
                        default="table", help="输出格式 (默认: table)")
    parser.add_argument("--output", type=Path,
                        help="输出文件路径 (默认: stdout)")

    args = parser.parse_args()

    temps = list(range(args.temps_start, args.temps_stop + 1, args.temps_step))
    vna_powers = [abs(int(x.strip())) for x in args.vna_powers.split(",")]
    laser_powers = [int(x.strip()) for x in args.laser_powers.split(",")]

    if not args.input.is_dir():
        print(f"错误: 目录不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    matrix = build_completeness_matrix(args.input, temps, vna_powers, laser_powers)
    missing = diagnose_missing(matrix, temps, vna_powers, laser_powers)
    report = build_report(matrix, temps, vna_powers, laser_powers, missing)

    if args.format == "json":
        output = format_report_json(report)
    else:
        output = format_report_table(report, temps, vna_powers, laser_powers, matrix)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"报告已写入 {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
