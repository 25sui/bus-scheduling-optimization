"""
NSGA-II 多目标排班优化器（升级版：三目标 + 约束处理）

使用DEAP库实现非支配排序遗传算法(NSGA-II)，
同时优化三个目标：
  目标1：最小化乘客平均等待时间
  目标2：最小化总碳排放量
  目标3：最小化总运营成本

支持真实约束：车辆数约束（惩罚函数法）。
优化结果持久化保存到 JSON 文件。
"""

import numpy as np
import random
import json
from datetime import datetime
from pathlib import Path
from deap import base, creator, tools, algorithms

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.config import OPTIMIZATION_CONFIG, BUS_ROUTE, CARBON_EMISSION
from src.optimization.carbon_calc import CarbonCalculator



# ── 全局：只需创建一次 DEAP 类型 ─────────────────────────────────────

def _ensure_creator():
    """确保 DEAP creator 类型已注册（全局只注册一次）。"""
    if not hasattr(creator, "FitnessMin"):
        # 三目标：(-等待时间, -碳排放, -运营成本)
        creator.create("FitnessMin", base.Fitness, weights=(-1.0, -1.0, -1.0))
    if not hasattr(creator, "Individual"):
        creator.create("Individual", list, fitness=creator.FitnessMin)


# ── 核心调度器类 ─────────────────────────────────────────────────────────────

class NSGA2Scheduler:
    """NSGA-II 公交排班优化器（三目标 + 约束）"""

    def __init__(self):
        self.cfg = OPTIMIZATION_CONFIG.copy()
        self.route_cfg = BUS_ROUTE.copy()
        self.carbon_calc = CarbonCalculator(CARBON_EMISSION)
        self.num_time_slots = int(self.route_cfg["operating_hours"] * 60 / 30)
        self._result_dir = Path(__file__).resolve().parent.parent.parent / "models" / "optimization_runs"
        self._result_dir.mkdir(parents=True, exist_ok=True)
        _ensure_creator()
        self._setup_toolbox()

    # ── 工具箱设置 ─────────────────────────────────────────────────────────

    def _setup_toolbox(self):
        """初始化遗传算法工具箱"""
        self.toolbox = base.Toolbox()

        # 基因：每个时间窗口的发车间隔（分钟）
        # 修复：初始化范围使用 max_headway_peak，避免初始种群碳排放过高
        self.toolbox.register(
            "attr_headway", random.randint,
            self.cfg["min_headway"],
            self.cfg["max_headway_peak"]
        )

        # 个体：num_time_slots 个发车间隔值
        self.toolbox.register(
            "individual", tools.initRepeat,
            creator.Individual,
            self.toolbox.attr_headway,
            self.num_time_slots
        )

        # 种群
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)

        # 遗传算子（SBX有界交叉 + 有界多项式变异）
        eta = 20.0
        min_h = self.cfg["min_headway"]
        max_h = self.cfg["max_headway_offpeak"]
        n = self.num_time_slots
        # low/up 数组：每个基因（时段）的合法边界
        low = [float(min_h)] * n
        up  = [float(max_h)] * n

        # cxSimulatedBinaryBounded：有界SBX交叉（确保offspring在边界内）
        self.toolbox.register(
            "mate", tools.cxSimulatedBinaryBounded,
            eta=eta, low=low, up=up
        )
        # mutPolynomialBounded：有界多项式变异（自身处理边界）
        self.toolbox.register(
            "mutate", tools.mutPolynomialBounded,
            eta=eta, indpb=0.2, low=low, up=up
        )
        self.toolbox.register("select", tools.selNSGA2)
        self.toolbox.register("evaluate", self._evaluate_individual)

        # 额外保险：装饰器再次裁剪（防止边界遗漏）
        def _make_boundary_repair(min_val, max_val):
            def _repair_decorator(func):
                def _wrapper(*args, **kwargs):
                    offspring = func(*args, **kwargs)
                    # offspring 是元组 (child1, child2) 或 (mutant,)
                    for ind in offspring:
                        for i in range(len(ind)):
                            ind[i] = int(np.clip(round(float(ind[i]), 0), min_val, max_val))
                    return offspring  # ← 必须返回修改后的 offspring
                return _wrapper
            return _repair_decorator

        self.toolbox.decorate("mate", _make_boundary_repair(min_h, max_h))
        self.toolbox.decorate("mutate", _make_boundary_repair(min_h, max_h))

    # ── 遗传算子细节 ─────────────────────────────────────────────────────

    def _mutate_headway(self, individual, indpb: float):
        """自定义变异：在合理范围内随机调整，并修复越界。"""
        for i in range(len(individual)):
            if random.random() < indpb:
                is_peak = self._is_peak_hour(i)
                max_h = self.cfg["max_headway_peak"] if is_peak else self.cfg["max_headway_offpeak"]
                min_h = self.cfg["min_headway"]
                delta = random.randint(-3, 3)
                individual[i] = int(np.clip(individual[i] + delta, min_h, max_h))
        return (individual,)

    @staticmethod
    def _is_peak_hour(time_slot_idx: int) -> bool:
        """判断是否高峰时段"""
        hour = (time_slot_idx * 30) / 60.0 + 5  # 从5点开始
        return (7 <= hour < 9) or (17 <= hour < 19)

    # ── 约束计算 ────────────────────────────────────────────────────────

    def _calc_total_trips(self, schedule: list) -> int:
        """计算总发车趟数"""
        total = 0
        for h in schedule:
            if h <= 0:
                continue
            # 每30分钟窗口内的发车次数
            trips = max(1, int(30 / h))
            total += trips
        return total

    def _calc_operating_cost(self, schedule: list) -> float:
        """计算总运营成本（元）"""
        total_trips = self._calc_total_trips(schedule)
        total_distance = total_trips * self.route_cfg["route_length_km"]

        # 燃料/电费
        cost_distance = total_distance * self.cfg["cost_per_km"]

        # 驾驶员薪资（简化：每趟平均1.5小时，按 `driver_wage_per_hour` 计算）
        total_driver_hours = total_trips * (self.route_cfg["route_length_km"] / self.route_cfg["avg_speed_kmh"])
        driver_cost = total_driver_hours * self.cfg["driver_wage_per_hour"]

        return cost_distance + driver_cost

    def _vehicle_penalty(self, schedule: list) -> float:
        """车辆数约束惩罚（若总趟数 > 车队规模）。
        返回惩罚值（0 表示无约束违反）。
        """
        total_trips = self._calc_total_trips(schedule)
        fleet = self.cfg["fleet_size"]
        if total_trips <= fleet:
            return 0.0
        # 超出部分每趟惩罚 50 元（可调）
        return (total_trips - fleet) * 50.0

    # ── 目标函数评估 ─────────────────────────────────────────────────

    def _evaluate_individual(self, individual: list) -> tuple:
        """
        评估个体的三目标函数值。
        返回 (waiting_time, carbon_emission, operating_cost)，
        均为最小化目标。
        """
        # 防御性处理：裁剪到合法范围并取整
        min_h = self.cfg["min_headway"]
        max_h = self.cfg["max_headway_offpeak"]
        schedule = np.array([
            int(np.clip(round(float(g), 0), min_h, max_h))
            for g in individual
        ], dtype=int)

        # 目标1：乘客平均等待时间
        avg_wait = self._calc_avg_waiting_time(schedule)

        # 目标2：总碳排放
        carbon_result = self.carbon_calc.calculate_daily_emission(
            schedule, self.route_cfg["route_length_km"], self.route_cfg["total_stops"]
        )
        total_carbon = carbon_result["total_emission_kg"]

        # 目标3：总运营成本
        operating_cost = self._calc_operating_cost(schedule)

        # 约束惩罚（仅加在运营成本上，不影响等待时间和碳排放目标）
        penalty = self._vehicle_penalty(schedule)
        operating_cost += penalty

        return (avg_wait, total_carbon, operating_cost)

    def _calc_avg_waiting_time(self, schedule: np.ndarray) -> float:
        """计算乘客平均等待时间（加权）"""
        total_wait = 0.0
        total_passenger = 0.0

        for i, headway in enumerate(schedule):
            if headway <= 0:
                continue
            hour = (i * 30) / 60.0 + 5
            passenger_weight = self._estimate_passengers(hour)

            # 平均等待时间 = 发车间隔 / 2（均匀到达假设）
            wait_time = headway / 2.0
            total_wait += wait_time * passenger_weight
            total_passenger += passenger_weight

        if total_passenger == 0:
            return 999.0

        return round(total_wait / total_passenger, 3)

    @staticmethod
    def _estimate_passengers(hour: float) -> float:
        """估算某小时段的相对客流量"""
        if 7 <= hour < 9:
            return 80.0
        elif 17 <= hour < 19:
            return 70.0
        elif 11 <= hour < 13:
            return 50.0
        elif hour < 6 or hour > 20:
            return 10.0
        else:
            return 30.0

    # ── 主优化流程 ──────────────────────────────────────────────────

    def run(self) -> dict:
        """
        执行 NSGA-II 三目标优化。

        Returns:
            result: 包含 Pareto 前沿、推荐解等信息的字典
        """
        print("=" * 60)
        print("[NSGA-II] 开始三目标优化...")
        print(f"  种群大小: {self.cfg['population_size']}")
        print(f"  迭代代数: {self.cfg['num_generations']}")
        print(f"  时间窗口数: {self.num_time_slots}")
        print(f"  优化目标: 等待时间 + 碳排放 + 运营成本")
        print(f"  车辆数约束: ≤ {self.cfg['fleet_size']} 趟/日")
        print("=" * 60)

        pop = self.toolbox.population(n=self.cfg["population_size"])
        hof = tools.ParetoFront()  # Pareto 最优前沿

        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("std", np.std, axis=0)

        algorithms.eaMuPlusLambda(
            pop, self.toolbox,
            mu=self.cfg["population_size"],
            lambda_=self.cfg["population_size"],
            cxpb=self.cfg["crossover_prob"],
            mutpb=self.cfg["mutation_prob"],
            ngen=self.cfg["num_generations"],
            stats=stats,
            halloffame=hof,
            verbose=True,
        )

        # 整理 Pareto 前沿解
        pareto_solutions = []
        for ind in hof.items:
            # 防御性处理：裁剪基因值到合法范围并取整（与 _evaluate_individual 一致）
            min_h = self.cfg["min_headway"]
            max_h = self.cfg["max_headway_offpeak"]
            clipped_schedule = [
                int(np.clip(round(float(g), 0), min_h, max_h))
                for g in ind
            ]
            pareto_solutions.append({
                "schedule": clipped_schedule,
                "waiting_time": round(ind.fitness.values[0], 3),
                "carbon_emission": round(ind.fitness.values[1], 2),
                "operating_cost": round(ind.fitness.values[2], 2),
            })

        # 计算基线方案（均匀10分钟间隔，模拟传统固定排班）
        # 这种基线的特点：平峰和低峰时段发车偏多→碳排放偏高，给优化留出空间
        # 优化策略：高峰加密+平峰拉长→同时降低等待时间和碳排放
        baseline_schedule = [10] * self.num_time_slots
        baseline_metrics = self._evaluate_individual(baseline_schedule)
        baseline_wait = baseline_metrics[0]
        baseline_carbon = baseline_metrics[1]
        self.baseline_carbon = baseline_carbon  # 保存为实例变量，供 _select_recommended 使用
        print(f"[基线方案] 均匀 10 分钟间隔（传统固定排班）:")
        print(f"  等待时间: {baseline_wait:.3f} 分钟")
        print(f"  碳排放:   {baseline_carbon:.2f} kg CO2")
        print(f"  运营成本:   {baseline_metrics[2]:.2f} 元")

        # 选择推荐方案（传入动态基线）
        recommended = self._select_recommended(pareto_solutions, baseline_wait, baseline_carbon)
        
        # Fallback：如果推荐方案为空（没有满足约束的解），选择综合权衡最优的解
        if not recommended:
            print(f"[Fallback] 没有找到双改善解，选择综合评分最高的解")
            # 综合评分 = 等待时间改善率 × 0.5 - 碳排放增加率 × 0.5
            # 即：优先改善等待时间，同时惩罚碳排放增加
            for s in pareto_solutions:
                wait_red = max(0, (baseline_wait - s["waiting_time"]) / baseline_wait)
                carbon_change = (s["carbon_emission"] - baseline_carbon) / baseline_carbon  # 正值=增加
                s["_fallback_score"] = wait_red * 0.5 - max(0, carbon_change) * 0.5
            best = max(pareto_solutions, key=lambda s: s["_fallback_score"])
            recommended = best.copy()
            recommended["selection_method"] = "balanced_fallback"
            recommended["warning"] = f"未找到同时改善等待时间和碳排放的解，选择了综合最优方案"

        # 为推荐方案计算改善率字段
        if recommended:
            rec_wait = recommended["waiting_time"]
            rec_carbon = recommended["carbon_emission"]
            # 改善率 = (基线 - 推荐) / 基线，正数表示改善
            recommended["wait_reduction"] = round((baseline_wait - rec_wait) / max(baseline_wait, 1e-6), 4)
            recommended["carbon_reduction"] = round((baseline_carbon - rec_carbon) / max(baseline_carbon, 1e-6), 4)

        result = {
            "pareto_front": pareto_solutions,
            "recommended": recommended,
            "baseline": {"waiting_time": round(baseline_wait, 3), "carbon_emission": round(baseline_carbon, 2)},
            "num_pareto": len(pareto_solutions),
            "config": {
                "pop_size": self.cfg["population_size"],
                "generations": self.cfg["num_generations"],
                "time_slots": self.num_time_slots,
                "objectives": ["waiting_time", "carbon_emission", "operating_cost"],
                "fleet_size": self.cfg["fleet_size"],
            },
        }

        print(f"\n[完成] Pareto 最优解数: {len(pareto_solutions)}")
        if recommended:
            print(f"  推荐方案:")
            print(f"    等待时间: {recommended['waiting_time']:.3f} 分钟")
            print(f"    碳排放:   {recommended['carbon_emission']:.2f} kg CO2")
            print(f"    运营成本:   {recommended['operating_cost']:.2f} 元")
            if "wait_reduction" in recommended:
                print(f"    等待改善:   {recommended['wait_reduction']*100:.1f}%")
                print(f"    碳减排率:   {recommended['carbon_reduction']*100:.1f}%")
                print(f"    选择方法:   {recommended.get('selection_method', 'unknown')}")

        # 持久化保存
        self._save_result(result)
        return result

    # ── 推荐方案选择 ─────────────────────────────────────────────

    def _select_recommended(self, solutions: list, 
                                 baseline_wait: float = None, 
                                 baseline_carbon: float = None) -> dict:
        """
        从 Pareto 前沿中选择推荐方案（平衡等待时间和碳排放改善）。
        
        策略：
        1. 优先选择"双改善"解（等待时间↓ AND 碳排放↓）
        2. 若无双改善解，选择综合评分最高的解
        3. 若没有满足碳排放约束的解，放宽约束到基线的1.1倍
        """
        if not solutions:
            return {}
        
        # 使用动态基线
        if baseline_wait is None:
            baseline_wait = 7.0
        if baseline_carbon is None:
            baseline_carbon = 1152.0
        
        # 防御性过滤：移除无效解（等待时间或碳排放为0/负值）
        valid = [s for s in solutions 
                 if s["waiting_time"] > 0 and s["carbon_emission"] > 0]
        if not valid:
            valid = solutions  # 如果都无效，保留原始列表
        
        # 分级约束：先严格，后放宽
        constraint_levels = [
            ("strict", baseline_carbon * 0.95),  # 级别1：碳排放 ≤ 基线 × 0.95（必须减排）
            ("strict2", baseline_carbon * 1.0),   # 级别2：碳排放 ≤ 基线
            ("relaxed", baseline_carbon * 1.1), # 级别3：碳排放 ≤ 基线 × 1.1
        ]
        
        for level_name, carbon_threshold in constraint_levels:
            # 当前级别的可行解
            feasible = [s for s in valid 
                        if s["carbon_emission"] <= carbon_threshold]
            
            if not feasible:
                continue  # 当前级别无解，放宽约束
            
            # 在可行解中，优先选择"双改善"解（等待时间↓ AND 碳排放↓）
            better = [s for s in feasible
                      if s["waiting_time"] < baseline_wait 
                      and s["carbon_emission"] < baseline_carbon]
            
            if better:
                # 有双改善解：选择综合评分最高的
                # 评分 = 等待时间改善率 × 0.4 + 碳排放改善率 × 0.6
                for s in better:
                    wait_red = (baseline_wait - s["waiting_time"]) / baseline_wait
                    carbon_red = (baseline_carbon - s["carbon_emission"]) / baseline_carbon
                    s["_score"] = wait_red * 0.4 + carbon_red * 0.6
                
                best = max(better, key=lambda s: s["_score"])
                rec = best.copy()
                rec["selection_method"] = f"dual_improvement_{level_name}"
                return rec
            
            # 没有双改善解：选择"单改善"解（至少改善一个目标）
            improved = [s for s in feasible
                        if s["waiting_time"] < baseline_wait 
                        or s["carbon_emission"] < baseline_carbon]
            
            if improved:
                # 选择改善幅度最大的解
                for s in improved:
                    wait_red = max(0, (baseline_wait - s["waiting_time"]) / baseline_wait)
                    carbon_red = max(0, (baseline_carbon - s["carbon_emission"]) / baseline_carbon)
                    s["_score"] = wait_red * 0.4 + carbon_red * 0.6
                
                best = max(improved, key=lambda s: s["_score"])
                rec = best.copy()
                rec["selection_method"] = f"single_improvement_{level_name}"
                return rec
            
            # 当前级别没有改善解：放宽到下一级别
        
        # 所有级别都失败：返回空字典（让 run() 的 fallback 处理）
        print(f"[警告] 没有找到比基线更好的解（基线: wait={baseline_wait:.3f}, carbon={baseline_carbon:.2f}）")
        return {}

    def _save_result(self, result: dict):
        """保存优化结果到 JSON 文件（models/optimization_runs/）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self._result_dir / f"run_{timestamp}.json"

        # 裁剪：Pareto 前沿只保存前 50 个解（减少文件体积）
        save_data = {
            "timestamp": timestamp,
            "config": result["config"],
            "num_pareto": result["num_pareto"],
            "recommended": result["recommended"],
            "pareto_front": result["pareto_front"][:50],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        print(f"[保存] 优化结果已保存: {filepath.name}")
        return str(filepath)


# ── CLI 入口 ──────────────────────────────────────────────────────────────

def main():
    """运行优化"""
    scheduler = NSGA2Scheduler()
    result = scheduler.run()
    return result


if __name__ == "__main__":
    main()
