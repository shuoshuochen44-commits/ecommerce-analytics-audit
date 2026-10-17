"""CLI entry point for offline analysis; outputs machine-readable JSON."""

import argparse
import json
from pathlib import Path

from .analysis import analyze, replay
from .question_catalog import QUESTIONS


def main(argv=None):
    parser=argparse.ArgumentParser(description='智数离线可审计问答（固定问题模板，不调用模型）')
    parser.add_argument('output_root',nargs='?',type=Path)
    parser.add_argument('question',nargs='?')
    parser.add_argument('--list',action='store_true',help='列出全部 30 条支持问题')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--state')
    parser.add_argument('--snapshot-run-id')
    parser.add_argument('--replay',metavar='ANALYSIS_RUN_ID')
    args=parser.parse_args(argv)
    if args.list:
        result=[{'id':q.id,'question':q.text,'kind':q.kind,'definition':q.definition} for q in QUESTIONS]
    elif args.output_root is None or not (args.question or args.replay):
        parser.error('需要成功快照输出目录及问题 ID/文本，或使用 --list')
    elif args.replay and (args.question or args.start or args.end or args.state or args.snapshot_run_id):
        parser.error('重放使用原运行参数，不能附加问题或筛选')
    else:
        try:
            result=(replay(args.output_root,args.replay) if args.replay else
                    analyze(args.output_root,args.question,start=args.start,end=args.end,state=args.state,
                            snapshot_run_id=args.snapshot_run_id))
        except (ValueError,FileNotFoundError,json.JSONDecodeError):
            print(json.dumps({'error':'无法读取或重放该运行，请核对 ID、版本和记录完整性。'},ensure_ascii=False))
            return 2
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 2 if isinstance(result,dict) and result.get('verification_status')=='blocked' else 0


if __name__=='__main__':
    raise SystemExit(main())
