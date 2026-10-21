"""T12: WhaleScore theo cửa sổ, nhãn hạ tầng từ T07 và chỉ số T09."""
from src.whale_score import main
from src.whale_score_audit import main as audit_main
from src.whale_score_design import main as design_main

if __name__ == '__main__':
    main()
    audit_main()
    design_main()
