import sys
sys.path.insert(0, 'src')
from optimization.nsga2_scheduler import NSGA2Scheduler

print("=" * 60)
print("开始优化测试...")
print("=" * 60)

scheduler = NSGA2Scheduler()
# 修改配置
scheduler.config['population_size'] = 20
scheduler.config['generations'] = 10

result = scheduler.run()

print("\n" + "=" * 60)
print("优化完成！")
print("=" * 60)

print(f"\n基线方案:")
print(f"  等待时间: {result['baseline']['waiting_time']:.3f} 分钟")
print(f"  碳排放: {result['baseline']['carbon_emission']:.2f} kg")

print(f"\nPareto 前沿: {result['num_pareto']} 个解")

rec = result.get('recommended', {})
if rec:
    print(f"\n推荐方案:")
    print(f"  等待时间: {rec['waiting_time']:.3f} 分钟")
    print(f"  碳排放: {rec['carbon_emission']:.2f} kg")
    print(f"  选择方法: {rec.get('selection_method', 'N/A')}")
else:
    print("\n推荐方案: 空（没有满足约束的解）")
