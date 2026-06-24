"""
数据预处理与特征工程模块

将原始客流数据转换为模型可用的特征矩阵。
包含：时间特征提取、历史滞后特征、标准化、数据集划分。
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.config import (
    PROCESSED_DATA_DIR, LSTM_CONFIG,
    TRAIN_RATIO, VAL_RATIO, TEST_RATIO
)


class DataPreprocessor:
    """数据预处理器"""

    def __init__(self):
        self.scaler_features = StandardScaler()
        self.scaler_target = MinMaxScaler()

    def extract_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取时间相关特征

        Features:
        - hour: 小时（0-23）
        - minute_of_day: 一天中的分钟数
        - day_of_week: 星期几（0-6）
        - is_weekend: 是否周末
        - is_morning_peak: 早高峰(7:00-9:00)
        - is_evening_peak: 晚高峰(17:00-19:00)
        - is_peak: 是否高峰时段
        - time_slot: 时间段编码（早/午/晚/夜）
        """
        df = df.copy()
        df["hour"] = df["datetime"].dt.hour.astype(float)

        # 高峰标记
        df["is_morning_peak"] = ((df["hour"] >= 7) & (df["hour"] < 9)).astype(float)
        df["is_evening_peak"] = ((df["hour"] >= 17) & (df["hour"] < 19)).astype(float)
        df["is_noon_peak"] = ((df["hour"] >= 11) & (df["hour"] < 13)).astype(float)
        df["is_peak"] = np.logical_or(df["is_morning_peak"], df["is_evening_peak"]).astype(float)

        # 周期性编码（sin/cos）
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

        return df

    def add_lag_features(self, df: pd.DataFrame, lag_windows: list[int] = None) -> pd.DataFrame:
        """
        添加历史滞后特征

        Args:
            lag_windows: 滞后窗口列表，默认[1, 2, 3, 7]天
        """
        if lag_windows is None:
            lag_windows = [1, 2, 3, 7]

        df = df.sort_values(["stop_id", "time_window", "date"]).copy()

        for stop_id in df["stop_id"].unique():
            mask = df["stop_id"] == stop_id
            for lag in lag_windows:
                col_name = f"flow_lag_{lag}"
                # 按时间窗口偏移
                shifted = df.loc[mask, "flow"].shift(lag * 32)  # 每天32个时间窗口
                if col_name not in df.columns:
                    df[col_name] = np.nan
                df.loc[mask, col_name] = shifted.values

        return df.fillna(0)

    def create_sequences(self, df: pd.DataFrame, seq_length: int = None) -> tuple[np.ndarray, np.ndarray]:
        """
        创建 LSTM 所需的时间序列样本

        Returns:
            X: shape (n_samples, seq_len, n_features)
            y: shape (n_samples,)
        """
        if seq_length is None:
            seq_length = LSTM_CONFIG["sequence_length"]

        feature_cols = [
            "hour", "hour_sin", "hour_cos",
            "dow_sin", "dow_cos",
            "is_morning_peak", "is_evening_peak", "is_peak",
            "is_weekend",
        ]

        # 确保所有特征列存在
        existing_features = [c for c in feature_cols if c in df.columns]
        lag_features = [c for c in df.columns if c.startswith("flow_lag_")]
        all_features = existing_features + lag_features

        X_list, y_list = [], []

        for stop_id in sorted(df["stop_id"].unique()):
            stop_data = df[df["stop_id"] == stop_id].sort_values("datetime").reset_index(drop=True)

            if len(stop_data) <= seq_length:
                continue

            features = stop_data[all_features].values
            targets = stop_data["flow"].values

            for i in range(seq_length, len(features)):
                x_seq = features[i - seq_length:i]
                y_val = targets[i]
                X_list.append(x_seq)
                y_list.append(y_val)

        return np.array(X_list), np.array(y_list).reshape(-1, 1)

    def create_xgboost_features(self, df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
        """
        创建 XGBoost 所需的特征（不需要序列）

        Returns:
            y: Series of target values
            X: DataFrame of features
        """
        feature_cols = [
            "hour", "hour_sin", "hour_cos",
            "dow_sin", "dow_cos",
            "is_morning_peak", "is_evening_peak", "is_peak",
            "is_weekend", "stop_id"
        ]
        lag_features = [c for c in df.columns if c.startswith("flow_lag_")]
        all_features = [c for c in (feature_cols + lag_features) if c in df.columns]

        y = df["flow"]
        X = df[all_features].fillna(0)
        return y, X

    def split_dataset(self, X: np.ndarray, y: np.ndarray) -> dict[str, tuple]:
        """
        数据集划分：训练集 / 验证集 / 测试集
        """
        n_total = len(X)
        n_train = int(n_total * TRAIN_RATIO)
        n_val = int(n_total * VAL_RATIO)

        indices = np.random.RandomState(42).permutation(n_total)

        train_idx = indices[:n_train]
        val_idx = indices[n_train:n_train + n_val]
        test_idx = indices[n_train + n_val:]

        return {
            "train": (X[train_idx], y[train_idx]),
            "val": (X[val_idx], y[val_idx]),
            "test": (X[test_idx], y[test_idx]),
        }

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """完整预处理流水线"""
        print("[预处理] 提取时间特征...")
        df = self.extract_time_features(df)

        print("[预处理] 添加滞后特征...")
        df = self.add_lag_features(df)

        # 标准化数值特征
        numeric_cols = ["hour", "is_morning_peak", "is_evening_peak", "is_noon_peak"]
        numeric_cols += [c for c in numeric_cols if c in df.columns]
        if len(numeric_cols) > 0 and all(c in df.columns for c in numeric_cols):
            pass  # 可选：对部分列做标准化

        print(f"[预处理] 完成，特征维度: {len(df.columns)}")
        return df


def main():
    """预处理主流程"""
    data_path = PROCESSED_DATA_DIR / "passenger_flow.csv"

    if not data_path.exists():
        print("[错误] 未找到客流数据，请先运行 gtfs_parser.py")
        return

    print("=" * 60)
    print("数据预处理与特征工程")
    print("=" * 60)

    df = pd.read_csv(data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    print(f"[输入] 加载 {len(df)} 条原始记录")

    preprocessor = DataPreprocessor()
    processed_df = preprocessor.fit_transform(df)

    output_path = PROCESSED_DATA_DIR / "processed_data.csv"
    processed_df.to_csv(output_path, index=False)

    print(f"[完成] 处理后数据已保存至: {output_path}")

    # 统计信息
    feature_cols = [c for c in processed_df.columns
                    if c not in ("datetime", "date")]
    print(f"\n[统计] 特征列表 ({len(feature_cols)} 个):")
    for f in sorted(feature_cols):
        print(f"  - {f}")


if __name__ == "__main__":
    main()
