# 城市公交智能调度优化系统

基于客流预测的绿色排班方案 — 2026年辽宁省大学生交通科技大赛参赛作品

## 项目简介

本系统利用 LSTM 深度学习模型预测公交客流，结合 NSGA-II 多目标遗传算法优化排班方案，
在最小化乘客等待时间的同时降低碳排放，实现公交运营的智能化与绿色化。

## 技术栈

- **客流预测**：PyTorch LSTM + XGBoost
- **排班优化**：NSGA-II 多目标遗传算法（DEAP）
- **后端**：FastAPI
- **前端**：Vue 3 + Element Plus + ECharts

## 快速开始

```bash
# 1. 安装依赖
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. 数据处理
python src/data/gtfs_parser.py
python src/data/preprocess.py

# 3. 训练模型
python src/prediction/train.py

# 4. 运行优化
python src/optimization/nsga2_scheduler.py

# 5. 启动后端
uvicorn src.api.app:app --reload --port 8000

# 6. 启动前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
bus-scheduling-optimization/
├── data/           # 数据存储
├── models/         # 训练好的模型
├── src/
│   ├── data/           # 数据处理
│   ├── prediction/     # 客流预测
│   ├── optimization/   # 排班优化
│   ├── api/            # 后端API
│   └── utils/          # 工具函数
├── frontend/       # Vue.js前端
├── notebooks/      # 探索性分析
└── docs/           # 文档
```
