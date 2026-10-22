"""T12: WhaleScore theo cửa sổ, nhãn hạ tầng từ T07 và chỉ số T09."""
from src.whale_score import main
from src.whale_score_audit import main as audit_main
from src.whale_score_design import main as design_main

if __name__ == '__main__':
    from src.graph_config import project_path
    from src.node_centrality import write_json
    write_json(project_path('data/processed/t12/t12_downstream_gate.json'), dict(
        ready_for_t14_t15=False,ready_for_cohort_whaleflow=False,
        blocking_reasons=['T12 recomputation in progress or interrupted.']))
    main()
    audit_main()
    design_main()
