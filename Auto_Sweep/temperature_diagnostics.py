# -*- coding: utf-8 -*-
"""
温度控制诊断模块 - Temperature Control Diagnostics
用于检测温度控制中的常见问题并提供解决方案
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from enum import Enum
import numpy as np


class ProblemType(Enum):
    """问题类型枚举"""
    OSCILLATION = "oscillation"              # 上下震荡
    SLOW_RESPONSE = "slow_response"         # 响应太慢
    DRIFT = "drift"                         # 持续漂移
    OVERSHOOT = "overshoot"                 # 超调
    UNDERSHOOT = "undershoot"               # 欠调
    NOISY = "noisy"                         # 噪声过大
    STABLE = "stable"                       # 稳定
    UNKNOWN = "unknown"                     # 未知


@dataclass
class DiagnosticResult:
    """诊断结果"""
    problem_type: ProblemType
    severity: str  # 'info', 'warning', 'critical'
    description: str
    details: Dict
    suggestions: List[str]


class TemperatureDiagnostics:
    """
    温度控制诊断器

    分析温度历史数据，检测常见问题并提供解决方案。
    """

    def __init__(self, history_window: int = 60):
        """
        Args:
            history_window: 用于分析的历史数据点数（每个点约10秒）
        """
        self.history_window = history_window

    def analyze(self, temperatures: List[float],
                times: Optional[List[float]] = None,
                target_temp: float = None) -> DiagnosticResult:
        """
        分析温度数据并返回诊断结果

        Args:
            temperatures: 温度历史数据
            times: 对应的时间戳（可选）
            target_temp: 目标温度（可选）

        Returns:
            DiagnosticResult: 诊断结果和建议
        """
        if len(temperatures) < 10:
            return DiagnosticResult(
                problem_type=ProblemType.UNKNOWN,
                severity='info',
                description="数据点不足，无法进行完整诊断",
                details={'data_points': len(temperatures)},
                suggestions=["等待更多数据后再诊断"]
            )

        # 执行各项检测
        oscillation_result = self._check_oscillation(temperatures)
        drift_result = self._check_drift(temperatures)
        noise_result = self._check_noise(temperatures)
        trend_result = self._check_trend(temperatures)

        # 综合判断最严重的问题
        problems = [oscillation_result, drift_result, noise_result, trend_result]
        problems = [p for p in problems if p is not None]

        if not problems:
            return DiagnosticResult(
                problem_type=ProblemType.STABLE,
                severity='info',
                description="温度控制正常，未检测到明显问题",
                details=self._get_basic_stats(temperatures),
                suggestions=["继续保持当前设置"]
            )

        # 找出最严重的问题
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        most_severe = min(problems, key=lambda x: severity_order.get(x[1], 3))

        return DiagnosticResult(
            problem_type=most_severe[0],
            severity=most_severe[1],
            description=most_severe[2],
            details=most_severe[3] if len(most_severe) > 3 else {},
            suggestions=most_severe[4] if len(most_severe) > 4 else []
        )

    def _get_basic_stats(self, temps: List[float]) -> Dict:
        """计算基本统计信息"""
        return {
            'mean': float(np.mean(temps)),
            'std': float(np.std(temps)),
            'min': float(np.min(temps)),
            'max': float(np.max(temps)),
            'range': float(np.max(temps) - np.min(temps)),
            'data_points': len(temps)
        }

    def _check_oscillation(self, temps: List[float]) -> Optional[Tuple]:
        """
        检测温度是否在设定点上下震荡

        震荡特征：
        - 温度曲线类似正弦波
        - 相邻温差符号交替
        - 周期性地高于和低于均值
        """
        if len(temps) < 20:
            return None

        temps_array = np.array(temps)

        # 方法1：检测相邻差分的符号变化
        diffs = np.diff(temps_array)
        sign_changes = np.sum(np.abs(np.diff(np.sign(diffs))))

        # 计算震荡频率（每分钟振荡次数）
        oscillation_rate = sign_changes / (len(temps) * 10 / 60)  # 假设每点10秒

        # 方法2：检测温度相对于均值的上下分布
        mean_temp = np.mean(temps_array)
        above_mean = temps_array > mean_temp
        above_changes = np.sum(np.abs(np.diff(np.sign(above_mean.astype(float)))))

        # 如果震荡明显
        if oscillation_rate > 0.3 and above_changes > len(temps) * 0.3:
            amplitude = (np.max(temps_array) - np.min(temps_array)) / 2

            return (
                ProblemType.OSCILLATION,
                'critical',
                f"检测到温度震荡！振幅约 {amplitude:.3f} K，振荡频率约 {oscillation_rate:.1f} 次/分钟",
                {
                    'amplitude': float(amplitude),
                    'oscillation_rate': float(oscillation_rate),
                    'sign_changes': int(sign_changes),
                    'mean': float(mean_temp)
                },
                self._get_oscillation_suggestions(amplitude, oscillation_rate)
            )

        return None

    def _get_oscillation_suggestions(self, amplitude: float, rate: float) -> List[str]:
        """针对震荡问题给出建议"""
        suggestions = []

        if amplitude > 0.5:
            suggestions.append("⚠️ 振幅过大！考虑减小P值（比例增益）")
            suggestions.append("   当前P值可能太高，导致过冲")
        elif amplitude > 0.2:
            suggestions.append("建议适当减小P值，减少过冲")

        if rate > 1.0:
            suggestions.append("⚠️ 震荡频率过高！考虑增加D值（微分增益）")
            suggestions.append("   微分项可以提前预测并抑制振荡")

        if amplitude > 0.2:
            suggestions.append("考虑启用主动抑制震荡的策略：")
            suggestions.append("   1. 暂时降低PID的P值50%")
            suggestions.append("   2. 等待3-5分钟让系统稳定")
            suggestions.append("   3. 逐步恢复P值，观察响应")

        if not suggestions:
            suggestions.append("轻微震荡，可观察暂不处理")

        return suggestions

    def _check_drift(self, temps: List[float]) -> Optional[Tuple]:
        """
        检测温度是否持续漂移

        漂移特征：
        - 温度呈现单调上升或下降趋势
        - 与设定点存在恒定偏差
        """
        if len(temps) < 15:
            return None

        temps_array = np.array(temps)

        # 线性拟合获取趋势
        x = np.arange(len(temps))
        slope, intercept = np.polyfit(x, temps_array, 1)

        # 计算趋势的严重程度（K/样本点）
        total_range = np.max(temps_array) - np.min(temps_array)

        # 判断：斜率方向一致，且整体变化明显
        if abs(slope) > 0.001:  # 每点变化超过0.001K
            direction = "上升" if slope > 0 else "下降"

            # 分类：慢漂移 vs 快漂移
            severity = 'warning' if abs(slope) < 0.01 else 'critical'

            # 计算预估的总漂移量（如果持续下去）
            estimated_total_drift = slope * 180  # 预估30分钟
            mean_temp = np.mean(temps_array)

            return (
                ProblemType.DRIFT,
                severity,
                f"检测到温度{direction}漂移！斜率: {slope*60:.4f} K/分钟",
                {
                    'slope_per_point': float(slope),
                    'slope_per_minute': float(slope * 60),
                    'direction': direction,
                    'estimated_30min_drift': float(estimated_total_drift),
                    'mean_temperature': float(mean_temp)
                },
                self._get_drift_suggestions(slope, direction)
            )

        return None

    def _get_drift_suggestions(self, slope: float, direction: str) -> List[str]:
        """针对漂移问题给出建议"""
        suggestions = []

        if direction == "上升" and slope > 0:
            if slope > 0.005:
                suggestions.append("⚠️ 温度持续上升，可能加热过度！")
                suggestions.append("   检查：1. 冷却系统是否正常工作")
                suggestions.append("        2. 温度传感器位置是否正确")
            suggestions.append("建议增加I值（积分增益）来消除稳态误差")
            suggestions.append("或检查是否存在外部热源干扰")
        else:
            if slope < -0.005:
                suggestions.append("⚠️ 温度持续下降，可能加热不足！")
                suggestions.append("   检查：1. 加热器是否正常工作")
                suggestions.append("        2. 杜瓦是否需要补充制冷剂")
            suggestions.append("建议适当增加P值或I值")

        suggestions.append("如果漂移缓慢且趋于稳定，可暂时观察")

        return suggestions

    def _check_noise(self, temps: List[float]) -> Optional[Tuple]:
        """
        检测测量噪声是否过大

        噪声特征：
        - 温度数据杂乱无章
        - 标准差相对于均值较大
        - 短时间内的快速变化
        """
        if len(temps) < 10:
            return None

        temps_array = np.array(temps)

        # 计算标准差
        std = np.std(temps_array)

        # 计算短期变化（相邻点的最大差值）
        diffs = np.abs(np.diff(temps_array))
        max_jump = np.max(diffs)
        mean_jump = np.mean(diffs)

        # 判断噪声水平
        if std > 0.05:  # 标准差大于50mK
            return (
                ProblemType.NOISY,
                'warning',
                f"检测到测量噪声过大！标准差: {std:.4f} K，最大跳变: {max_jump:.4f} K",
                {
                    'std': float(std),
                    'max_jump': float(max_jump),
                    'mean_jump': float(mean_jump)
                },
                [
                    "检查温度传感器接线是否良好",
                    "检查是否存在电磁干扰",
                    "考虑增加测量滤波（如移动平均）",
                    "检查传感器电缆是否与其他电缆捆扎在一起"
                ]
            )

        return None

    def _check_trend(self, temps: List[float]) -> Optional[Tuple]:
        """
        检测温度趋势（整体上升/下降/平稳）
        """
        if len(temps) < 10:
            return None

        temps_array = np.array(temps)

        # 比较前半段和后半段的均值
        mid = len(temps) // 2
        first_half_mean = np.mean(temps_array[:mid])
        second_half_mean = np.mean(temps_array[mid:])
        change = second_half_mean - first_half_mean

        # 判断趋势
        if abs(change) > 0.2:  # 变化超过0.2K
            direction = "上升" if change > 0 else "下降"
            return (
                ProblemType.UNKNOWN,
                'info',
                f"温度整体呈{direction}趋势，变化约 {change:.3f} K",
                {
                    'first_half_mean': float(first_half_mean),
                    'second_half_mean': float(second_half_mean),
                    'change': float(change),
                    'direction': direction
                },
                ["继续观察，让系统自然趋于稳定"] if abs(change) < 0.5 else
                ["温度变化较大，可能需要调整控制参数"]
            )

        return None

    def diagnose_and_suggest(self, temperatures: List[float],
                            target_temp: float = None) -> str:
        """
        生成完整的诊断报告

        Args:
            temperatures: 温度历史
            target_temp: 目标温度

        Returns:
            str: 格式化的诊断报告
        """
        result = self.analyze(temperatures, target_temp=target_temp)

        report = []
        report.append("=" * 50)
        report.append("🌡️ 温度控制诊断报告")
        report.append("=" * 50)

        # 基础统计
        stats = self._get_basic_stats(temperatures)
        report.append(f"\n📊 基础统计:")
        report.append(f"   平均温度: {stats['mean']:.4f} K")
        report.append(f"   标准差:   {stats['std']:.4f} K")
        report.append(f"   温度范围: {stats['min']:.4f} ~ {stats['max']:.4f} K")
        report.append(f"   数据点数: {stats['data_points']}")

        if target_temp:
            error = stats['mean'] - target_temp
            report.append(f"   目标温度: {target_temp:.3f} K")
            report.append(f"   平均误差: {error:+.4f} K")

        # 问题诊断
        report.append(f"\n🔍 诊断结果:")
        severity_emoji = {'critical': '🔴', 'warning': '🟡', 'info': '🟢'}
        emoji = severity_emoji.get(result.severity, '⚪')
        report.append(f"   {emoji} {result.description}")

        # 详细信息
        if result.details:
            report.append(f"\n📋 详细参数:")
            for key, value in result.details.items():
                if isinstance(value, float):
                    report.append(f"   {key}: {value:.6f}")
                else:
                    report.append(f"   {key}: {value}")

        # 建议
        if result.suggestions:
            report.append(f"\n💡 解决方案:")
            for i, suggestion in enumerate(result.suggestions, 1):
                report.append(f"   {i}. {suggestion}")

        report.append("\n" + "=" * 50)

        return '\n'.join(report)


class AdaptivePIDAdjuster:
    """
    自适应PID调节器

    根据温度控制状态自动调整PID参数，以改善控制效果。
    """

    def __init__(self):
        self.current_state = 'normal'
        self.adjustment_history = []

    def analyze_and_adjust(self, temperatures: List[float],
                          current_pid: Dict[str, float],
                          target_temp: float) -> Dict[str, float]:
        """
        分析温度数据并给出PID调整建议

        Args:
            temperatures: 温度历史
            current_pid: 当前PID参数 {'p': xxx, 'i': xxx, 'd': xxx}
            target_temp: 目标温度

        Returns:
            Dict: 调整后的PID参数和建议
        """
        diagnostics = TemperatureDiagnostics()
        result = diagnostics.analyze(temperatures, target_temp=target_temp)

        new_pid = current_pid.copy()
        adjustments = []

        if result.problem_type == ProblemType.OSCILLATION:
            # 震荡问题：减小P，增加D
            old_p = new_pid['p']
            new_pid['p'] = max(old_p * 0.7, old_p - 20)  # 减小至少20
            new_pid['d'] = min(new_pid.get('d', 0) + 5, 20)  # 增加D
            adjustments.append(f"P: {old_p:.1f} → {new_pid['p']:.1f} (减小以抑制振荡)")
            adjustments.append(f"D: {new_pid.get('d', 0):.1f} → {new_pid['d']:.1f} (增加微分阻尼)")

        elif result.problem_type == ProblemType.DRIFT:
            # 漂移问题：增加I
            old_i = new_pid.get('i', 0)
            new_pid['i'] = min(old_i + 1, 20)  # 增加积分
            if old_i == 0:
                adjustments.append(f"I: 0 → {new_pid['i']:.1f} (启用积分消除稳态误差)")
            else:
                adjustments.append(f"I: {old_i:.1f} → {new_pid['i']:.1f} (增加积分消除漂移)")

        elif result.problem_type == ProblemType.NOISY:
            # 噪声问题：减小P，增加滤波
            old_p = new_pid['p']
            new_pid['p'] = max(old_p * 0.8, old_p - 10)
            adjustments.append(f"P: {old_p:.1f} → {new_pid['p']:.1f} (减小P降低对噪声的敏感度)")
            adjustments.append("建议：在温度读取时增加移动平均滤波")

        elif result.problem_type == ProblemType.STABLE:
            # 稳定状态：可以微调优化
            mean_temp = np.mean(temperatures)
            error = abs(mean_temp - target_temp)

            if error > 0.1:
                # 有稳态误差，增加I
                old_i = new_pid.get('i', 0)
                new_pid['i'] = min(old_i + 2, 20)
                adjustments.append(f"存在稳态误差 {error:.3f}K: I: {old_i:.1f} → {new_pid['i']:.1f}")

        return {
            'new_pid': new_pid,
            'adjustments': adjustments,
            'diagnosis': result
        }


def diagnose_temperature_stability(
    temperatures: List[float],
    target_temp: float = None,
) -> DiagnosticResult:
    """Convenience function — one-shot diagnostic without creating objects.

    Usage:
        from temperature_diagnostics import diagnose_temperature_stability

        result = diagnose_temperature_stability(my_temps, target_temp=30.0)
        print(result.description)
        for s in result.suggestions:
            print(f"  • {s}")
    """
    diag = TemperatureDiagnostics()
    return diag.analyze(temperatures, target_temp=target_temp)


def run_diagnostics_demo():
    """Run the built-in diagnostic demo with synthetic data."""
    diagnostics = TemperatureDiagnostics()
    adjuster = AdaptivePIDAdjuster()

    print("\n" + "=" * 60)
    print("Temperature Control Diagnostics Demo")
    print("=" * 60)

    # Scenario 1: stable
    print("\n[Scenario 1: Stable]")
    stable_temps = [10.0 + np.random.normal(0, 0.01) for _ in range(50)]
    print(diagnostics.diagnose_and_suggest(stable_temps, target_temp=10.0))

    # Scenario 2: oscillating
    print("\n[Scenario 2: Oscillating]")
    oscillation_temps = [10.0 + 0.5 * np.sin(i * 0.3) + np.random.normal(0, 0.02) for i in range(50)]
    print(diagnostics.diagnose_and_suggest(oscillation_temps, target_temp=10.0))

    # Scenario 3: drifting
    print("\n[Scenario 3: Drifting]")
    drift_temps = [10.0 + 0.01 * i + np.random.normal(0, 0.01) for i in range(50)]
    print(diagnostics.diagnose_and_suggest(drift_temps, target_temp=10.0))

    # Scenario 4: noisy
    print("\n[Scenario 4: Noisy]")
    noisy_temps = [10.0 + np.random.normal(0, 0.08) for _ in range(50)]
    print(diagnostics.diagnose_and_suggest(noisy_temps, target_temp=10.0))

    # Adaptive PID adjustment demo
    print("\n[Adaptive PID Adjustment Demo]")
    current_pid = {"p": 100.0, "i": 5.0, "d": 0.0}
    result = adjuster.analyze_and_adjust(oscillation_temps, current_pid, 10.0)
    print(f"Current PID: {current_pid}")
    print(f"Diagnosed problem: {result['diagnosis'].problem_type.value}")
    print(f"Adjusted PID: {result['new_pid']}")
    print("Adjustments:")
    for adj in result["adjustments"]:
        print(f"  - {adj}")


if __name__ == "__main__":
    run_diagnostics_demo()
