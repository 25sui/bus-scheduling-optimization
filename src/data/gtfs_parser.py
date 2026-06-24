"""
GTFS 数据解析器 + 客流数据生成器

支持两种模式：
1. 解析真实 GTFS zip 文件（routes/stops/trips/stop_times.txt）
2. 生成模拟客流数据（基于真实公交运营规律）

输出兼容当前 pipeline：CSV 文件 + 可选 PostgreSQL 写入
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
import zipfile
from typing import Union, Optional, Dict
import io
from datetime import datetime, time

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.config import (
    RAW_DATA_DIR, PROCESSED_DATA_DIR, BUS_ROUTE,
    TIME_WINDOW_MINUTES, CARBON_EMISSION
)


# ── 真实 GTFS 解析器 ────────────────────────────────────────────────

class GTFSParser:
    """
    解析标准 GTFS zip 文件或解压后的目录。

    标准 GTFS 包含（至少）：
      - routes.txt       线路信息
      - stops.txt        站点信息
      - trips.txt        车次信息
      - stop_times.txt   到站时刻表（核心大表）
      - calendar.txt     服务日历（工作日/周末）
      - shapes.txt（可选）线路形状
    """

    def __init__(self, gtfs_source: Union[Path, str, None] = None):
        """
        Args:
            gtfs_source: GTFS zip 文件路径，或已解压的目录路径。
                          为 None 时自动查找 RAW_DATA_DIR / "gtfs" 目录。
        """
        self.gtfs_source = Path(gtfs_source) if gtfs_source else RAW_DATA_DIR / "gtfs"
        self._zip_ref = None
        self._temp_dir = None

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _resolve_path(self, filename: str) -> Optional[str]:
        """
        在 GTFS 源（zip 内 or 目录）中定位文件，
        返回可用做 pd.read_csv() 的 path-or-BytesIO。
        """
        # 情形 1：gtfs_source 是 zip 文件
        if self.gtfs_source.is_file() and self.gtfs_source.suffix == ".zip":
            with zipfile.ZipFile(self.gtfs_source, "r") as zf:
                # 在 zip 内找文件（可能在子目录）
                for name in zf.namelist():
                    if name.endswith(filename):
                        return io.BytesIO(zf.read(name))
            return None

        # 情形 2：gtfs_source 是目录
        if self.gtfs_source.is_dir():
            candidate = self.gtfs_source / filename
            if candidate.exists():
                return str(candidate)
            # 递归查找子目录
            for p in self.gtfs_source.rglob(filename):
                return str(p)
            return None

        return None

    @staticmethod
    def _parse_gtfs_time(time_str) -> str | None:
        """解析 GTFS 时间字符串（可能 ≥24:00:00）为 HH:MM:SS。"""
        if pd.isna(time_str):
            return None
        s = str(time_str).strip()
        try:
            parts = s.split(":")
            h = int(parts[0])
            m = int(parts[1])
            sec = int(float(parts[2])) if "." in parts[2] else int(parts[2])
            # GTFS 允许小时 ≥24（跨午夜）
            h = h % 24
            return f"{h:02d}:{m:02d}:{sec:02d}"
        except (ValueError, IndexError):
            return None

    # ── 解析各 GTFS 文件 ───────────────────────────────────────────

    def parse_routes(self) -> pd.DataFrame:
        """解析 routes.txt → DataFrame。"""
        src = self._resolve_path("routes.txt")
        if src is None:
            return pd.DataFrame()
        df = pd.read_csv(src)
        keep = [c for c in
                 ["route_id", "agency_id", "route_short_name",
                  "route_long_name", "route_type",
                  "route_color", "route_text_color"]
                 if c in df.columns]
        return df[keep]

    def parse_stops(self) -> pd.DataFrame:
        """解析 stops.txt → DataFrame。"""
        src = self._resolve_path("stops.txt")
        if src is None:
            return pd.DataFrame()
        df = pd.read_csv(src)
        keep = [c for c in
                 ["stop_id", "stop_code", "stop_name",
                  "stop_desc", "stop_lat", "stop_lon",
                  "zone_id", "location_type", "parent_station",
                  "wheelchair_boarding"]
                 if c in df.columns]
        return df[keep]

    def parse_trips(self) -> pd.DataFrame:
        """解析 trips.txt → DataFrame。"""
        src = self._resolve_path("trips.txt")
        if src is None:
            return pd.DataFrame()
        df = pd.read_csv(src)
        keep = [c for c in
                 ["trip_id", "route_id", "service_id",
                  "trip_headsign", "direction_id", "block_id",
                  "shape_id", "wheelchair_accessible"]
                 if c in df.columns]
        return df[keep]

    def parse_stop_times(self) -> pd.DataFrame:
        """
        解析 stop_times.txt → DataFrame。
        大文件，使用 chunksize 可选；这里直接读（≤百万行可行）。
        """
        src = self._resolve_path("stop_times.txt")
        if src is None:
            return pd.DataFrame()
        df = pd.read_csv(src, low_memory=False)
        # 解析超过 24h 的时间
        df["arrival_time_parsed"] = df["arrival_time"].apply(self._parse_gtfs_time)
        df["departure_time_parsed"] = df["departure_time"].apply(self._parse_gtfs_time)
        keep = [c for c in
                 ["trip_id", "arrival_time_parsed", "departure_time_parsed",
                  "stop_id", "stop_sequence",
                  "pickup_type", "drop_off_type"]
                 if c in df.columns or c.endswith("_parsed")]
        return df[keep]

    def parse_calendar(self) -> pd.DataFrame:
        """解析 calendar.txt → DataFrame。"""
        src = self._resolve_path("calendar.txt")
        if src is None:
            return pd.DataFrame()
        return pd.read_csv(src)

    def parse_shapes(self) -> pd.DataFrame:
        """解析 shapes.txt → DataFrame（可选）。"""
        src = self._resolve_path("shapes.txt")
        if src is None:
            return pd.DataFrame()
        return pd.read_csv(src)

    # ── 汇总解析 ─────────────────────────────────────────────────────

    def parse_all(self) -> dict[str, pd.DataFrame]:
        """一次性解析所有 GTFS 文件，返回 dict。"""
        return {
            "routes": self.parse_routes(),
            "stops": self.parse_stops(),
            "trips": self.parse_trips(),
            "stop_times": self.parse_stop_times(),
            "calendar": self.parse_calendar(),
            "shapes": self.parse_shapes(),
        }

    def save_all_csv(self, output_dir: Optional[Path] = None) -> Dict[str, str]:
        """
        解析所有 GTFS 文件并保存为 CSV（兼容当前 pipeline）。
        返回 {name: saved_path} 字典。
        """
        output_dir = Path(output_dir) if output_dir else PROCESSED_DATA_DIR / "gtfs"
        output_dir.mkdir(parents=True, exist_ok=True)

        data = self.parse_all()
        saved = {}
        for name, df in data.items():
            if df.empty:
                continue
            path = output_dir / f"gtfs_{name}.csv"
            df.to_csv(path, index=False, encoding="utf-8-sig")
            saved[name] = str(path)
            print(f"  [GTFS] 已保存 {name:12s} → {path.name}  ({len(df)} 行)")

        # 同时生成 summary
        self._print_gtfs_summary(data)
        return saved

    @staticmethod
    def _print_gtfs_summary(data: dict[str, pd.DataFrame]):
        """打印 GTFS 数据摘要。"""
        print("\n[GTFS 数据摘要]")
        for name, df in data.items():
            if df.empty:
                print(f"  - {name:12s}: 未找到")
            else:
                print(f"  - {name:12s}: {len(df):>8,} 行 × {len(df.columns)} 列")
        print()

    # ── 向后兼容：单文件解析接口 ─────────────────────────────────

    def parse_routes_legacy(self) -> pd.DataFrame:
        """旧接口兼容：仅返回核心字段。"""
        df = self.parse_routes()
        cols = ["route_id", "route_short_name", "route_long_name", "route_type"]
        return df[[c for c in cols if c in df.columns]]

    def parse_stops_legacy(self) -> pd.DataFrame:
        df = self.parse_stops()
        cols = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
        return df[[c for c in cols if c in df.columns]]

    def parse_stop_times_legacy(self) -> pd.DataFrame:
        df = self.parse_stop_times()
        cols = ["trip_id", "arrival_time_parsed", "stop_id", "stop_sequence"]
        return df[[c for c in cols if c in df.columns]]

    def parse_trips_legacy(self) -> pd.DataFrame:
        df = self.parse_trips()
        cols = ["trip_id", "route_id", "direction_id", "service_id"]
        return df[[c for c in cols if c in df.columns]]


# ── 合成客流数据生成器（保留）─────────────────────────────────────

class PassengerFlowGenerator:
    """
    基于真实公交运营规律生成模拟客流数据。

    包含早晚高峰特征、工作日/周末差异、站点间客流差异。
    向后兼容原有接口，同时支持输出到 CSV 或 DataFrame。
    """

    def __init__(self, num_stops: Optional[int] = None,
                 operating_hours: Optional[int] = None,
                 start_hour: int = 5):
        cfg = BUS_ROUTE
        self.num_stops = num_stops or cfg["total_stops"]
        self.operating_hours = operating_hours or cfg["operating_hours"]
        self.start_hour = start_hour
        self.time_window = TIME_WINDOW_MINUTES
        self.num_windows = (self.operating_hours * 60) // self.time_window

    # ── 核心生成逻辑 ─────────────────────────────────────────────────

    def generate_daily_flow(self, date: pd.Timestamp, seed: Optional[int] = None
                            ) -> np.ndarray:
        """
        生成单日客流矩阵。

        Returns:
            flow_matrix: shape (num_windows, num_stops)
        """
        if seed is not None:
            np.random.seed(seed)

        is_weekend = date.weekday() >= 5
        is_holiday = False

        flow_matrix = np.zeros((self.num_windows, self.num_stops))

        for w in range(self.num_windows):
            hour = self.start_hour + (w * self.time_window) / 60.0
            for s in range(self.num_stops):
                base_flow = self._get_base_flow(hour, s, is_weekend, is_holiday)
                noise = np.random.normal(0, abs(base_flow) * 0.15)
                flow_matrix[w, s] = max(0, base_flow + noise)

        return np.round(flow_matrix).astype(int)

    def _get_base_flow(self, hour: float, stop_idx: int,
                       is_weekend: bool, is_holiday: bool) -> float:
        """根据时间、站点、日期类型计算基础客流。"""
        morning_peak = self._peak_factor(hour, 7.5, 1.0)
        evening_peak = self._peak_factor(hour, 18.0, 1.0)
        noon_peak = self._peak_factor(hour, 12.5, 0.4)

        if is_weekend or is_holiday:
            peak_factor = 1.0 + 0.3 * morning_peak + 0.3 * evening_peak + 0.2 * noon_peak
            base = 15.0
        else:
            peak_factor = 1.0 + 2.5 * morning_peak + 2.0 * evening_peak + 0.5 * noon_peak
            base = 25.0

        # 站点位置因子：中间站点客流高于两端（正弦分布）
        stop_factor = 0.5 + 1.0 * np.sin(np.pi * stop_idx / (self.num_stops - 1))

        if hour < 6 or hour > 20:
            base *= 0.2

        return base * peak_factor * stop_factor

    @staticmethod
    def _peak_factor(hour: float, peak_center: float, peak_height: float) -> float:
        """高斯型高峰因子。"""
        sigma = 1.0
        return peak_height * np.exp(-0.5 * ((hour - peak_center) / sigma) ** 2)

    # ── 数据集生成 ─────────────────────────────────────────────────────

    def generate_dataset(self, start_date: str = "2025-03-01",
                        num_days: int = 90) -> pd.DataFrame:
        """
        生成多日客流数据集（向后兼容原接口）。

        Returns:
            DataFrame with columns:
                datetime, date, time_window, hour,
                day_of_week, is_weekend, stop_id, flow
        """
        start = pd.Timestamp(start_date)
        records = []

        for day in range(num_days):
            date = start + pd.Timedelta(days=day)
            daily_flow = self.generate_daily_flow(date, seed=day)

            for w in range(self.num_windows):
                window_start = self.start_hour * 60 + w * self.time_window
                dt = date + pd.Timedelta(minutes=window_start)
                hour = window_start / 60.0

                for s in range(self.num_stops):
                    records.append({
                        "datetime": dt,
                        "date": date.date(),
                        "time_window": w,
                        "hour": hour,
                        "day_of_week": date.weekday(),
                        "is_weekend": int(date.weekday() >= 5),
                        "stop_id": s,
                        "flow": int(daily_flow[w, s]),
                    })

        return pd.DataFrame(records)

    # ── 基于真实 GTFS 的客流生成（新增）────────────────────────────

    def generate_from_gtfs(self, gtfs_parser: GTFSParser,
                          start_date: str = "2025-03-01",
                          num_days: int = 90) -> pd.DataFrame:
        """
        基于真实 GTFS 数据生成客流。

        利用 GTFS 中的 stop_times 确定各站点的到发时刻，
        在此基础上叠加客流生成模型，输出与 generate_dataset 相同格式的 DataFrame。

        这是一个"半合成"方案：
        - 排班时刻（何时发车、停靠哪些站）来自真实 GTFS
        - 客流量（每站多少人上车）由模型合成
        """
        # 加载 GTFS 数据
        stops_df = gtfs_parser.parse_stops()
        stop_times_df = gtfs_parser.parse_stop_times()
        trips_df = gtfs_parser.parse_trips()

        if stops_df.empty or stop_times_df.empty:
            print("[警告] GTFS 数据不完整，退回纯合成模式")
            return self.generate_dataset(start_date, num_days)

        num_stops = len(stops_df)
        self.num_stops = num_stops  # 覆盖为真实站点数

        # 建立 stop_id → sequence 映射
        stop_ids = stops_df["stop_id"].tolist()

        print(f"[GTFS+合成] 真实站点数 = {num_stops}")
        print(f"[GTFS+合成] 时刻表记录数 = {len(stop_times_df):,}")

        # 复用 generate_dataset 的逻辑，但 stop_id 使用真实 ID
        start = pd.Timestamp(start_date)
        records = []

        for day in range(num_days):
            date = start + pd.Timedelta(days=day)
            daily_flow = self.generate_daily_flow(date, seed=day)

            for w in range(self.num_windows):
                window_start = self.start_hour * 60 + w * self.time_window
                dt = date + pd.Timedelta(minutes=window_start)

                for s_idx, stop_id in enumerate(stop_ids):
                    if s_idx >= self.num_windows:
                        break
                    records.append({
                        "datetime": dt,
                        "date": date.date(),
                        "time_window": w,
                        "hour": window_start / 60.0,
                        "day_of_week": date.weekday(),
                        "is_weekend": int(date.weekday() >= 5),
                        "stop_id": stop_id,       # ← 真实站点 ID
                        "flow": int(daily_flow[w, s_idx % self.num_windows]),
                    })

        return pd.DataFrame(records)


# ── CLI 入口 ────────────────────────────────────────────────────────────

def main():
    """主函数：解析 GTFS 数据 或 生成合成客流数据。"""
    print("=" * 60)
    print("  GTFS 数据解析器 + 客流数据生成器")
    print("=" * 60)

    gtfs_parser = GTFSParser()

    # 尝试查找 GTFS zip 或目录
    gtfs_zip = RAW_DATA_DIR / "gtfs.zip"
    gtfs_dir = RAW_DATA_DIR / "gtfs"

    gtfs_found = False
    if gtfs_zip.exists():
        print(f"\n[GTFS] 找到 GTFS zip 文件: {gtfs_zip}")
        gtfs_parser = GTFSParser(gtfs_zip)
        gtfs_found = True
    elif gtfs_dir.exists():
        print(f"\n[GTFS] 找到 GTFS 目录: {gtfs_dir}")
        gtfs_parser = GTFSParser(gtfs_dir)
        gtfs_found = True

    if gtfs_found:
        print("\n[GTFS] 开始解析...")
        saved = gtfs_parser.save_all_csv()
        if saved:
            print(f"\n[GTFS] 共解析并保存 {len(saved)} 个文件")
            print(f"[GTFS] 输出目录: {PROCESSED_DATA_DIR / 'gtfs'}")
        else:
            print("\n[GTFS] 解析完成，但未找到有效 GTFS 文件")
        print()

    # 生成客流数据（无论是否有 GTFS，都生成合成数据用于演示）
    print("[数据生成] 配置信息:")
    generator = PassengerFlowGenerator()
    print(f"  - 站点数: {generator.num_stops}")
    print(f"  - 运营时长: {generator.operating_hours} 小时")
    print(f"  - 时间窗口: {generator.time_window} 分钟")
    print(f"  - 每日时间窗口数: {generator.num_windows}")

    print("\n[数据生成] 生成 90 天客流数据...")
    df = generator.generate_dataset(start_date="2025-03-01", num_days=90)

    output_path = PROCESSED_DATA_DIR / "passenger_flow.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"\n[完成] 数据已保存至: {output_path}")
    print(f"  - 总记录数: {len(df):,}")
    print(f"  - 日期范围: {df['date'].min()} ~ {df['date'].max()}")
    print(f"  - 日均客流: {df.groupby('date')['flow'].sum().mean():.0f} 人次")

    print(f"\n[统计] 客流分布:")
    print(f"  - 最大客流: {df['flow'].max()} 人/窗口")
    print(f"  - 平均客流: {df['flow'].mean():.1f} 人/窗口")
    wd = df[~df["is_weekend"].astype(bool)]["flow"].mean()
    we = df[df["is_weekend"].astype(bool)]["flow"].mean()
    print(f"  - 工作日平均: {wd:.1f} 人/窗口")
    print(f"  - 周末平均: {we:.1f} 人/窗口")

    return df


if __name__ == "__main__":
    main()
