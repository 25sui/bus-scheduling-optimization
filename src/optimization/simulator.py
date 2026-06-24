"""
公交运营仿真器

模拟公交运营过程，验证排班方案的实际效果。
输入：排班方案 + 客流数据
输出：运营指标（等待时间、满载率、碳排放）
支持"优化前 vs 优化后"对比。
"""
import numpy as np
import pandas as pd
from typing import Union, List

from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.config import BUS_ROUTE, CARBON_EMISSION
from src.optimization.carbon_calc import CarbonCalculator


class BusOperationSimulator:
    """公交运营仿真器"""

    def __init__(self):
        self.route = BUS_ROUTE.copy()
        self.carbon_calc = CarbonCalculator()
        self.num_stops = self.route["total_stops"]
        self.route_length_km = self.route["route_length_km"]
        self.avg_speed_kmh = self.route["avg_speed_kmh"]
        self.trip_time_min = (self.route_length_km / self.avg_speed_kmh) * 60  # 单程时间(分钟)

        # 生成模拟客流分布（与数据生成器一致）
        self._build_flow_pattern()

    def _build_flow_pattern(self):
        """构建各时段各站点的客流到达模式"""
        self.num_slots = int(self.route["operating_hours"] * 60 / 30)
        self.flow_matrix = np.zeros((self.num_slots, self.num_stops))

        for slot in range(self.num_slots):
            hour = (slot * 30) / 60 + 5
            for stop in range(self.num_stops):
                # 基础客流 + 高峰因子 + 站点位置因子
                base = 20
                peak_factor = (
                    2.5 * np.exp(-0.5 * ((hour - 7.5) / 1) ** 2) +
                    2.0 * np.exp(-0.5 * ((hour - 18) / 1) ** 2)
                )
                stop_factor = 0.5 + 1.0 * np.sin(np.pi * stop / (self.num_stops - 1))

                if hour < 6 or hour > 20:
                    base *= 0.2

                self.flow_matrix[slot, stop] = base * (1 + peak_factor) * stop_factor

    def simulate_schedule(self, schedule: Union[List[int], np.ndarray],
                           name: str = "方案") -> dict:
        """
        模拟排班方案的运营效果

        Args:
            schedule: 各时段发车间隔列表（分钟）
            name: 方案名称

        Returns:
            metrics: 运营指标字典
        """
        schedule = np.array(schedule)
        total_passengers = 0
        total_wait_time = 0.0
        total_boarded = 0
        total_trips = 0

        slot_details = []

        for slot in range(len(schedule)):
            headway = schedule[slot]
            if headway <= 0:
                headway = 15  # 默认值

            # 该时段的乘客数
            slot_passengers = self.flow_matrix[slot].sum()

            # 发车班次
            num_trips_slot = max(int(np.ceil(30 / headway)), 1)

            # 平均等待时间（均匀到达假设）
            avg_wait = headway / 2.0

            # 实际上车人数（考虑运力限制）
            capacity_per_trip = CARBON_EMISSION["large_bus_capacity"]
            total_capacity = num_trips_slot * capacity_per_trip
            boarded = min(slot_passengers, total_capacity)
            overflow = slot_passengers - boarded

            load_ratio = boarded / total_capacity if total_capacity > 0 else 0

            # 统计
            total_passengers += slot_passengers
            total_wait_time += avg_wait * boarded
            total_boarded += boarded
            total_trips += num_trips_slot

            slot_details.append({
                "time_slot": slot,
                "headway": headway,
                "passengers": round(slot_passengers, 1),
                "trips": num_trips_slot,
                "boarded": round(boarded, 1),
                "overflow": round(overflow, 1),
                "load_ratio": round(load_ratio, 3),
                "avg_wait": avg_wait,
            })

        # 碳排放计算
        carbon_result = self.carbon_calc.calculate_daily_emission(
            schedule, self.route_length_km, self.num_stops
        )

        # 汇总指标
        overall_metrics = {
            "name": name,
            "schedule": list(schedule),
            "total_passengers": round(total_passengers, 1),
            "total_boarded": round(total_boarded, 1),
            "total_overflow": round(total_passengers - total_boarded, 1),
            "total_trips": total_trips,
            "avg_waiting_time": round(
                total_wait_time / max(total_boarded, 1), 2
            ),
            "avg_load_ratio": round(
                total_boarded / (total_trips * CARBON_EMISSION["large_bus_capacity"]),
                3
            ),
            "carbon_emission_kg": carbon_result["total_emission_kg"],
            "carbon_per_passenger": round(
                carbon_result["total_emission_kg"] / max(total_boarded, 1), 4
            ),
            "avg_wait_time_per_slot": [round(s["avg_wait"], 2) for s in slot_details],
            "slot_details": slot_details,
        }

        return overall_metrics

    def compare_schedules(self, baseline: List[int],
                          optimized: List[int]) -> dict:
        """
        对比两个排班方案

        Returns:
            comparison: 对比结果，包含改进百分比
        """
        print("[仿真] 运行基准方案...")
        baseline_result = self.simulate_schedule(baseline, name="固定排班")

        print("[仿真] 运行优化方案...")
        optimized_result = self.simulate_schedule(optimized, name="智能优化")

        # 计算各时段满载率（6个时段：5-8,8-11,11-13,13-16,16-19,19-21）
        def _period_load_rate(details):
            ranges = [(0,6), (6,12), (12,16), (16,22), (22,28), (28,32)]
            result = []
            for start, end in ranges:
                period = details[start:end]
                if period:
                    avg = sum(s["load_ratio"] for s in period) / len(period)
                    result.append(round(avg, 3))
                else:
                    result.append(0.0)
            return result

        baseline_result["load_rate_per_period"] = _period_load_rate(baseline_result["slot_details"])
        optimized_result["load_rate_per_period"] = _period_load_rate(optimized_result["slot_details"])

        # 计算改进量
        wait_reduction = (
            (baseline_result["avg_waiting_time"] - optimized_result["avg_waiting_time"])
            / baseline_result["avg_waiting_time"] * 100
        )
        carbon_reduction = (
            (baseline_result["carbon_emission_kg"] - optimized_result["carbon_emission_kg"])
            / baseline_result["carbon_emission_kg"] * 100
        )
        trips_saved = baseline_result["total_trips"] - optimized_result["total_trips"]

        comparison = {
            "summary": {
                "wait_improve": round((wait_reduction / 100.0), 4),  # 前端以小数显示百分比
                "carbon_reduce": round((carbon_reduction / 100.0), 4),
                "trips_reduced": int(trips_saved),
                "load_improve": round(
                    (optimized_result["avg_load_ratio"] - baseline_result["avg_load_ratio"]) /
                    max(baseline_result["avg_load_ratio"], 0.01), 4
                ),
            },
            "baseline": baseline_result,
            "optimized": optimized_result,
            "improvements": {
                "waiting_time_reduction_pct": round(wait_reduction, 2),
                "carbon_reduction_pct": round(carbon_reduction, 2),
                "trips_saved": trips_saved,
                "carbon_saved_kg": round(
                    baseline_result["carbon_emission_kg"]
                    - optimized_result["carbon_emission_kg"], 2
                ),
            },
        }

        print(f"\n[对比结果]")
        print(f"  等待时间改善: {wait_reduction:.1f}%")
        print(f"  减少碳排放: {carbon_reduction:.1f}%, "
              f"{comparison['improvements']['carbon_saved_kg']} kg CO2/日")
        print(f"  减少班次: {trips_saved} 趟/日")

        return comparison


def main():
    """测试仿真器"""
    sim = BusOperationSimulator()

    # 固定排班 vs 优化排班
    fixed_schedule = [10] * sim.num_slots  # 每10分钟一班
    smart_schedule = (
        [5] * 6      # 早高峰(5-8): 5min间隔
        + [10] * 10   # 日间平峰(8-13)
        + [7] * 4     # 午高峰(13-15)
        + [10] * 4    # 下午(15-17)
        + [5] * 4     # 晚高峰(17-19)
        + [12] * 3    # 傍晚(19-20.5)
        + [15] * 1    # 夜间(20.5-21)
    )

    result = sim.compare_schedules(fixed_schedule, smart_schedule)


if __name__ == "__main__":
    main()
