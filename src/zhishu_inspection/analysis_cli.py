"""CLI entry point for offline analysis; outputs machine-readable JSON."""

import argparse
import json
import sys
from pathlib import Path

from .analysis import analyze, replay
from .question_catalog import QUESTIONS


def main(argv=None):
    # Windows redirected streams can inherit GBK; machine JSON is always UTF-8.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='智数离线可审计问答与异常检测（不调用模型）',
        epilog='示例：zhishu-analyze work/check --detect-anomalies --input orders.csv --output report.json；'
               '完整检测：zhishu-analyze work/check --detect-anomalies --rules all --format html；'
               '读取已有快照：zhishu-analyze work/check --detect-anomalies --start 2026-01-15。')
    parser.add_argument('output_root',nargs='?',type=Path)
    parser.add_argument('question',nargs='?')
    parser.add_argument('--list',action='store_true',help='列出全部 30 条支持问题')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--state')
    parser.add_argument('--snapshot-run-id')
    parser.add_argument('--replay',metavar='ANALYSIS_RUN_ID')
    parser.add_argument('--detect-anomalies',action='store_true',help='检测成功快照中的异常；--rules all 启用三种统计规则')
    parser.add_argument('--input',dest='input_path',type=Path,help='九列订单 CSV；仅导入到新的 output_root 目录')
    parser.add_argument('--mapping',dest='mapping_path',type=Path,help='目标中文字段到源列名的 JSON；需 --rules all --input')
    parser.add_argument('--output',dest='report_output',type=Path,help='异常检测 JSON/HTML 报告；拒绝覆盖已有文件')
    parser.add_argument('--format',choices=('json','html'),help='异常报告格式，默认 json')
    parser.add_argument('--rules',choices=('sales','all'),help='sales 为兼容销售模式；all 检查销售额、订单量和单笔金额')
    parser.add_argument('--config',dest='config_path',type=Path,help='异常规则 JSON 配置文件')
    parser.add_argument('--category',help='异常检测品类筛选，金额按商品行汇总')
    args=parser.parse_args(argv)
    if args.detect_anomalies:
        if args.output_root is None or args.question or args.list or args.replay:
            parser.error('异常检测需要 output_root，且不能同时使用问题、--list 或 --replay')
        if args.input_path and args.snapshot_run_id:
            parser.error('--input 创建新快照，不能同时指定已有 --snapshot-run-id')
        if args.mapping_path is not None and (not args.input_path or args.rules != 'all'):
            parser.error('--mapping 需要 --rules all 和 --input')
        from .anomaly_cli import run_anomaly_cli
        return run_anomaly_cli(args)
    if any(value is not None for value in (args.input_path,args.report_output,args.format,args.config_path,args.category,args.rules,args.mapping_path)):
        parser.error('--input/--output/--format/--config/--category/--rules/--mapping 需要 --detect-anomalies')
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
