"""Safe row evidence from the existing order mapping quality gate."""

import hashlib
import uuid
from datetime import datetime, timezone

from .csv_import import COLUMNS
from .file_sources import read_csv_table
from .tabular_mapping import validate_order_table


class AnomalyInputError(ValueError):
    def __init__(self, report: dict):
        super().__init__('订单质量检查未通过，未运行统计检测或创建成功快照；请按报告行列提示修正')
        self.report = report


def validate_anomaly_csv(content: bytes, mapping: dict[str, str] | None = None) -> None:
    table = read_csv_table(content)
    if mapping is None:
        if table.columns != COLUMNS:
            raise ValueError('请使用原有九列订单表头与顺序；其他字段请明确映射')
        mapping = {column: column for column in COLUMNS}
    validation = validate_order_table(table, mapping)
    if validation['valid']:
        return
    first_rows, related = {}, {}
    order_position = table.columns.index(mapping['订单号'])
    for line, row in zip(table.row_numbers, table.rows):
        key = row[order_position].strip()
        if key in first_rows:
            related[line] = [first_rows[key], line]
        else:
            first_rows[key] = line
    issues = []
    rule_for_field = {'订单号': 'Q01', '下单日期': 'Q10', '商品金额': 'Q07',
                      '运费': 'Q08', '支付金额': 'Q14', '订单状态': 'Q09'}
    for issue in validation['issues']:
        item = dict(issue)
        duplicate = item['target_field'] == '订单号' and item['reason'] == '订单号重复'
        item['quality_rule_id'] = 'Q02' if duplicate else rule_for_field.get(item['target_field'], 'IMPORT_FIELD')
        if duplicate:
            item['related_rows'] = related[item['row_number']]
        issues.append(item)
    raise AnomalyInputError({
        'schema_version': '1.1', 'run_id': 'quality_' + uuid.uuid4().hex,
        'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'BLOCKED_QUALITY',
        'snapshot_id': None, 'source_fingerprint': hashlib.sha256(content).hexdigest(),
        'sample_size': validation['row_count'], 'alert_count': 0, 'results': [],
        'quality_issue_count': validation['error_count'], 'quality_issues': issues,
        'issues_truncated': validation['truncated'],
        'limitations': ['这是输入质量阻断证据，没有成功快照或统计异常结论；问题数不等于异常订单去重数。',
                        '行号是原 CSV 中记录起始物理行，最多展示前 50 项安全诊断，不包含原始单元格内容。'],
    })
