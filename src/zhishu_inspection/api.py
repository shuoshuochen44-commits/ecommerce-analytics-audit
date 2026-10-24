"""Public offline API; existing snapshot/statistics implementations are reused."""

import hashlib
from pathlib import Path

from .anomalies import detect_anomalies, get_anomaly_run
from .anomaly_diagnostics import AnomalyInputError, validate_anomaly_csv
from .anomaly_models import AnomalyConfig, AnomalySuiteConfig
from .anomaly_reports import render_anomaly_html
from .anomaly_filters import validate_anomaly_filter_values, validate_csv_filter_membership
from .csv_import import COLUMNS, MAX_BYTES, import_csv
from .file_sources import read_csv_table
from .tabular_mapping import map_order_table

__all__ = ['audit_csv', 'detect_anomalies', 'get_anomaly_run', 'AnomalyInputError',
           'AnomalyConfig', 'AnomalySuiteConfig', 'render_anomaly_html']


def audit_csv(input_path: Path | str, output_root: Path | str, *,
              mapping: dict[str, str] | None = None, config: AnomalySuiteConfig | None = None,
              start: str | None = None, end: str | None = None,
              state: str | None = None, category: str | None = None) -> dict:
    """Map/validate a bounded CSV, create a new snapshot, run all anomaly rules.

    Canonical nine-column input uses an identity mapping. Other column names
    require an explicit target-to-source mapping; no guesses are auto-confirmed.
    Quality failures raise AnomalyInputError with safe row evidence, before any
    snapshot is created. An existing output directory is always refused.
    """
    source, root = Path(input_path), Path(output_root)
    if root.exists():
        raise FileExistsError('输出目录已存在；请读取原成功快照或使用新目录')
    if config is not None and not isinstance(config, AnomalySuiteConfig):
        raise ValueError('config 必须是 AnomalySuiteConfig')
    validate_anomaly_filter_values(start=start, end=end, state=state, category=category)
    if source.suffix.lower() != '.csv' or not source.is_file():
        raise ValueError('请选择存在的 CSV 文件')
    with source.open('rb') as stream:
        content = stream.read(MAX_BYTES + 1)
    if not content or len(content) > MAX_BYTES:
        raise ValueError('CSV 输入必须非空且不超过 5 MB')
    validate_anomaly_csv(content, mapping)
    source_sha256 = hashlib.sha256(content).hexdigest()
    effective_mapping = mapping if mapping is not None else {c: c for c in COLUMNS}
    content = map_order_table(read_csv_table(content), effective_mapping)
    validate_csv_filter_membership(content, state=state, category=category)
    # Reserve after validation, exclusively: another importer may have created
    # this directory since the initial check. Never append into its workspace.
    root.mkdir(parents=True, exist_ok=False)
    import_csv(content, root, provenance={'schema_version': '1.0', 'kind': 'csv_api',
               'source_sha256': source_sha256, 'mapping': effective_mapping})
    return detect_anomalies(root, rules='all', config=config,
                            start=start, end=end, state=state, category=category)
