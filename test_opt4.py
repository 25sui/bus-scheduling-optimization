import sys
sys.path.insert(0, 'src')
from optimization.nsga2_scheduler import NSGA2Scheduler

print("=" * 60)
print("Start optimization test...")
print("=" * 60)

scheduler = NSGA2Scheduler()
scheduler.cfg['population_size'] = 20
scheduler.cfg['num_generations'] = 10

result = scheduler.run()

print("\n" + "=" * 60)
print("Optimization completed!")
print("=" * 60)

print(f"\nBaseline:")
print(f"  Waiting time: {result['baseline']['waiting_time']:.3f} min")
print(f"  Carbon emission: {result['baseline']['carbon_emission']:.2f} kg")

print(f"\nPareto front: {result['num_pareto']} solutions")

rec = result.get('recommended', {})
if rec:
    print(f"\nRecommended solution:")
    print(f"  Waiting time: {rec['waiting_time']:.3f} min")
    print(f"  Carbon emission: {rec['carbon_emission']:.2f} kg")
    print(f"  Selection method: {rec.get('selection_method', 'N/A')}")
    
    baseline_c = result['baseline']['carbon_emission']
    threshold = baseline_c * 1.5
    print(f"\nConstraint check:")
    print(f"  Baseline carbon: {baseline_c:.2f} kg")
    print(f"  Threshold (150%): {threshold:.2f} kg")
    print(f"  Recommended carbon: {rec['carbon_emission']:.2f} kg")
    print(f"  Satisfies constraint: {rec['carbon_emission'] <= threshold}")
else:
    print("\nRecommended solution: EMPTY (no solution satisfies constraints)")
    
    # Debug: show Pareto front stats
    pareto = result['pareto_front']
    carbons = [s['carbon_emission'] for s in pareto]
    waits = [s['waiting_time'] for s in pareto]
    print(f"\nPareto front stats:")
    print(f"  Carbon range: {min(carbons):.2f} - {max(carbons):.2f} kg")
    print(f"  Waiting time range: {min(waits):.3f} - {max(waits):.3f} min")
