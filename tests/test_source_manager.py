import csv
import io
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from zhishu_inspection.csv_import import COLUMNS
from zhishu_inspection.pipeline import load_snapshot


def csv_bytes(amount='100.00'):
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(COLUMNS)
    writer.writerow(['001','2026-01-01','广东省','U1','家居日用',amount,'0.00',amount,'已完成'])
    return stream.getvalue().encode('utf-8-sig')


def add_csv(manager,tmp_path):
    path=tmp_path/'orders.csv'
    path.write_bytes(csv_bytes())
    source=manager.register_file(path)
    manager.configure(source['id'],table=source['tables'][0]['name'],mapping={c:c for c in COLUMNS})
    return source['id'],path


def test_file_change_refresh_and_failure_keep_last_success(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,path=add_csv(manager,tmp_path)
        first=manager.refresh(sid,wait=True)
        assert first['state']=='ready' and first['snapshot_run_id']
        root=manager.output_for(sid)
        snapshot=load_snapshot(root)
        assert snapshot['summary']['metrics']['completed_product_amount']=='100.00'
        assert any(r['filename']=='source_manifest.json' for r in snapshot['manifest']['inputs'])
        same=manager.refresh(sid,wait=True)
        assert same['snapshot_run_id']==first['snapshot_run_id']
        path.write_bytes(csv_bytes('150.00'))
        changed=manager.refresh(sid,wait=True)
        assert changed['snapshot_run_id']!=first['snapshot_run_id']
        assert load_snapshot(root)['summary']['metrics']['completed_product_amount']=='150.00'
        path.write_bytes(b'bad')
        failure=manager.refresh(sid,wait=True)
        assert failure['state']=='error'
        assert failure['snapshot_run_id']==changed['snapshot_run_id']
        assert load_snapshot(root)['run_id']==changed['snapshot_run_id']


def test_sqlite_mutations_reach_a_new_snapshot(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    path=tmp_path/'source.sqlite'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE orders (order_id TEXT,purchase_date TEXT,province TEXT,buyer_id TEXT,category TEXT,amount TEXT,freight TEXT,paid TEXT,status TEXT)')
        con.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)',('001','2026-01-01','广东省','U1','家居日用','100.00','0.00','100.00','已完成'))
    columns=['order_id','purchase_date','province','buyer_id','category','amount','freight','paid','status']
    with SourceManager(tmp_path/'output') as manager:
        source=manager.register_database({'kind':'sqlite','path':str(path)})
        sid=source['id']
        manager.configure(sid,table='orders',mapping=dict(zip(COLUMNS,columns)))
        first=manager.refresh(sid,wait=True)
        with sqlite3.connect(path) as con:
            con.execute("UPDATE orders SET amount='175.00',paid='175.00'")
        second=manager.refresh(sid,wait=True)
        assert first['snapshot_run_id']!=second['snapshot_run_id']
        assert load_snapshot(manager.output_for(sid))['summary']['metrics']['completed_product_amount']=='175.00'
        with sqlite3.connect(path) as con:
            con.execute('DELETE FROM orders')
        empty=manager.refresh(sid,wait=True)
        assert empty['state']=='ready'
        assert load_snapshot(manager.output_for(sid))['summary']['metrics']['completed_order_count']==0


def test_manual_scheduled_and_watch_share_single_flight(tmp_path,monkeypatch):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,_=add_csv(manager,tmp_path)
        manager.configure(sid,refresh={'interval_seconds':30,'watch_seconds':1})
        original=manager._acquire
        entered=threading.Event()
        release=threading.Event()
        calls=[]
        def hold(record):
            calls.append(1)
            entered.set()
            assert release.wait(5)
            return original(record)
        monkeypatch.setattr(manager,'_acquire',hold)
        manager.refresh(sid)
        assert entered.wait(5)
        manager.refresh(sid)
        manager.tick(now=10**15)
        release.set()
        manager.wait_for_idle(sid)
        assert len(calls)==1
        assert manager.get(sid)['refresh']=={'interval_seconds':30,'watch_seconds':1}
        events=manager.events_after(0,timeout=0)
        assert any(e['type']=='updated' and e['source_id']==sid for e in events)


def test_registry_restart_keeps_settings_and_version(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    output=tmp_path/'output'
    with SourceManager(output) as manager:
        sid,_=add_csv(manager,tmp_path)
        manager.configure(sid,refresh={'interval_seconds':30,'watch_seconds':2})
        first=manager.refresh(sid,wait=True)
    with SourceManager(output) as manager:
        assert manager.get(sid)['snapshot_run_id']==first['snapshot_run_id']
        assert manager.get(sid)['refresh']['watch_seconds']==2
        assert manager.refresh(sid,wait=True)['snapshot_run_id']==first['snapshot_run_id']


def test_invalid_settings_and_paths_are_not_accepted(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,_=add_csv(manager,tmp_path)
        for settings in ({'interval_seconds':0},{'watch_seconds':0},{'watch_seconds':True},{'interval_seconds':'30'}):
            with pytest.raises(ValueError): manager.configure(sid,refresh=settings)
        with pytest.raises(ValueError): manager.output_for('../x')
        with pytest.raises(ValueError): manager.configure(sid,mapping={'订单号':'missing'})
        with pytest.raises(ValueError): manager.register_file(tmp_path/'missing.csv')


def test_uploads_are_explicitly_static_until_reuploaded(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        source=manager.register_upload('orders.csv',csv_bytes())
        assert source['watchable'] is False
        with pytest.raises(ValueError):
            manager.configure(source['id'],refresh={'watch_seconds':1})
        with pytest.raises(ValueError): manager.register_upload('../orders.csv',csv_bytes())


def test_changed_headers_can_be_previewed_and_remapped_without_losing_history(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,path=add_csv(manager,tmp_path)
        first=manager.refresh(sid,wait=True)
        path.write_bytes(csv_bytes('125.00').decode('utf-8-sig').replace('商品金额','amount').encode('utf-8-sig'))
        assert manager.refresh(sid,wait=True)['state']=='error'
        preview=manager.preview(sid)
        assert 'amount' in preview['columns']
        mapping={c:c for c in COLUMNS};mapping['商品金额']='amount'
        manager.configure(sid,mapping=mapping)
        second=manager.refresh(sid,wait=True)
        assert second['state']=='ready' and second['snapshot_run_id']!=first['snapshot_run_id']
        assert load_snapshot(manager.output_for(sid),run_id=first['snapshot_run_id'])['run_id']==first['snapshot_run_id']


@pytest.mark.parametrize('password',['test-secret-123',''])
def test_database_password_never_enters_registry_or_public_status(tmp_path,monkeypatch,password):
    import zhishu_inspection.source_manager as module
    monkeypatch.setattr(module,'inspect_database',lambda config:{'tables':[{'name':'orders','schema':None,'columns':list(COLUMNS)}]})
    config={'kind':'mysql','host':'localhost','port':3306,'database':'demo','username':'reader','password':password}
    output=tmp_path/'output'
    with module.SourceManager(output) as manager:
        source=manager.register_database(config)
        assert 'test-secret-123' not in json.dumps(manager.list_sources())
        assert 'test-secret-123' not in manager.registry.read_text(encoding='utf-8')
        assert source['credentials_required'] is False
    with module.SourceManager(output) as manager:
        assert manager.get(source['id'])['credentials_required'] is True


def test_validate_proposed_mapping_does_not_persist_and_counts_errors(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        path=tmp_path/'invalid.csv'; path.write_bytes(csv_bytes('-1.00'))
        source=manager.register_file(path)
        result=manager.validate(source['id'],mapping={c:c for c in COLUMNS})
        assert not result['valid'] and result['error_count']==2
        assert manager.get(source['id'])['mapping']=={}
        assert result['issues'][0]['row_number']==2
        with pytest.raises(ValueError):
            manager.configure(source['id'],mapping={c:c for c in COLUMNS})
        assert manager.get(source['id'])['mapping']=={}


def test_preview_reuses_only_unique_confirmed_mapping_for_exact_columns(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,path=add_csv(manager,tmp_path)
        other=manager.register_file(path)
        preview=manager.preview(other['id'])
        assert preview['remembered_mapping']=={c:c for c in COLUMNS}
        assert preview['mapping_origin']=='history'
        assert manager.preview(sid)['mapping_origin']=='current'
        conflicting={c:c for c in COLUMNS}
        conflicting['商品金额'],conflicting['支付金额']='支付金额','商品金额'
        manager.configure(other['id'],mapping=conflicting)
        third=manager.register_file(path)
        assert manager.preview(third['id'])['remembered_mapping']=={}
        assert manager.preview(third['id'])['mapping_origin']=='conflict'
        extra=tmp_path/'extra.csv'
        extra.write_bytes(path.read_bytes().decode('utf-8-sig').replace('订单状态','订单状态,extra').replace('已完成','已完成,x').encode('utf-8-sig'))
        fourth=manager.register_file(extra)
        assert manager.preview(fourth['id'])['remembered_mapping']=={}


def test_refresh_diagnostics_use_original_order_and_keep_success(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,path=add_csv(manager,tmp_path)
        first=manager.refresh(sid,wait=True)
        path.write_bytes(csv_bytes().replace(b'001',b'ZZZ')+csv_bytes('-5').decode('utf-8-sig').splitlines()[1].encode()+b'\r\n')
        failed=manager.refresh(sid,wait=True)
        assert failed['state']=='error'
        assert failed['snapshot_run_id']==first['snapshot_run_id']
        assert failed['diagnostics']['issues'][0]['row_number']==3
        assert 'ZZZ' not in str(failed['diagnostics'])
        path.write_bytes(csv_bytes())
        assert manager.refresh(sid,wait=True)['diagnostics'] is None


def test_old_registry_mapping_is_reused_after_upgrade(tmp_path):
    from zhishu_inspection.source_manager import SourceManager
    output=tmp_path/'output'
    with SourceManager(output) as manager:
        sid,path=add_csv(manager,tmp_path)
    registry=output/'connections'/'registry.json'
    records=json.loads(registry.read_text(encoding='utf-8'))
    for record in records['sources']:
        record.pop('mapping_columns',None)
    registry.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
    with SourceManager(output) as manager:
        new=manager.register_file(path)
        result=manager.preview(new['id'])
        assert result['mapping_origin']=='history'
        assert result['remembered_mapping']=={c:c for c in COLUMNS}


def test_mapping_validation_does_not_block_status_and_rejects_stale_commit(tmp_path,monkeypatch):
    from zhishu_inspection.source_manager import SourceManager
    with SourceManager(tmp_path/'output') as manager:
        sid,_=add_csv(manager,tmp_path)
        entered=threading.Event(); release=threading.Event(); status_done=threading.Event(); failures=[]
        original=manager._read_table
        def hold(record):
            if threading.current_thread().name=='mapping-check':
                entered.set(); assert release.wait(5)
            return original(record)
        monkeypatch.setattr(manager,'_read_table',hold)
        def configure():
            try: manager.configure(sid,mapping={c:c for c in COLUMNS})
            except ValueError as error: failures.append(str(error))
        worker=threading.Thread(target=configure,name='mapping-check');worker.start()
        assert entered.wait(5)
        reader=threading.Thread(target=lambda:(manager.get(sid),status_done.set()));reader.start()
        try:
            assert status_done.wait(1), 'status reads must remain available while source data is checked'
            manager.configure(sid,refresh={'interval_seconds':60})
        finally:
            release.set();worker.join(6);reader.join(6)
        assert failures and '变化' in failures[0]
        assert manager.get(sid)['refresh']['interval_seconds']==60
