"""Chạy T09 lần hai trong cache, so hash bốn bảng rồi dọn dữ liệu tạm."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import yaml

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    cfg=yaml.safe_load((ROOT/'config/config.yaml').read_text(encoding='utf-8'))
    output=ROOT/cfg['data']['processed_t09_dir']
    summary=json.loads((output/'t09_summary.json').read_text(encoding='utf-8'))
    review=json.loads((output/'t09_review.json').read_text(encoding='utf-8'))
    if summary.get('status')!='VALIDATED' or not review.get('ready_for_downstream'):
        raise ValueError('Cần nghiệm thu độc lập lần chạy đầu trước khi so tái lập.')
    temporary=ROOT/'.cache'/('t09_repro_'+uuid.uuid4().hex)
    hashes={};error=None
    try:
        subprocess.run([sys.executable,str(ROOT/'T09_Network_Centrality.py'),
                        '--output-dir',str(temporary)],cwd=ROOT,check=True)
        for mode in ['daily','weekly']:
            for kind in ['node','snapshot']:
                name=f'{kind}_metrics_{mode}.parquet'
                expected=summary['results'][mode]['artifacts'][name]['sha256']
                hashes[name]=dict(run1=digest(output/name),run2=digest(temporary/name),expected=expected)
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
    finally:
        temporary.resolve().relative_to((ROOT/'.cache').resolve())
        if temporary.exists():
            shutil.rmtree(temporary)
    same=error is None and len(hashes)==4 and all(v['run1']==v['run2']==v['expected'] for v in hashes.values())
    result=dict(status='PASS' if same else 'FAIL',all_match=same,hashes=hashes,error=error,
                temporary_outputs_removed=True)
    (output/'t09_reproducibility.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    summary['reproducibility']=result
    summary['ready_for_downstream']=bool(summary['ready_for_downstream'] and same)
    review['reproducibility_pass']=same
    review['ready_for_downstream']=bool(review['ready_for_downstream'] and same)
    (output/'t09_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    (output/'t09_review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False),encoding='utf-8')
    if not same:
        raise RuntimeError('T09 tái lập không khớp; xem t09_reproducibility.json')
    for name in ['T09_completion_report.md','T09_review_report.md']:
        path=ROOT/'docs'/name
        text=path.read_text(encoding='utf-8')
        note='\nTái lập: chạy lại độc lập lần hai, SHA-256 của cả 4 bảng Parquet giống hệt; dữ liệu tạm đã được dọn. Bằng chứng: data/processed/t09/t09_reproducibility.json.\n'
        if note.strip() not in text:
            path.write_text(text+note,encoding='utf-8')
    print('T09 reproducibility: 4/4 hashes match; temporary outputs removed.',flush=True)


if __name__=='__main__':
    main()
