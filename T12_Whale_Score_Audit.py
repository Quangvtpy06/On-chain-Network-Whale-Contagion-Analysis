"""T12: label coverage, log sensitivity, persistence and public-source review."""
from src.whale_score_audit import main
from src.whale_score_design import main as design_main

if __name__=='__main__':
    from src.graph_config import project_path
    from src.node_centrality import write_json
    write_json(project_path('data/processed/t12/t12_downstream_gate.json'), dict(
        ready_for_t14_t15=False,ready_for_cohort_whaleflow=False,
        blocking_reasons=['T12 audit/design recomputation in progress or interrupted.']))
    main()
    design_main()
