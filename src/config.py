"""项目配置文件"""
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).resolve().parent.parent  # src/config.py -> bus-scheduling-optimization/
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"
MODEL_DIR = BASE_DIR / "models"

# 数据配置
GTFS_DATA_URL = "https://transitfeeds.com/p/mta-new-york-city-transit/2"  # NYC MTA GTFS
TIME_WINDOW_MINUTES = 30  # 客流时间窗口（分钟）
TRAIN_RATIO = 0.7
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# LSTM模型配置
LSTM_CONFIG = {
    "input_size": 10,        # 特征数量
    "hidden_size": 128,      # 隐藏层大小
    "num_layers": 2,         # LSTM层数
    "output_size": 1,        # 输出维度
    "dropout": 0.2,          # Dropout率
    "sequence_length": 12,   # 输入序列长度（12个时间窗口 = 6小时）
    "batch_size": 64,
    "learning_rate": 0.001,
    "num_epochs": 50,
    "patience": 10,          # Early stopping patience
}

# 优化算法配置
OPTIMIZATION_CONFIG = {
    "population_size": 100,
    "num_generations": 200,
    "crossover_prob": 0.9,
    "mutation_prob": 0.1,
    "min_headway": 3,        # 最小发车间隔（分钟）
    "max_headway_peak": 15,  # 高峰最大发车间隔（分钟）
    "max_headway_offpeak": 30,  # 平峰最大发车间隔（分钟）
    "fleet_size": 20,        # 可用车辆数（真实约束）
    "driver_max_hours": 8,   # 驾驶员单班最大时长
    "cost_per_km": 8.5,       # 每公里运营成本（元，含燃料/电耗+折旧）
    "driver_wage_per_hour": 45.0,  # 驾驶员时薪（元）
}

# 碳排放系数 (kg CO2 / km)
CARBON_EMISSION = {
    "large_bus": 1.2,    # 大型公交车
    "medium_bus": 0.8,   # 中型公交车
    "large_bus_capacity": 80,   # 大型车额定载客
    "medium_bus_capacity": 40,  # 中型车额定载客
}

# 公交线路配置
BUS_ROUTE = {
    "total_stops": 20,          # 线路站点数
    "route_length_km": 15.0,    # 线路长度（公里）
    "operating_hours": 16,      # 运营时长（小时，5:00-21:00）
    "avg_speed_kmh": 20,        # 平均运营速度
}

# API配置
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
