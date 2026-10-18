import csv
import io

import pytest

from zhishu_inspection.csv_import import COLUMNS,import_csv,parse_csv
from zhishu_inspection.pipeline import load_snapshot


def test_live_empty_source_and_origin_are_preserved(tmp_path):
    stream=io.StringIO(newline='')
    csv.writer(stream).writerow(COLUMNS)
    content=stream.getvalue().encode('utf-8-sig')
    with pytest.raises(ValueError):parse_csv(content)
    result=import_csv(content,tmp_path,allow_empty=True,provenance={'kind':'sqlite','table':'orders','mapping_version':'1'})
    assert result['metrics']['completed_order_count']==0
    snapshot=load_snapshot(tmp_path)
    assert 'source_manifest.json' in {r['filename'] for r in snapshot['manifest']['inputs']}
