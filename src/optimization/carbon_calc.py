"""
碳排放计算模块

根据公交运营参数（车型、载客率、行驶里程）计算碳排放量。
支持不同车型和不同运营场景的碳足迹量化。
"""
import numpy as np


class CarbonCalculator:
    """公交碳排放计算器"""

    def __init__(self, config: dict = None):
        # 兼容 config.py 中的键名格式（"large_bus" 或 "large_bus_emission"）
        if config:
            self.config = {
                "large_bus_emission": config.get("large_bus_emission", config.get("large_bus", 1.2)),
                "medium_bus_emission": config.get("medium_bus_emission", config.get("medium_bus", 0.8)),
                "large_bus_capacity": config.get("large_bus_capacity", config.get("large_bus_capacity", 80)),
                "medium_bus_capacity": config.get("medium_bus_capacity", config.get("medium_bus_capacity", 40)),
            }
        else:
            self.config = {
                "large_bus_emission": 1.2,
                "medium_bus_emission": 0.8,
                "large_bus_capacity": 80,
                "medium_bus_capacity": 40,
            }
        # 从配置中读取公交车型（默认大型车）
        self.default_bus_type = "large"
        self.default_load_ratio = 0.6  # 默认载客率 60%

    def calculate_trip_emission(self, distance_km: float,
                                 bus_type: str = None,
                                 load_ratio: float = None) -> float:
        """
        计算单趟行程碳排放

        Args:
            distance_km: 行驶距离(公里)，应为往返距离
            bus_type: 车型 ("large" / "medium")，None 则使用默认
            load_ratio: 载客率 (0-1)，None 则使用默认

        Returns:
            emission: 碳排放量 (kg CO2)
        """
        bt = bus_type or self.default_bus_type
        lr = load_ratio if load_ratio is not None else self.default_load_ratio

        if bt == "large":
            base_rate = self.config["large_bus_emission"]
        else:
            base_rate = self.config["medium_bus_emission"]

        # 载客率调整：空载时单位排放略高，满载时效率更高
        efficiency_factor = 0.9 + 0.1 * (1 - lr)

        emission = distance_km * base_rate * efficiency_factor
        return round(emission, 3)

    def calculate_daily_emission(self, schedule: np.ndarray,
                                  route_length_km: float,
                                  num_stops: int = 20) -> dict:
        """
        计算每日总碳排放（精确计算，不用 ceil）
        
        Args:
            schedule: 各时段发车间隔数组 (分钟)，长度=时间窗口数
            route_length_km: 单程线路长度(km)
            num_stops: 站点数
            
        Returns:
            details: 包含各项详细数据的字典
        """
        time_windows_per_hour = 60 / 30  # 30分钟窗口，每小时2个
        total_trips = 0.0  # 改用浮点数，支持小数班次
        total_emission = 0.0
        trip_details = []

        for i, headway in enumerate(schedule):
            if headway <= 0:
                continue
            
            # 每个时间窗口的发车班次（精确计算，不用 ceil）
            window_minutes = 30
            trips_in_window = window_minutes / headway  # 可以是小数
            total_trips += trips_in_window
            
            # 每趟碳排放（往返）
            emission_per_trip = self.calculate_trip_emission(
                route_length_km * 2,
                bus_type=self.default_bus_type,
                load_ratio=self.default_load_ratio,
            )
            
            # 总碳排放 = 班次 × 每趟碳排放
            total_emission += trips_in_window * emission_per_trip
            
            trip_details.append({
                "time_window": i,
                "headway": headway,
                "trips": trips_in_window,
                "emission_kg": trips_in_window * emission_per_trip,
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
        计算固定排班方案的基准碳排放（与 calculate_daily_emission 逻辑一致）

        Args:
            fixed_headway: 固定发车间隔(分钟)
            route_length_km: 线路长度(单程, km)
            operating_hours: 运营小时数

        Returns:
            包含基准碳排放的字典
        """
        total_minutes = operating_hours * 60
        # 总趟数 = 运营总分钟数 / 发车间隔（精确计算，不用 ceil）
        total_trips = total_minutes / fixed_headway

        # 每趟往返距离
        trip_distance = route_length_km * 2

        # 总距离
        total_distance = total_trips * trip_distance

        # 总碳排放
        total_emission = total_distance * self.config["large_bus_emission"]

        return {
            "fixed_headway": fixed_headway,
            "total_trips": total_trips,
            "total_distance_km": total_distance,
            "total_emission_kg": round(total_emission, 2),
        }


def main():
    """测试碳排放计算"""
    print("=" * 50)
    print("碳排放计算模块测试")
    print("=" * 50)

    calc = CarbonCalculator()

    # 测试单趟计算
    emission_15km = calc.calculate_trip_emission(15.0 * 2, "large", 0.6)
    print(f"\n单趟(15km×2, 大型车, 60%载客): {emission_15km} kg CO2")

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
