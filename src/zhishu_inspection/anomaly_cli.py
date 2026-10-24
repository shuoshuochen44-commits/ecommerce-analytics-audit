"""Anomaly mode for the existing analysis CLI, with safe local-only output."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .anomalies import detect_anomalies
from .anomaly_models import AnomalyConfig, AnomalySuiteConfig
from .anomaly_diagnostics import AnomalyInputError
from .api import audit_csv
from .anomaly_reports import render_anomaly_html
from .anomaly_filters import validate_anomaly_filter_values, validate_csv_filter_membership
from .csv_import import MAX_BYTES, import_csv


def _read_bounded(path: Path, maximum: int) -> bytes:
    if not path.is_file():
        raise ValueError('请选择存在的普通输入或配置文件')
    with path.open('rb') as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError('输入或配置文件超过大小限制')
    return content


def run_anomaly_cli(args: argparse.Namespace) -> int:
    try:
        validate_anomaly_filter_values(start=args.start, end=args.end,
                                      state=args.state, category=args.category)
        rules = args.rules or 'sales'
        config_type = AnomalySuiteConfig if rules == 'all' else AnomalyConfig
        config = config_type()
        if args.config_path:
            content = _read_bounded(args.config_path, 16384).decode('utf-8-sig')
            config = config_type.from_mapping(json.loads(content, parse_float=Decimal))
        if args.report_output:
            if args.report_output.exists():
                raise FileExistsError()
            if not args.report_output.parent.is_dir():
                raise ValueError('输出文件的父目录不存在，请先创建目录')
        report = None
        if args.input_path:
            # Imports are explicit new workspaces. Never advance an existing user's
            # latest pointer merely because a command line was mistyped.
            if args.output_root.exists():
                raise FileExistsError()
            if args.input_path.suffix.lower() != '.csv':
                raise ValueError('当前异常检测输入模式支持九列订单 CSV；其他格式请先通过已有数据接入生成快照')
            if rules == 'all':
                mapping = (json.loads(_read_bounded(args.mapping_path, 16384).decode('utf-8-sig'))
                           if args.mapping_path else None)
                report = audit_csv(args.input_path, args.output_root, mapping=mapping, config=config,
                                   start=args.start, end=args.end, state=args.state, category=args.category)
            else:
                content = _read_bounded(args.input_path, MAX_BYTES)
                validate_csv_filter_membership(content, state=args.state, category=args.category)
                import_csv(content, args.output_root)
        if report is None:
            report = detect_anomalies(args.output_root, snapshot_run_id=args.snapshot_run_id,
                                  start=args.start, end=args.end, state=args.state,
                                  category=args.category, config=config, rules=rules)
        encoded = (render_anomaly_html(report) if args.format == 'html' else
                   json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        if args.report_output:
            with args.report_output.open('x', encoding='utf-8') as target:
                target.write(encoded + '\n')
        # Redirected Windows streams may default to GBK. Machine JSON uses the
        # same UTF-8 contract as the report file, independent of the shell locale.
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(encoded)
        return 0
    except AnomalyInputError as error:
        if args.report_output:
            encoded = (render_anomaly_html(error.report) if args.format == 'html' else
                       json.dumps(error.report, ensure_ascii=False, indent=2, allow_nan=False))
            try:
                with args.report_output.open('x', encoding='utf-8') as target:
                    target.write(encoded + '\n')
            except OSError:
                print('质量未通过，且无法保存诊断报告；已有输出文件保持不变。', file=sys.stderr)
                return 2
        print(str(error), file=sys.stderr)
    except FileExistsError:
        print('异常检测未执行：输出文件或 CSV 导入目录已存在。请选择新路径；已有快照请去掉 --input 后读取。', file=sys.stderr)
    except KeyError:
        print('异常检测未完成：成功快照结构不完整或格式不兼容，请重新核验数据快照。', file=sys.stderr)
    except (ValueError, TypeError, UnicodeError) as error:
        print(f'异常检测未完成：{error}', file=sys.stderr)
    except OSError:
        print('异常检测未完成：无法读取输入、配置、成功快照或写入记录，请检查文件和目录权限。', file=sys.stderr)
    return 2
