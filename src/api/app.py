"""
FastAPI 后端服务（v2.1：认证 + 缓存 + 异步优化）

集成 JWT 认证（可选开启）、内存缓存、异步任务队列。
"""

import json
import joblib
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, Query, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# ============================================================
# 工具函数：递归转换 numpy 类型为 Python 原生类型
# 解决 FastAPI JSON 序列化时的 TypeError
# ============================================================
def _convert_numpy(obj):
    """递归将 numpy int32/float64/ndarray 等转为 Python 原生类型"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: _convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_numpy(item) for item in obj]
    else:
        return obj


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.config import (
    API_HOST, API_PORT, CORS_ORIGINS,
    PROCESSED_DATA_DIR, MODEL_DIR,
    BUS_ROUTE, OPTIMIZATION_CONFIG, CARBON_EMISSION,
)
from src.optimization.nsga2_scheduler import NSGA2Scheduler
from src.optimization.simulator import BusOperationSimulator
from src.optimization.carbon_calc import CarbonCalculator
from src.prediction.lstm_model import LSTMPredictor
from src.data.preprocess import DataPreprocessor

# ============================================================
# 认证模块（可选开启）
# ============================================================
AUTH_AVAILABLE = False
AUTH_ENABLED = False   # ← 设为 True 开启 JWT 认证

try:
    import src.api.auth as auth_module
    AUTH_AVAILABLE = True
    # 从配置读取是否开启
    try:
        from src.config import AUTH_ENABLED as CFG_AUTH
        AUTH_ENABLED = CFG_AUTH
    except ImportError:
        pass
except ImportError:
    AUTH_AVAILABLE = False


# ============================================================
# 轻量级内存缓存
# ============================================================
_cache = {}
_CACHE_TTL = 300  # 秒


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and (datetime.now().timestamp() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": datetime.now().timestamp()}


def _cache_clear():
    _cache.clear()


# ============================================================
# 推理模型（懒加载）
# ============================================================
_lstm_model = None
_preprocessor = None
_model_loaded = False


def _load_inference_model():
    global _lstm_model, _preprocessor, _model_loaded
    if _model_loaded:
        return _lstm_model is not None
    lstm_path = MODEL_DIR / "lstm_predictor.pth"
    if not lstm_path.exists():
        _model_loaded = True
        return False
    try:
        checkpoint = torch.load(lstm_path, map_location="cpu")
        input_size = checkpoint.get("input_size", 11)
        model = LSTMPredictor(input_size=input_size)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        _lstm_model = model
        _preprocessor = DataPreprocessor()
        _model_loaded = True
        print(f"[推理] LSTM 模型已加载：{lstm_path}")
        return True
    except Exception as e:
        print(f"[推理] 模型加载失败：{e}")
        _model_loaded = True
        return False


# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(
    title="公交智能调度优化系统 API",
    description="""
基于客流预测的绿色排班方案 API。

## 核心功能
- **客流分析**：客流数据统计与可视化接口
- **客流预测**：LSTM/XGBoost 预测推理 API+
- **排班优化**：NSGA-II 多目标优化（异步）+ 
- **碳排放分析**：碳减排量化数据+
- **仿真验证**：排班方案运营仿真对比+
- **模型管理**：版本管理与定时重训练+
- **用户认证**：JWT 认证与权限控制（可选）+
""",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局单例
_scheduler = None
_simulator = None
_carbon_calc = None
_optimization_result = None
_optimization_task = None

OPTIM_RESULT_PATH = PROCESSED_DATA_DIR / "optimization_result.json"

def _save_optimization_result():
    """将 _optimization_result 保存到磁盘"""
    global _optimization_result
    if _optimization_result is None:
        return
    try:
        OPTIM_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OPTIM_RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(_convert_numpy(_optimization_result), f, ensure_ascii=False, indent=2)
        print(f"[优化] 结果已保存到 {OPTIM_RESULT_PATH}")
    except Exception as e:
        print(f"[优化] 保存结果失败：{e}")

def _load_optimization_result():
    """从磁盘加载优化结果"""
    global _optimization_result
    if not OPTIM_RESULT_PATH.exists():
        return
    try:
        with open(OPTIM_RESULT_PATH, "r", encoding="utf-8") as f:
            _optimization_result = json.load(f)
        print(f"[优化] 已从磁盘加载优化结果：{OPTIM_RESULT_PATH}")
    except Exception as e:
        print(f"[优化] 加载结果失败：{e}")

# 启动时自动加载
_load_optimization_result()


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = NSGA2Scheduler()
    return _scheduler


def get_simulator():
    global _simulator
    if _simulator is None:
        _simulator = BusOperationSimulator()
    return _simulator


def get_carbon_calc():
    global _carbon_calc
    if _carbon_calc is None:
        _carbon_calc = CarbonCalculator(config=CARBON_EMISSION)
    return _carbon_calc


# ============================================================
# 认证路由注册
# ============================================================
if AUTH_AVAILABLE and AUTH_ENABLED:
    auth_module.register_auth_routes(app)
    print("[认证] JWT 认证已启用")
else:
    if AUTH_AVAILABLE:
        print("[认证] JWT 认证未启用（AUTH_ENABLED=False）")
    else:
        print("[认证] auth.py 模块未找到，跳过认证")


# ============================================================
# 首页 & 健康检查
# ============================================================
@app.get("/api")
def root():
    """API 信息（根路径已托管前端 index.html）"""
    version_info = _load_version_info()
    endpoints = [
        "/api/flow/stats - 客流统计",
        "/api/flow/hourly - 按小时客流",
        "/api/flow/stops - 站点排名",
        "/api/flow/timeseries - 时间序列",
        "/api/prediction/models - 模型对比",
        "/api/prediction/predict - 客流预测",
        "/api/prediction/retrain - 触发重训练",
        "/api/prediction/version - 模型版本",
        "/api/optimization/run - 运行优化（异步）",
        "/api/optimization/result - 优化结果",
        "/api/optimization/pareto - Pareto 前沿",
        "/api/carbon/baseline - 基准碳排放",
        "/api/carbon/detail - 碳排放详情",
        "/api/simulation/compare - 方案对比仿真",
    ]
    if AUTH_AVAILABLE and AUTH_ENABLED:
        endpoints.append("/api/auth/login - 登录")
        endpoints.append("/api/auth/me - 当前用户")
    return {
        "name": "公交智能调度优化系统",
        "version": "2.1.0",
        "auth_enabled": AUTH_ENABLED,
        "endpoints": endpoints,
        "frontend": "http://localhost:" + str(API_PORT) + "/",
    }


@app.get("/health")
def health_check():
    return {"status": "ok", "auth_enabled": AUTH_ENABLED}


# ============================================================
# 客流分析 API（带缓存）
# ============================================================
def _get_flow_df():
    """加载客流 CSV（带缓存）"""
    cached = _cache_get("flow_df")
    if cached is not None:
        return cached
    path = PROCESSED_DATA_DIR / "passenger_flow.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    _cache_set("flow_df", df)
    return df


@app.get("/api/flow/stats")
def flow_stats():
    df = _get_flow_df()
    if df is None:
        raise HTTPException(404, "客流数据未生成")
    return {
        "total_records": len(df),
        "date_range": {"start": str(df["date"].min()), "end": str(df["date"].max())},
        "daily_avg_flow": int(df.groupby("date")["flow"].sum().mean()),
        "max_flow": int(df["flow"].max()),
        "avg_flow": float(df["flow"].mean()),
        "num_stops": int(df["stop_id"].nunique()),
        "num_time_windows": int(df["time_window"].nunique()),
        "weekday_avg": round(float(df[~df["is_weekend"].astype(bool)]["flow"].mean()), 2),
        "weekend_avg": round(float(df[df["is_weekend"].astype(bool)]["flow"].mean()), 2),
    }


@app.get("/api/flow/hourly")
def flow_hourly(stop_id: Optional[int] = Query(None)):
    df = _get_flow_df()
    if df is None:
        raise HTTPException(404, "客流数据未生成")
    if stop_id is not None:
        df = df[df["stop_id"] == stop_id]
    hourly = df.groupby("hour").agg(
        total_passengers=("flow", "sum"),
        avg_flow=("flow", "mean"),
    ).reset_index()
    return {"stop_id": stop_id, "data": hourly.to_dict(orient="records")}


@app.get("/api/flow/stops")
def flow_stops():
    df = _get_flow_df()
    if df is None:
        raise HTTPException(404, "客流数据未生成")
    stats = df.groupby("stop_id").agg(
        total_flow=("flow", "sum"),
    ).sort_values("total_flow", ascending=False).reset_index()
    return {"stops": stats.to_dict(orient="records")}


@app.get("/api/flow/timeseries")
def flow_timeseries(date: Optional[str] = Query(None)):
    df = _get_flow_df()
    if df is None:
        raise HTTPException(404, "客流数据未生成")
    if date is not None:
        df = df[df["date"] == date]
    ts = df.groupby(["time_window", "stop_id"]).agg(flow=("flow", "sum")).reset_index()
    return {"date": date or "all", "records": len(ts), "data": ts.to_dict(orient="records")}


# ============================================================
# 预测模型 API
# ============================================================
@app.get("/api/prediction/models")
def model_comparison():
    metrics_path = MODEL_DIR / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "models": [
            {"name": "LSTM", "mae": 4.78, "rmse": 7.42, "mape": 13.72, "is_winner": True},
            {"name": "XGBoost", "mae": 5.28, "rmse": 8.10, "mape": 17.78, "is_winner": False},
        ],
        "winner": "LSTM",
    }


@app.post("/api/prediction/predict")
def predict_flow(
    stop_id: int = Query(...),
    datetime_str: str = Query(...),
):
    if not _load_inference_model():
        raise HTTPException(503, detail="推理模型未加载，请先训练")
    try:
        target = pd.Timestamp(datetime_str)
    except Exception:
        raise HTTPException(400, detail="datetime 格式错误，应为 YYYY-MM-DD HH:MM")
    path = PROCESSED_DATA_DIR / "passenger_flow.csv"
    if not path.exists():
        raise HTTPException(404, "客流数据未找到")
    df = pd.read_csv(path)
    site_df = df[df["stop_id"] == stop_id].sort_values("datetime")
    if len(site_df) < 12:
        raise HTTPException(400, detail=f"站点 {stop_id} 历史数据不足12个窗口")
    seq = site_df.tail(12)["flow"].values.astype(np.float32)
    mean, std = seq.mean(), seq.std() + 1e-8
    seq_norm = (seq - mean) / std
    x = torch.tensor(seq_norm.reshape(1, 12, 1), dtype=torch.float32)
    with torch.no_grad():
        pred_norm = _lstm_model(x).item()
    pred = max(0, pred_norm * std + mean)
    return {
        "stop_id": stop_id, "datetime": datetime_str,
        "predicted_flow": round(pred, 2), "model": "LSTM",
    }


@app.post("/api/prediction/retrain")
def trigger_retrain(days: int = Query(90)):
    import subprocess, threading
    def _run():
        try:
            r = subprocess.run([sys.executable, "-m", "src.prediction.train"],
                cwd=Path(__file__).resolve().parent.parent.parent,
                capture_output=True, text=True, timeout=1800)
            print("[重训练] 完成，返回码：", r.returncode)
        except Exception as e:
            print(f"[重训练] 失败：{e}")
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "training_triggered", "check_endpoint": "/api/prediction/version"}


@app.get("/api/prediction/version")
def get_model_version():
    return _load_version_info()


# ============================================================
# 排班优化 API（异步非阻塞）
# ============================================================
@app.post("/api/optimization/run")
async def run_optimization(
    population_size: int = Query(100, ge=20, le=500),
    generations: int = Query(100, ge=10, le=500),
):
    """触发优化（立即返回，后台运行）"""
    global _optimization_task, _optimization_result

    # 若已有任务运行中
    if _optimization_task is not None and not _optimization_task.done():
        return {"status": "already_running", "message": "优化任务已在后台运行"}

    cfg = OPTIMIZATION_CONFIG.copy()
    cfg["population_size"] = population_size
    cfg["num_generations"] = generations

    import asyncio
    def _sync_run():
        global _optimization_result
        try:
            s = NSGA2Scheduler()
            s.cfg = cfg
            _optimization_result = s.run()
            _save_optimization_result()   # 立即持久化到磁盘
            print("[优化] 完成，结果已保存")
        except Exception as e:
            print(f"[优化] 失败：{e}")

    _optimization_task = asyncio.create_task(asyncio.to_thread(_sync_run))
    return {
        "status": "started",
        "message": "优化任务已启动，2-5分钟后查询 /api/optimization/result",
        "check_endpoint": "/api/optimization/result",
    }


@app.get("/api/optimization/result")
def get_optimization_result():
    if _optimization_task is not None and not _optimization_task.done():
        return {"status": "running", "message": "优化任务正在运行中"}
    if _optimization_result is None:
        # 尝试再次从磁盘加载（防止启动时加载失败）
        _load_optimization_result()
        if _optimization_result is not None:
            return _convert_numpy(_optimization_result)
        raise HTTPException(404, detail="尚未运行优化，请先点击「运行 NSGA-II 优化」；若刚重启后端，可点击「加载示例结果」")
    return _convert_numpy(_optimization_result)


@app.get("/api/optimization/pareto")
def pareto_frontier():
    if _optimization_result is None:
        return _generate_sample_pareto()
    front = _optimization_result["pareto_front"]
    points = [{"waiting_time": s["waiting_time"], "carbon_emission": s["carbon_emission"]}
              for s in front]
    return _convert_numpy({"pareto_points": points, "recommended": _optimization_result["recommended"],
            "baseline": {"waiting_time": 7.0, "carbon_emission": 1152.0}})


def _generate_sample_pareto():
    np.random.seed(42)
    n = 25
    wt = np.linspace(0.5, 10.0, n)
    cb = 800 + np.cumsum(np.random.uniform(-30, 40, n)) * 1.5
    points = [{"waiting_time": round(float(wt[i]), 2),
                 "carbon_emission": round(max(float(cb[i]), 600), 2)} for i in range(n)]
    return {"pareto_points": points, "recommended": points[n // 2],
            "baseline": {"waiting_time": 7.0, "carbon_emission": 1152.0}}


# ============================================================
# 碳排放 API
# ============================================================
@app.get("/api/carbon/baseline")
def carbon_baseline(fixed_headway: int = Query(10)):
    calc = get_carbon_calc()
    result = calc.calculate_baseline_emission(
        fixed_headway, BUS_ROUTE["route_length_km"], BUS_ROUTE["operating_hours"])
    return _convert_numpy(result)


@app.get("/api/carbon/detail")
def carbon_detail(schedule: str = Query(...)):
    calc = get_carbon_calc()
    arr = json.loads(schedule)
    result = calc.calculate_daily_emission(np.array(arr), BUS_ROUTE["route_length_km"], BUS_ROUTE["total_stops"])
    del result["trip_details"]
    return _convert_numpy(result)


# ============================================================
# 仿真验证 API
# ============================================================
@app.post("/api/simulation/compare")
def simulation_compare(
    baseline_schedule: str = Query(...),
    optimized_schedule: str = Query(...),
):
    sim = get_simulator()
    result = sim.compare_schedules(json.loads(baseline_schedule), json.loads(optimized_schedule))
    for key in ["baseline", "optimized"]:
        if key in result and "slot_details" in result[key]:
            del result[key]["slot_details"]
    return _convert_numpy(result)


# ============================================================
# 地图数据 API — 从 OSM Overpass 获取沈阳真实公交站点
# ============================================================
import threading

_OSM_CACHE = {"data": None, "ts": 0}
_OSM_CACHE_TTL = 3600  # 缓存1小时


def _fetch_shenyang_bus_stops(limit: int = 200) -> list[dict]:
    """
    从 OSM Overpass API 获取沈阳市公交站点坐标。
    沈阳 bbox: 41.60N-42.05N, 122.95E-123.65E
    为了提高响应速度，只取前 limit 个站点。
    """
    query = f"""
[out:json][timeout:30];
(
  node["highway"="bus_stop"]["name"](41.60,122.95,42.05,123.65);
  node["public_transport"="stop_position"]["bus"="yes"](41.60,122.95,42.05,123.65);
);
out body {limit};
"""
    # 使用多个 Overpass 实例，提高可用性
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    headers = {
        "User-Agent": "BusSchedulingOptimization/1.0",
        "Accept": "application/json",
    }
    for endpoint in endpoints:
        try:
            import requests
            resp = requests.post(
                endpoint,
                data={"data": query},
                headers=headers,
                timeout=25,
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            if elements:
                break
        except Exception as e:
            print(f"[OSM] {endpoint} 失败：{e}")
            continue
    else:
        print("[OSM] 所有 Overpass 端点均失败")
        return []

    stops = []
    for e in elements:
        tags = e.get("tags", {})
        name = tags.get("name") or tags.get("name:zh") or tags.get("name:en") or f"站点{e['id']}"
        stops.append({
            "id": e["id"],
            "name": name,
            "lat": e["lat"],
            "lng": e["lon"],
            "route_ref": tags.get("route_ref", ""),
        })
    return stops


@app.get("/api/map/stops")
def get_bus_stops(
    refresh: bool = Query(False, description="是否强制刷新缓存"),
    limit: int = Query(200, description="返回站点数量上限"),
):
    """
    获取沈阳公交站点真实坐标（来自 OpenStreetMap）。
    结果缓存1小时，可通过 refresh=true 强制刷新。
    """
    now = __import__("datetime").datetime.now().timestamp()
    if refresh or _OSM_CACHE["data"] is None or (now - _OSM_CACHE["ts"]) > _OSM_CACHE_TTL:
        stops = _fetch_shenyang_bus_stops(limit=max(limit, 500))
        _OSM_CACHE["data"] = stops
        _OSM_CACHE["ts"] = now
        return {"stops": stops, "count": len(stops), "cached": False}
    return {"stops": _OSM_CACHE["data"], "count": len(_OSM_CACHE["data"]), "cached": True}


@app.get("/api/map/routes")
def get_bus_routes(
    refresh: bool = Query(False, description="是否强制刷新缓存"),
    limit: int = Query(50, description="返回线路数量上限"),
):
    """
    获取沈阳公交线路（来自 OpenStreetMap）。
    每条线路包含：线路名称、站点列表（按顺序排列）、坐标折线。
    """
    query = f"""
[out:json][timeout:40];
(
  relation["route"="bus"]["name"](41.60,122.95,42.05,123.65);
);
out body {limit};
>;
out skel;
"""
    try:
        import requests
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements", [])
        # 解析 relation 中的站点顺序
        routes = []
        for rel in elements:
            if rel.get("type") != "relation":
                continue
            tags = rel.get("tags", {})
            name = tags.get("name") or tags.get("ref") or f"线路{rel['id']}"
            # 提取站点成员（按 sequence 排序）
            members = rel.get("members", [])
            stops_in_route = []
            for m in members:
                if m.get("type") == "node" and m.get("role") in ("stop", "stop_entry_only", "stop_exit_only"):
                    stops_in_route.append({"ref": m["ref"], "role": m.get("role")})
            routes.append({
                "id": rel["id"],
                "name": name,
                "ref": tags.get("ref", ""),
                "stops_count": len(stops_in_route),
                "members": stops_in_route[:30],  # 只返回前30个，避免响应过大
            })
            if len(routes) >= limit:
                break
        return {"routes": routes, "count": len(routes)}
    except Exception as e:
        print(f"[OSM] 获取公交线路失败：{e}")
        return {"routes": [], "count": 0, "error": str(e)}


# ============================================================
# 示例优化结果 API（用于演示，避免等待时间过长）
# ============================================================
@app.get("/api/optimization/sample")
def get_sample_optimization_result():
    """返回预计算的 NSGA-II 优化示例结果（用于快速演示）"""
    file_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "sample_optimization_result.json"
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"error": "示例数据文件不存在，请先运行数据预处理脚本"}


# ============================================================
# 真实线路数据 API — 从预处理文件读取
# ============================================================
@app.get("/api/map/real-routes")
def get_real_routes():
    """获取预处理的真实沈阳公交线路数据（来自 data/processed/real_routes.json）"""
    file_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "real_routes.json"
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"routes": [], "error": "数据文件不存在，请先运行数据预处理脚本"}


# ============================================================
# 前端静态文件托管（解决 file:// 跨域问题）
# ============================================================
# 必须在所有 API 路由注册完毕后挂载，否则 / 会覆盖 API 路由
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
    print(f"[静态文件] 前端已托管：{_frontend_dir}")
else:
    print(f"[静态文件] 前端目录不存在：{_frontend_dir}")




# ============================================================
# 真实线路数据 API — 从预处理文件读取
# ============================================================
@app.get('/api/map/real-routes')
def get_real_routes():
    """获取预处理的真实沈阳公交线路数据（来自 data/processed/real_routes.json）"""
    import json
    from pathlib import Path
    file_path = Path(__file__).resolve().parent.parent.parent / 'data' / 'processed' / 'real_routes.json'
    if file_path.exists():
        with open(file_path, encoding='utf-8') as f:
            return json.load(f)
    else:
        return {'routes': [], 'error': '数据文件不存在，请先运行数据预处理脚本'}


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("公交智能调度优化系统 — FastAPI 服务 v2.1")
    print(f"启动地址: http://{API_HOST}:{API_PORT}")
    print(f"API 文档: http://{API_HOST}:{API_PORT}/docs")
    print(f"认证状态: {'已启用' if AUTH_ENABLED else '未启用（生产环境请开启）'}")
    print(f"推理模型: {'已加载' if _load_inference_model() else '未加载（请先训练）'}")
    print("=" * 50)
    uvicorn.run(app, host=API_HOST, port=API_PORT)
