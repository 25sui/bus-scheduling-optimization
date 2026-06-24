-- ============================================================
-- 公交智能调度优化系统 数据库设计
-- PostgreSQL + PostGIS + TimescaleDB
-- 适用：Phase 1 数据真实化 + 持久化存储
-- ============================================================

-- 启用必要扩展
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- TimescaleDB 可选（用于时序客流数据）：CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- 第一部分：GTFS 标准表（真实公交数据）
-- ============================================================

-- 公交线路表
CREATE TABLE gtfs_routes (
    route_id VARCHAR(50) PRIMARY KEY,
    agency_id VARCHAR(50),
    route_short_name VARCHAR(50),
    route_long_name TEXT,
    route_type INTEGER NOT NULL DEFAULT 3,  -- 3=公交
    route_color VARCHAR(10),
    route_text_color VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 站点表（含PostGIS空间字段）
CREATE TABLE gtfs_stops (
    stop_id VARCHAR(50) PRIMARY KEY,
    stop_code VARCHAR(50),
    stop_name VARCHAR(200) NOT NULL,
    stop_desc TEXT,
    stop_lat DOUBLE PRECISION,
    stop_lon DOUBLE PRECISION,
    stop_geom GEOGRAPHY(Point, 4326),  -- PostGIS空间字段
    zone_id VARCHAR(50),
    stop_url TEXT,
    location_type INTEGER DEFAULT 0,
    parent_station VARCHAR(50),
    wheelchair_boarding INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 班次表（每个班次对应一条trip）
CREATE TABLE gtfs_trips (
    trip_id VARCHAR(50) PRIMARY KEY,
    route_id VARCHAR(50) NOT NULL REFERENCES gtfs_routes(route_id),
    service_id VARCHAR(50) NOT NULL,  -- 关联日历（工作日/周末）
    trip_headsign VARCHAR(200),
    trip_short_name VARCHAR(50),
    direction_id INTEGER,
    block_id VARCHAR(50),
    shape_id VARCHAR(50),
    wheelchair_accessible INTEGER,
    bikes_allowed INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 到站时刻表（核心大表，需要索引优化）
CREATE TABLE gtfs_stop_times (
    trip_id VARCHAR(50) NOT NULL REFERENCES gtfs_trips(trip_id),
    arrival_time TIME,
    departure_time TIME,
    stop_id VARCHAR(50) NOT NULL REFERENCES gtfs_stops(stop_id),
    stop_sequence INTEGER NOT NULL,
    pickup_type INTEGER DEFAULT 0,
    drop_off_type INTEGER DEFAULT 0,
    shape_dist_traveled DOUBLE PRECISION,
    PRIMARY KEY (trip_id, stop_sequence)
);

-- 服务日历表（工作日/周末模式）
CREATE TABLE gtfs_calendar (
    service_id VARCHAR(50) PRIMARY KEY,
    monday BOOLEAN DEFAULT FALSE,
    tuesday BOOLEAN DEFAULT FALSE,
    wednesday BOOLEAN DEFAULT FALSE,
    thursday BOOLEAN DEFAULT FALSE,
    friday BOOLEAN DEFAULT FALSE,
    saturday BOOLEAN DEFAULT FALSE,
    sunday BOOLEAN DEFAULT FALSE,
    start_date DATE,
    end_date DATE
);

-- 线路形状表（可选，用于地图上绘制线路走向）
CREATE TABLE gtfs_shapes (
    shape_id VARCHAR(50) NOT NULL,
    shape_pt_lat DOUBLE PRECISION NOT NULL,
    shape_pt_lon DOUBLE PRECISION NOT NULL,
    shape_pt_sequence INTEGER NOT NULL,
    shape_dist_traveled DOUBLE PRECISION,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);

-- ============================================================
-- 第二部分：客流数据表（时序数据核心）
-- ============================================================

-- 客流事实表（每半小时聚合格式，核心业务表）
CREATE TABLE passenger_flow (
    id BIGSERIAL PRIMARY KEY,
    trip_id VARCHAR(50) NOT NULL,
    stop_id VARCHAR(50) NOT NULL,
    stop_sequence INTEGER NOT NULL,
    time_window_start TIMESTAMP NOT NULL,  -- 时间窗口起始（如 2026-06-20 07:00:00）
    time_window_index INTEGER NOT NULL,      -- 0-31（每天32个窗口）
    calendar_date DATE NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    passenger_count INTEGER NOT NULL,
    load_factor DOUBLE PRECISION,            -- 满载率（可选）
    data_source VARCHAR(50) DEFAULT 'ic_card',  -- 数据来源：ic_card/gps/synthetic
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (trip_id) REFERENCES gtfs_trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES gtfs_stops(stop_id)
);

-- 客流聚合表（按时间窗口预聚合，加速查询）
CREATE TABLE passenger_flow_agg (
    id BIGSERIAL PRIMARY KEY,
    stop_id VARCHAR(50) NOT NULL,
    time_window_index INTEGER NOT NULL,
    calendar_date DATE NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    total_passengers INTEGER NOT NULL,
    avg_passengers DOUBLE PRECISION,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (stop_id, time_window_index, calendar_date),
    FOREIGN KEY (stop_id) REFERENCES gtfs_stops(stop_id)
);

-- ============================================================
-- 第三部分：预测模型相关表
-- ============================================================

-- 模型记录表
CREATE TABLE prediction_models (
    model_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name VARCHAR(100) NOT NULL,       -- 'LSTM', 'XGBoost', 'ST-GCN'
    model_version VARCHAR(50) NOT NULL,      -- 'v1.0', 'v20260620'
    model_path TEXT NOT NULL,                -- 模型文件存储路径
    mae DOUBLE PRECISION,
    rmse DOUBLE PRECISION,
    mape DOUBLE PRECISION,
    training_days INTEGER,                   -- 训练用天数
    trained_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT FALSE,         -- 是否为当前线上模型
    created_by VARCHAR(100)
);

-- 预测结果表（存储模型预测输出，避免重复预测）
CREATE TABLE prediction_results (
    id BIGSERIAL PRIMARY KEY,
    model_id UUID NOT NULL REFERENCES prediction_models(model_id),
    stop_id VARCHAR(50) NOT NULL,
    time_window_start TIMESTAMP NOT NULL,
    predicted_count DOUBLE PRECISION NOT NULL,
    actual_count DOUBLE PRECISION,           -- 事后可填入实际值用于评估
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (stop_id) REFERENCES gtfs_stops(stop_id)
);

-- ============================================================
-- 第四部分：优化相关表
-- ============================================================

-- 优化任务表（每次触发NSGA-II的记录）
CREATE TABLE optimization_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_name VARCHAR(200),
    route_id VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    population_size INTEGER DEFAULT 100,
    num_generations INTEGER DEFAULT 200,
    status VARCHAR(50) DEFAULT 'pending',   -- pending/running/completed/failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_pareto_solutions INTEGER,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (route_id) REFERENCES gtfs_routes(route_id)
);

-- Pareto最优解详情表
CREATE TABLE optimization_pareto_solutions (
    solution_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES optimization_runs(run_id) ON DELETE CASCADE,
    solution_index INTEGER NOT NULL,          -- Pareto前沿中的序号
    avg_waiting_time DOUBLE PRECISION NOT NULL,
    total_carbon_emission DOUBLE PRECISION NOT NULL,
    total_trips INTEGER NOT NULL,
    total_operating_cost DOUBLE PRECISION,   -- 第三目标（可选）
    is_recommended BOOLEAN DEFAULT FALSE,     -- 是否为TOPSIS推荐方案
    topsis_score DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 排班方案详情表（每个solution对应的各时段发车间隔）
CREATE TABLE optimization_schedules (
    id BIGSERIAL PRIMARY KEY,
    solution_id UUID NOT NULL REFERENCES optimization_pareto_solutions(solution_id) ON DELETE CASCADE,
    time_window_index INTEGER NOT NULL,       -- 0-31
    headway_minutes INTEGER NOT NULL,         -- 发车间隔（分钟）
    bus_type VARCHAR(20) DEFAULT 'large',    -- 'large'/'medium'
    estimated_carbon_kg DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 第五部分：仿真相关表
-- ============================================================

-- 仿真运行记录表
CREATE TABLE simulation_runs (
    sim_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_name VARCHAR(200),
    solution_id UUID NOT NULL REFERENCES optimization_pareto_solutions(solution_id),
    baseline_solution_id UUID REFERENCES optimization_pareto_solutions(solution_id),
    sim_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 仿真结果指标表
CREATE TABLE simulation_metrics (
    id BIGSERIAL PRIMARY KEY,
    sim_id UUID NOT NULL REFERENCES simulation_runs(sim_id) ON DELETE CASCADE,
    time_window_index INTEGER NOT NULL,
    scenario VARCHAR(50) NOT NULL,           -- 'optimized'/'baseline'
    avg_waiting_time DOUBLE PRECISION,
    avg_load_factor DOUBLE PRECISION,
    total_carbon_kg DOUBLE PRECISION,
    total_trips INTEGER,
    passenger_satisfaction DOUBLE PRECISION,  -- 满意度（可选计算）
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 第六部分：系统管理表（Phase 3 多用户）
-- ============================================================

-- 用户表
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(100),
    email VARCHAR(200),
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',  -- 'admin'/'dispatcher'/'viewer'
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 操作日志表
CREATE TABLE operation_logs (
    log_id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(user_id),
    action VARCHAR(100) NOT NULL,             -- 'run_optimization'/'view_report'等
    resource_type VARCHAR(50),                -- 'optimization_run'/'simulation'等
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 第七部分：索引优化
-- ============================================================

-- passenger_flow 核心查询索引
CREATE INDEX idx_passenger_flow_date ON passenger_flow(calendar_date);
CREATE INDEX idx_passenger_flow_stop_date ON passenger_flow(stop_id, calendar_date);
CREATE INDEX idx_passenger_flow_trip_stop ON passenger_flow(trip_id, stop_id);

-- passenger_flow_agg 索引
CREATE INDEX idx_flow_agg_date ON passenger_flow_agg(calendar_date);
CREATE INDEX idx_flow_agg_stop ON passenger_flow_agg(stop_id);

-- prediction_results 索引
CREATE INDEX idx_pred_results_model ON prediction_results(model_id);
CREATE INDEX idx_pred_results_time ON prediction_results(time_window_start);

-- optimization 相关索引
CREATE INDEX idx_opt_runs_route ON optimization_runs(route_id);
CREATE INDEX idx_opt_runs_status ON optimization_runs(status);
CREATE INDEX idx_pareto_run ON optimization_pareto_solutions(run_id);

-- simulation 索引
CREATE INDEX idx_sim_runs_solution ON simulation_runs(solution_id);

-- gtfs_stop_times 查询优化（最关键的大表）
CREATE INDEX idx_stop_times_trip ON gtfs_stop_times(trip_id);
CREATE INDEX idx_stop_times_stop ON gtfs_stop_times(stop_id);

-- ============================================================
-- 第八部分：初始化数据
-- ============================================================

-- 插入默认管理员用户（密码：admin123，正式环境需修改）
-- 密码hash对应 'admin123'，使用 bcrypt
INSERT INTO users (username, password_hash, real_name, role)
VALUES ('admin', '$2b$12$EixZaYUQgWkY6Z6Z6Z6Z6e', '系统管理员', 'admin')
ON CONFLICT (username) DO NOTHING;

-- 插入默认调度员用户（密码：dispatcher123）
INSERT INTO users (username, password_hash, real_name, role)
VALUES ('dispatcher', '$2b$12$EixZaYUQgWkY6Z6Z6Z6Z6e', '调度员', 'dispatcher')
ON CONFLICT (username) DO NOTHING;

-- ============================================================
-- 第九部分：TimescaleDB 时序数据优化（可选）
-- ============================================================
-- 如果已安装 TimescaleDB，可将 passenger_flow 转换为超表：
-- SELECT create_hypertable('passenger_flow', 'time_window_start');

-- ============================================================
-- 第十部分：PostGIS 空间索引
-- ============================================================
CREATE INDEX idx_stops_geom ON gtfs_stops USING GIST(stop_geom);

-- ============================================================
-- 完成提示
-- ============================================================
-- 执行完成后：
-- 1. 验证：\dt 查看所有表
-- 2. 验证PostGIS：SELECT PostGIS_Version();
-- 3. 验证空间索引：\di idx_stops_geom
-- 4. 导入GTFS数据：使用 gtfs_parser.py 重写版
-- 5. 导入客流数据：使用 preprocess.py 重写版
-- ============================================================
