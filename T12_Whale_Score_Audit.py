"""T12: label coverage, log sensitivity, persistence and public-source review."""
from src.whale_score_audit import main
from src.whale_score_design import main as design_main

if __name__=='__main__':
    main()
    design_main()
