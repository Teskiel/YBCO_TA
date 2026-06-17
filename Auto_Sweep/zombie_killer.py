# -*- coding: utf-8 -*-
"""
后台僵尸进程清理工具。

Bun runtime 崩溃后，subprocess 启动的 Python 进程可能泄漏。
此工具输出 PowerShell 命令到 stdout，由 Claude Code 通过 Bash 执行。

用法:
  python zombie_killer.py               # 输出扫描 + 终止的 PS 命令
  python zombie_killer.py --dry-run     # 仅扫描，不终止
  python zombie_killer.py --execute     # 直接通过 Bash 执行清理

设计: 因为 Bun 沙箱限制了 Python subprocess 对 PowerShell 的调用，
所有的进程操作通过 Bash 工具执行 PS 命令。
"""

import argparse
import sys

# PS 扫描命令
SCAN_SCRIPT = r"""
Write-Host '--- Python 进程扫描 ---'
Get-CimInstance Win32_Process -Filter "Name LIKE '%python%'" |
    ForEach-Object {
        $parentName = try { (Get-Process -Id $_.ParentProcessId -EA 0).ProcessName }
                      catch { '<gone>' }
        $isZombie = ($_.WorkingSetSize/1MB -gt 80) -and ($_.Name -notlike '*pythonw*')
        $marker = if ($isZombie) { '[ZOMBIE]' } else { '[OK]' }
        Write-Host ("{0} PID={1} Parent={2}({3}) Mem={4:F1}MB" -f
            $marker, $_.ProcessId, $_.ParentProcessId, $parentName,
            ($_.WorkingSetSize/1MB))
    }
"""

# PS 终止命令（终止高内存的 python.exe，排除 pythonw）
KILL_SCRIPT = r"""
$zombies = Get-CimInstance Win32_Process -Filter "Name LIKE '%python%'" |
    Where-Object {
        ($_.WorkingSetSize/1MB -gt 80) -and ($_.Name -notlike '*pythonw*')
    }
if (-not $zombies) {
    Write-Host 'No zombie processes found.'
    exit 0
}
$totalMem = ($zombies | Measure-Object -Property WorkingSetSize -Sum).Sum / 1MB
Write-Host ("Found {0} zombie(s), total {1:F0} MB" -f @($zombies).Count, $totalMem)
foreach ($z in $zombies) {
    Write-Host ("  Killing PID {0} ({1:F0} MB)..." -f $z.ProcessId, ($z.WorkingSetSize/1MB))
    $r = (Get-WmiObject Win32_Process -Filter "ProcessId=$($z.ProcessId)").Terminate()
    Write-Host ("    ReturnValue={0}" -f $r.ReturnValue)
}
Write-Host 'Done.'
"""


def main():
    parser = argparse.ArgumentParser(
        description="清理 Bun 崩溃残留的僵尸 Python 进程")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅扫描，不终止")
    parser.add_argument("--execute", action="store_true",
                        help="直接通过 Bash 执行清理")
    args = parser.parse_args()

    if args.execute:
        # 扫描 + 终止
        print(SCAN_SCRIPT.strip())
        print(KILL_SCRIPT.strip())
    elif args.dry_run:
        # 仅扫描
        print(SCAN_SCRIPT.strip())
    else:
        # 默认: 输出扫描 + 终止
        print(SCAN_SCRIPT.strip())
        print(KILL_SCRIPT.strip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
