"""Local TEMPLATE acceptance, not a frozen LLM benchmark or method comparison."""

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from zhishu_inspection.analysis import analyze
from zhishu_inspection.dataset import FIXTURE_DATASET
from zhishu_inspection.pipeline import load_snapshot, run_pipeline
from zhishu_inspection.question_catalog import QUESTIONS


PROJECT_ROOT=Path(__file__).resolve().parents[1]


def verify(output_root,*,fixture_gold=False):
    snapshot=load_snapshot(output_root)
    gold={}
    if fixture_gold:
        if snapshot['manifest']['dataset']!=FIXTURE_DATASET:
            raise ValueError('手工验收样本必须明确标注为模拟数据；请重新运行 --fixture-gold，不要使用 --existing')
        fixture=PROJECT_ROOT/'tests'/'fixtures'/'olist_mini'
        expected_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.glob('*.csv')}
        actual_hashes={row['filename']:row['sha256'] for row in snapshot['manifest']['inputs'] if row['filename'].endswith('.csv')}
        if expected_hashes!=actual_hashes:
            raise ValueError('人工金标准只适用于已提交的 olist_mini 原始输入')
        gold=json.loads((PROJECT_ROOT/'tests'/'analysis_expected.json').read_text(encoding='utf-8'))
    records=[]
    for q in QUESTIONS:
        answer=analyze(output_root,q.id,snapshot_run_id=snapshot['run_id'])
        if q.kind=='refusal':
            passed=answer['verification_status']=='blocked' and answer['verification']['method']=='explicit_refusal'
        elif q.kind=='knowledge':
            passed=answer['verification_status']=='not_applicable' and bool(answer['citations'])
        else:
            passed=answer['verification']['matched'] is True and answer['verification_status'] in ('verified','needs_review')
        if q.id in gold:
            passed=passed and answer['result']==gold[q.id]
        records.append({'question_id':q.id,'kind':q.kind,'run_id':answer['run_id'],
                        'verification_status':answer['verification_status'],
                        'passed':passed,'manual_gold_checked':q.id in gold,'elapsed_ms':answer['elapsed_ms']})
    return {'mode':'offline_templates','notice':'固定问题模板的工程验收；没有接入模型，不代表自然语言泛化、模型基线或论文评测结果。',
            'snapshot_run_id':snapshot['run_id'],'input_fingerprint':snapshot['manifest']['input_fingerprint'],
            'dataset':snapshot['manifest']['dataset'],'llm_calls':0,'llm_cost':0,
            'passed':sum(r['passed'] for r in records),'failed':sum(not r['passed'] for r in records),
            'statuses':dict(Counter(r['verification_status'] for r in records)),
            'mean_elapsed_ms':round(sum(r['elapsed_ms'] for r in records)/len(records),3),
            'records':records}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir',type=Path,default=PROJECT_ROOT/'tests'/'fixtures'/'olist_mini')
    parser.add_argument('--output-root',type=Path,default=PROJECT_ROOT/'artifacts'/'analysis-acceptance')
    parser.add_argument('--existing',action='store_true',help='使用现有成功快照，不重新加工')
    parser.add_argument('--fixture-gold',action='store_true')
    args=parser.parse_args(argv)
    if not args.existing:
        if args.fixture_gold:
            args.output_root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='fixture-input-',dir=args.output_root) as temporary:
                raw=Path(temporary)/'raw'
                shutil.copytree(args.raw_dir,raw)
                (raw/'dataset.json').write_text(json.dumps(FIXTURE_DATASET,ensure_ascii=False,sort_keys=True),encoding='utf-8')
                run_pipeline(raw,args.output_root)
        else:
            run_pipeline(args.raw_dir,args.output_root)
    report=verify(args.output_root,fixture_gold=args.fixture_gold)
    path=args.output_root/'template-acceptance.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(path),'passed':report['passed'],'failed':report['failed'],
                      'statuses':report['statuses'],'mode':report['mode']},ensure_ascii=False))
    return 1 if report['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
