# -*- coding: utf-8 -*-
"""
实验数据整合工具 — 扫描、分组、去重、清理、合并

Usage:
    python consolidate.py              # 交互模式
    python consolidate.py --dry-run    # 预览，不执行
    python consolidate.py --yes        # 跳过确认，自动执行
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# =========================================================================
# Data types
# =========================================================================

@dataclass
class S2PFile:
    """单个 .s2p 文件的解析信息。"""
    path: str           # 相对于 run 根目录的路径
    vna_dbm: float
    laser_mw: float
    target_k: float
    actual_k: float
    mtime: float = 0.0  # 文件修改时间（用于冲突裁决）


@dataclass
class RunInfo:
    """一个实验运行目录的扫描结果。"""
    id: str                          # 目录名
    path: str                        # 完整路径
    params_hash: str = ""            # (sorted Pv, sorted Pl) 的 SHA256 前 12 位
    target_temps: set = field(default_factory=set)
    s2p_count: int = 0
    timestamp: Optional[datetime] = None
    has_manifest: bool = False
    has_status: bool = False
    s2p_files: list = field(default_factory=list)
    vna_power_plan: list = field(default_factory=list)
    laser_power_plan: list = field(default_factory=list)


# =========================================================================
# S2P filename parsing
# =========================================================================

_S2P_RE = re.compile(
    r"YBCO_(-?\d+)dBm_(\d+)mW_target_([\d.]+)K_actual_([\d.]+)K\.s2p$"
)


def parse_s2p_filename(filename: str) -> Optional[S2PFile]:
    """Parse an s2p filename into its measurement parameters.

    Returns None if the filename doesn't match the expected pattern.
    """
    m = _S2P_RE.match(filename)
    if not m:
        return None
    return S2PFile(
        path="",  # caller fills in
        vna_dbm=float(m.group(1)),
        laser_mw=float(m.group(2)),
        target_k=float(m.group(3)),
        actual_k=float(m.group(4)),
    )


# =========================================================================
# Special directories to skip during scanning
# =========================================================================

SKIP_DIRS = {"~merged", "_junk", "_fragments", "_archive"}


# =========================================================================
# Parameter extraction
# =========================================================================

def _make_params_hash(vna_power_plan: list, laser_power_plan: list) -> str:
    """Deterministic hash of (sorted Pv, sorted Pl) for grouping."""
    payload = json.dumps([
        sorted(vna_power_plan),
        sorted(laser_power_plan),
    ], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def scan_run(dir_path: str) -> Optional[RunInfo]:
    """Scan a single experiment output directory and extract its parameters.

    Parameter sources (priority order):
      1. manifest.json
      2. status.json or checkpoint.json
      3. Infer from directory structure (walk .s2p files)

    Returns None if the directory should be skipped (special dirs).
    """
    dir_name = os.path.basename(dir_path)

    # Skip special directories
    if dir_name in SKIP_DIRS:
        return None

    # Check for already-consolidated marker
    for fname in os.listdir(dir_path):
        if fname.endswith(".txt") and "__" in fname and "pts" in fname:
            return None  # already consolidated

    info = RunInfo(id=dir_name, path=dir_path)

    # --- Step 1: Try manifest.json ---
    manifest_path = os.path.join(dir_path, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            info.has_manifest = True
            info.vna_power_plan = m.get("vna_power_plan", [])
            info.laser_power_plan = m.get("laser_power_plan", [])
            info.target_temps = set(m.get("temperature_plan", []))
            info.params_hash = _make_params_hash(
                info.vna_power_plan, info.laser_power_plan)
            ts = m.get("start_time", "")
            if ts:
                try:
                    info.timestamp = datetime.fromisoformat(ts)
                except ValueError:
                    pass
        except (json.JSONDecodeError, OSError):
            pass

    # --- Step 2: Try status.json ---
    if not info.has_manifest:
        status_path = os.path.join(dir_path, "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                info.has_status = True
                info.vna_power_plan = s.get("vna_power_plan", [])
                info.laser_power_plan = s.get("laser_power_plan", [])
                info.target_temps = set(s.get("temperature_plan", []))
                info.params_hash = _make_params_hash(
                    info.vna_power_plan, info.laser_power_plan)
                ts = s.get("start_time", "")
                if ts:
                    try:
                        info.timestamp = datetime.fromisoformat(ts)
                    except ValueError:
                        pass
            except (json.JSONDecodeError, OSError):
                pass

    # --- Step 2b: Try checkpoint.json (if status didn't have plans) ---
    if not info.has_manifest and not info.has_status:
        ckpt_path = os.path.join(dir_path, "checkpoint.json")
        if os.path.exists(ckpt_path):
            try:
                with open(ckpt_path, "r", encoding="utf-8") as f:
                    c = json.load(f)
                info.vna_power_plan = c.get("original_vna_power_list", [])
                info.laser_power_plan = c.get("original_power_list", [])
                info.target_temps = set(c.get("original_temp_list", []))
                info.params_hash = _make_params_hash(
                    info.vna_power_plan, info.laser_power_plan)
                ts = c.get("timestamp", "")
                if ts:
                    try:
                        info.timestamp = datetime.fromisoformat(ts)
                    except ValueError:
                        pass
            except (json.JSONDecodeError, OSError):
                pass

    # --- Step 3: Walk s2p files ---
    s2p_files = []
    target_temps_from_files = set()
    vna_powers = set()
    laser_powers = set()
    for root, dirs, files in os.walk(dir_path):
        for fname in files:
            if not fname.endswith(".s2p"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, dir_path)
            parsed = parse_s2p_filename(fname)
            if parsed is None:
                continue
            parsed.path = rel_path
            parsed.mtime = os.path.getmtime(full_path)
            s2p_files.append(parsed)
            target_temps_from_files.add(parsed.target_k)
            vna_powers.add(parsed.vna_dbm)
            laser_powers.add(parsed.laser_mw)

    info.s2p_files = s2p_files
    info.s2p_count = len(s2p_files)

    # --- Step 4: Infer from directory structure if metadata was missing ---
    if not info.has_manifest and not info.has_status and not info.params_hash:
        if vna_powers and laser_powers:
            info.vna_power_plan = sorted(vna_powers)
            info.laser_power_plan = sorted(laser_powers)
            info.params_hash = _make_params_hash(
                info.vna_power_plan, info.laser_power_plan)

    if target_temps_from_files:
        info.target_temps = target_temps_from_files

    # --- Step 5: Fallback timestamp from dir name ---
    if info.timestamp is None:
        # Try to parse YYYYMMDD_HHMMSS from directory name
        ts_match = re.match(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})",
                            dir_name)
        if ts_match:
            try:
                parts = [int(g) for g in ts_match.groups()]
                info.timestamp = datetime(*parts)
            except ValueError:
                pass

    return info
