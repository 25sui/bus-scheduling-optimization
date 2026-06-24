"""
碳排放计算模块

根据公交运营参数（车型、载客率、行驶里程）计算碳排放量。
支持不同车型和不同运营场景的碳足迹量化。
"""
import numpy as np


class CarbonCalculator:
    """公交碳排放计算器"""

    def __init__(self, config: dict = None):
        self.config = config or {
            "large_bus_emission": 1.20,    # kg CO2/km (大型车)
            "medium_bus_emission": 0.80,   # kg CO2/km (中型车)
            "large_bus_capacity": 80,       # 额定载客
            "medium_bus_capacity": 40,      # 额定载客
        }

    def calculate_trip_emission(self, distance_km: float,
                                 bus_type: str = "large",
                                 load_ratio: float = 0.5) -> float:
        """
        计算单趟行程碳排放

        Args:
            distance_km: 行驶距离(公里)
            bus_type: 车型 ("large" / "medium")
            load_ratio: 载客率 (0-1)

        Returns:
            emission: 碳排放量 (kg CO2)
        """
        if bus_type == "large":
            base_rate = self.config["large_bus_emission"]
        else:
            base_rate = self.config["medium_bus_emission"]

        # 载客率调整：空载时单位排放略高（分摊到更少乘客），满载时效率更高
        # 使用线性插值：满载时排放系数为基准，空载时增加10%
        efficiency_factor = 0.9 + 0.1 * (1 - load_ratio)

        emission = distance_km * base_rate * efficiency_factor
        return round(emission, 3)

    def calculate_daily_emission(self, schedule: np.ndarray,
                                  route_length_km: float,
                                  num_stops: int = 20) -> dict:
        """
        计算每日总碳排放

        Args:
            schedule: 各时段发车间隔数组 (分钟)，长度=时间窗口数
            route_length_km: 单程线路长度(km)
            num_stops: 站点数

        Returns:
            details: 包含各项详细数据的字典
        """
        time_windows_per_hour = 60 / 30  # 30分钟窗口，每小时2个
        total_trips = 0
        total_emission = 0.0
        trip_details = []

        for i, headway in enumerate(schedule):
            if headway <= 0:
                continue

            # 每个时间窗口的发车班次
            window_hours = 0.5  # 30分钟窗口
            trips_in_window = int(np.ceil(window_hours * 60 / headway))
            total_trips += trips_in_window

            for _ in range(trips_in_window):
                emission = self.calculate_trip_emission(
                    route_length_km * 2,  # 往返
                    bus_type="large"
                )
                total_emission += emission
                trip_details.append({
                    "time_window": i,
                    "headway": headway,
                    "emission_kg": emission,
                })

        return {
            "total_trips": total_trips,
            "total_emission_kg": round(total_emission, 2),
            "per_trip_avg": round(total_emission / max(total_trips, 1), 3),
            "trip_details": trip_details,
        }

    def calculate_baseline_emission(self, fixed_headway: int,
                                    route_length_km: float,
                                    operating_hours: int = 16) -> dict:
        """
        计算固定排班方案的基准碳排放

        Args:
            fixed_headway: 固定发车间隔(分钟)
            route_length_km: 线路长度
            operating_hours: 运营小时数
        """
        total_minutes = operating_hours * 60
        total_trips = int(np.ceil(total_minutes / fixed_headway))
        total_distance = total_trips * route_length_km * 2  # 往返
        total_emission = total_distance * self.config["large_bus_emission"]

        return {
            "fixed_headway": fixed_headway,
            "total_trips": total_trips,
            "total_emission_kg": round(total_emission, 2),
            "total_distance_km": total_distance,
        }


def main():
    """测试碳排放计算"""
    print("=" * 50)
    print("碳排放计算模块测试")
    print("=" * 50)

    calc = CarbonCalculator()

    # 测试单趟计算
    emission_15km = calc.calculate_trip_emission(15.0, "large", 0.6)
    print(f"\n单趟(15km, 大型车, 60%载客): {emission_15kg} kg CO2")

    # 测试排班方案对比
    schedule_dense = [5] * 16 + [10] * 16  # 高峰密集 + 平峰
    schedule_sparse = [15] * 32           # 全天稀疏

    result_dense = calc.calculate_daily_emission(schedule_dense, 15.0)
    result_sparse = calc.calculate_daily_emission(schedule_sparse, 15.0)
    baseline = calc.calculate_baseline_emission(10, 15.0)

    print(f"\n密集排班方案: {result_dense['total_trips']} 趟/日, "
          f"排放 {result_dense['total_emission_kg']} kg CO2")
    print(f"稀疏排班方案: {result_sparse['total_trips']} 趟/日, "
          f"排放 {result_sparse['total_emission_kg']} kg CO2")
    print(f"固定排班(10min): {baseline['total_trips']} 趟/日, "
          f"排放 {baseline['total_emission_kg']} kg CO2")

    reduction = baseline["total_emission_kg"] - result_sparse["total_emission_kg"]
    pct = reduction / baseline["total_emission_kg"] * 100
    print(f"\n优化后减排: {reduction:.2f} kg CO2/日 ({pct:.1f}%)")


if __name__ == "__main__":
    main()
