import threading
from pathlib import Path

import pytest

from zhishu_inspection.server import create_server


def test_another_running_server_exclusively_owns_its_port(tmp_path):
    first=create_server(tmp_path/'one',port=0)
    second=None
    try:
        with pytest.raises(OSError):
            second=create_server(tmp_path/'two',port=first.server_address[1])
    finally:
        if second:second.server_close()
        first.server_close()


def test_startup_creates_no_demo_or_preloaded_snapshot(tmp_path):
    from zhishu_inspection.launcher import prepare_workspace
    root=prepare_workspace(tmp_path)
    assert root.is_dir()
    assert not (root/'latest.json').exists()
    assert not (tmp_path/'data/raw').exists()
    assert not list(tmp_path.rglob('*.csv'))


def test_downloadable_template_has_only_headers():
    import csv
    import io
    from zhishu_inspection.csv_import import COLUMNS, template_csv
    assert list(csv.reader(io.StringIO(template_csv().decode('utf-8-sig')))) == [list(COLUMNS)]


def test_empty_service_has_health_identity_without_data(tmp_path):
    from zhishu_inspection.launcher import existing_workspace
    server=create_server(tmp_path/'empty',port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        url=f'http://127.0.0.1:{server.server_address[1]}/'
        assert existing_workspace(url,tmp_path/'empty')
        assert not existing_workspace(url,tmp_path/'other')
    finally:
        server.shutdown();server.server_close();thread.join()


def test_product_has_no_simulation_notice_and_opens_ingestion_first():
    page=Path('src/zhishu_inspection/web/dashboard.html').read_text(encoding='utf-8')
    assert '模拟数据' not in page
    assert '模拟练习' not in page
    assert 'initializeWorkspace()' in page


def test_frozen_resource_and_data_locations_are_separate(tmp_path,monkeypatch):
    import sys
    from zhishu_inspection.resources import project_directory,resource_path
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path/'bundle'),raising=False)
    monkeypatch.setattr(sys,'executable',str(tmp_path/'delivery'/'智数巡检.exe'))
    assert project_directory()==tmp_path/'delivery'
    assert resource_path('sql')==tmp_path/'bundle'/'sql'
