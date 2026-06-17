# -*- coding: utf-8 -*-
"""
Claude Code 侧实验监控脚本

用法:
  python claude_monitor.py --dir DIR --check      # 状态摘要
  python claude_monitor.py --dir DIR --report     # Markdown 进度表
  python claude_monitor.py --dir DIR --intervene   # 分析并写入 commands.json
  python claude_monitor.py --dir DIR --fill-plan   # 生成 fill_plan.json

由 Claude Code 通过 Bash 工具调用，输出直接显示在终端。
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import List, Set

# Windows GBK 控制台兼容：强制 stdout/stderr 使用 utf-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保能找到同目录模块
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from experiment_status import ExperimentStatusReader
from fill_planner import scan_s2p_files, compute_missing, generate_fill_plan


# =========================================================================
# 纯逻辑：决策规则
# =========================================================================

def analyze_for_intervention(issues: list, skipped_list: list,
                             existing_actions: set) -> list:
    """分析异常列表，返回应执行的干预命令。

    Args:
        issues: status.json 中的 issues 列表
        skipped_list: status.json 中的 skipped 列表
        existing_actions: commands.json 中已存在的 pending/applied action 名集合

    Returns:
        [{"action": ..., "params": {...}, "reason": "..."}, ...]
    """
    commands = []

    # 规则1：连续2次超时 → 延长 max_wait
    timeout_temps = [
        i["target_k"] for i in issues
        if i["type"] in ("timeout", "timeout_hard_fail")
    ]
    # 按温度点去重计数
    unique_timeout_temps = len(set(timeout_temps))
    if unique_timeout_temps >= 2 and "extend_max_wait" not in existing_actions:
        commands.append({
            "action": "extend_max_wait",
            "params": {"add_minutes": 30},
            "reason": f"连续 {unique_timeout_temps} 个温度点超时，增加等待时间",
        })

    # 规则2：同一温度点熔断 >=2 次 → 放宽熔断阈值
    meltdown_temps = [
        i["target_k"] for i in issues
        if i["type"] == "meltdown"
    ]
    meltdown_counts = Counter(meltdown_temps)
    for temp_k, count in meltdown_counts.items():
        if count >= 2 and "relax_meltdown" not in existing_actions:
            commands.append({
                "action": "relax_meltdown",
                "params": {"new_threshold_k": 0.35, "target_k": temp_k},
                "reason": f"{temp_k}K 已熔断 {count} 次，临时放宽阈值至 0.35K",
            })
            break  # 一条命令即可

    return commands


# =========================================================================
# CLI 子命令
# =========================================================================

def _read_status(output_dir: str) -> dict | None:
    """读取 status.json，失败时打印错误到 stderr。"""
    reader = ExperimentStatusReader(output_dir)
    status = reader.read()
    if status is None:
        print(f"[错误] {output_dir} 中未找到 status.json", file=sys.stderr)
        return None
    return status


def _load_existing_actions(output_dir: str) -> Set[str]:
    """读取 commands.json 中已存在的 action 名。"""
    cmd_path = os.path.join(output_dir, "commands.json")
    if not os.path.exists(cmd_path):
        return set()
    try:
        with open(cmd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {c["action"] for c in data.get("commands", [])}
    except (json.JSONDecodeError, OSError):
        return set()


def _write_commands(output_dir: str, new_commands: list):
    """将新命令写入 commands.json（追加到已有命令列表）。"""
    cmd_path = os.path.join(output_dir, "commands.json")
    existing = {"commands": [], "last_command_id": ""}

    if os.path.exists(cmd_path):
        try:
            with open(cmd_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    next_id = len(existing["commands"]) + 1
    for cmd in new_commands:
        cmd["id"] = f"cmd_{next_id:03d}"
        cmd["time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        cmd["status"] = "pending"
        existing["commands"].append(cmd)
        next_id += 1

    if existing["commands"]:
        existing["last_command_id"] = existing["commands"][-1]["id"]

    os.makedirs(output_dir, exist_ok=True)
    with open(cmd_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _cmd_check(output_dir: str):
    """--check: 打印状态摘要。"""
    status = _read_status(output_dir)
    if status is None:
        sys.exit(1)

    curr = status.get("current", {})
    phase_labels = {
        "stabilizing_sparse": "稳定中 (sparse)",
        "stabilizing_fine": "稳定中 (fine)",
        "pre_measuring": "预测量等待",
        "measuring": "测量中",
        "meltdown_recovery": "熔断恢复",
    }
    phase_cn = phase_labels.get(curr.get("phase", ""), curr.get("phase", "?"))

    print(f"📡 实验 {status['experiment_id']}")
    print(f"   状态: {status['status']}")
    print(f"   当前: {curr.get('target_k', '?')}K | "
          f"{curr.get('vna_dbm', '?')}dBm | {curr.get('laser_mw', '?')}mW")
    print(f"   阶段: {phase_cn}")
    print(f"   已完成: {len(status.get('completed', []))} 组测量")
    print(f"   异常: {len(status.get('issues', []))} 条")
    print(f"   跳过: {len(status.get('skipped', []))} 条")

    # 若有跳过，列出详情
    skipped = status.get("skipped", [])
    if skipped:
        print(f"   跳过详情:")
        for s in skipped:
            print(f"     - {s['target_k']}K: {s['reason']}")


def _cmd_report(output_dir: str):
    """--report: 打印 Markdown 格式进度表。"""
    status = _read_status(output_dir)
    if status is None:
        sys.exit(1)

    temps = status.get("temperature_plan", [])
    vnas = status.get("vna_power_plan", [])
    completed = status.get("completed", [])
    skipped = status.get("skipped", [])

    # 构建完成映射: {(target_k, vna_dbm): set(power_mw)}
    done_map = {}
    for c in completed:
        key = (c["target_k"], c["vna_dbm"])
        done_map.setdefault(key, set()).add(c["power_mw"])

    # 被完全跳过的温度点
    skipped_temps = {s["target_k"] for s in skipped}

    print(f"## 📊 实验 {status['experiment_id']} 进度报告")
    print()
    print(f"| 温度点 | VNA 功率 | 状态 | 已完成功率数 | 备注 |")
    print(f"|--------|---------|------|-------------|------|")

    for t in temps:
        if t in skipped_temps:
            skip_info = next((s for s in skipped if s["target_k"] == t), {})
            print(f"| **{t}K** | — | ❌ 跳过 | — | {skip_info.get('reason', '')} |")
            continue

        for v in vnas:
            key = (t, v)
            powers_done = done_map.get(key, set())
            expected_count = len(status.get("laser_power_plan", []))

            if len(powers_done) == expected_count and expected_count > 0:
                emoji, label = "✅", "完成"
                note = ""
            elif len(powers_done) > 0:
                emoji, label = "⚠️", "部分"
                note = f"已测 {len(powers_done)}/{expected_count}"
            else:
                emoji, label = "❌", "缺失"
                note = "未开始"

            print(f"| {t}K | {v:+d} dBm | {emoji} {label} | "
                  f"{len(powers_done)}/{expected_count} | {note} |")

    total_expected = len(temps) * len(vnas) * len(status.get("laser_power_plan", []))
    total_done = len(completed)
    print()
    print(f"**总进度: {total_done}/{total_expected} ({total_done * 100 // max(total_expected, 1)}%)**")


def _cmd_intervene(output_dir: str):
    """--intervene: 分析状态，写入 commands.json。"""
    status = _read_status(output_dir)
    if status is None:
        sys.exit(1)

    issues = status.get("issues", [])
    skipped_list = status.get("skipped", [])
    existing_actions = _load_existing_actions(output_dir)

    commands = analyze_for_intervention(issues, skipped_list, existing_actions)

    if not commands:
        print("✅ 无需干预，实验状态正常。")
        return

    _write_commands(output_dir, commands)
    for cmd in commands:
        print(f"⚠️ 已写入命令: {cmd['action']} — {cmd['reason']}")


def _cmd_fill_plan(output_dir: str):
    """--fill-plan: 分析缺失数据，生成补测计划。"""
    status = _read_status(output_dir)
    if status is None:
        sys.exit(1)

    # 从 status 获取期望列表
    temp_plan = status.get("temperature_plan", [])
    vna_plan = status.get("vna_power_plan", [])
    laser_plan = status.get("laser_power_plan", [])

    # 从 status 的 completed 中提取已完成
    completed = status.get("completed", [])
    actual_set = set()
    for c in completed:
        for pw in c.get("powers_mw", []):
            actual_set.add((c["target_k"], c["vna_dbm"], pw))

    # 也扫描文件系统（优先 status，补充文件系统）
    scanned = scan_s2p_files(output_dir)
    for s in scanned:
        actual_set.add((s["target_k"], s["vna_dbm"], s["power_mw"]))

    expected = []
    for t in temp_plan:
        for v in vna_plan:
            for p in laser_plan:
                expected.append((t, v, p))

    missing = compute_missing(expected, list(actual_set))

    if not missing:
        print("✅ 数据完整，无需补测。")
        return

    print(f"🔍 缺失 {len(missing)} 个测量点:")

    # 按温度+VNA分组展示
    groups: dict[tuple, list] = {}
    for t, v, p in missing:
        groups.setdefault((t, v), []).append(p)

    for (t, v), powers in sorted(groups.items()):
        print(f"   {t}K  {v:+d} dBm  缺 {len(powers)} 个激光功率: {sorted(powers)}")

    # 生成补测计划
    import config
    plan_path = generate_fill_plan(
        missing=missing,
        experiment_id=status["experiment_id"],
        output_dir=output_dir,
        cooldown_offset_k=config.fill_cooldown_offset_k,
    )

    if plan_path:
        print(f"\n📋 补测计划已写入: {plan_path}")
        print(f"   预计耗时: ~{len(missing) * 2} 分钟")
        # 打印补测计划概要
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        print(f"   温度点: {plan['temperature_plan']}")
        print(f"   策略: {plan['strategy']} (冷却至 target-{plan['cooldown_offset_k']}K)")


# =========================================================================
# CLI 入口
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code 实验监控脚本",
    )
    parser.add_argument("--dir", type=str, required=True,
                        help="实验输出目录路径")
    parser.add_argument("--check", action="store_true",
                        help="状态摘要")
    parser.add_argument("--report", action="store_true",
                        help="Markdown 进度表")
    parser.add_argument("--intervene", action="store_true",
                        help="分析并写入干预命令")
    parser.add_argument("--fill-plan", action="store_true",
                        dest="fill_plan",
                        help="分析缺失并生成补测计划")

    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"[错误] 目录不存在: {args.dir}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        _cmd_check(args.dir)
    elif args.report:
        _cmd_report(args.dir)
    elif args.intervene:
        _cmd_intervene(args.dir)
    elif args.fill_plan:
        _cmd_fill_plan(args.dir)
    else:
        # 默认行为：等同于 --check
        _cmd_check(args.dir)


if __name__ == "__main__":
    main()
