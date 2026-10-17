import json
from pathlib import Path

from zhishu_inspection.pipeline import run_pipeline


def test_cli_list_run_and_replay(tmp_path,capsys):
    from zhishu_inspection.analysis_cli import main
    assert main(['--list'])==0
    assert len(json.loads(capsys.readouterr().out))==30
    root=tmp_path/'snapshots'
    run_pipeline(Path('tests/fixtures/olist_mini'),root)
    assert main([str(root),'A01'])==0
    response=json.loads(capsys.readouterr().out)
    assert response['result']==[{'value':'230.00'}]
    assert main([str(root),'--replay',response['run_id']])==0
    replay=json.loads(capsys.readouterr().out)
    assert replay['replay_matches']


def test_cli_errors_have_nonzero_exit(tmp_path,capsys):
    from zhishu_inspection.analysis_cli import main
    assert main([str(tmp_path),'A01'])==2
    assert json.loads(capsys.readouterr().out)['verification_status']=='blocked'
    assert main([str(tmp_path),'--replay','../bad'])==2
    assert 'error' in json.loads(capsys.readouterr().out)


def test_acceptance_checks_all_fixture_answers(tmp_path):
    import shutil
    from zhishu_inspection.dataset import FIXTURE_DATASET
    from scripts.verify_analysis import verify
    root=tmp_path/'snapshots'
    raw=tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    (raw/'dataset.json').write_text(json.dumps(FIXTURE_DATASET,ensure_ascii=False),encoding='utf-8')
    run_pipeline(raw,root)
    report=verify(root, fixture_gold=True)
    assert report['passed']==30 and report['failed']==0
    assert report['mode']=='offline_templates'
    assert report['llm_calls']==0
    assert report['dataset']['simulated'] is True


def test_one_command_fixture_acceptance_preserves_simulation_provenance(tmp_path,capsys):
    from scripts.verify_analysis import main
    from zhishu_inspection.pipeline import load_snapshot
    root=tmp_path/'acceptance'
    assert main(['--fixture-gold','--output-root',str(root)])==0
    report=json.loads((root/'template-acceptance.json').read_text(encoding='utf-8'))
    assert report['dataset']['simulated'] is True
    assert report['dataset']['id']=='olist_mini'
    snapshot=load_snapshot(root)
    assert any(row['filename']=='dataset.json' for row in snapshot['manifest']['inputs'])


def test_hand_gold_is_rejected_for_unlabelled_snapshot(tmp_path):
    import pytest
    from scripts.verify_analysis import verify
    run_pipeline(Path('tests/fixtures/olist_mini'),tmp_path)
    with pytest.raises(ValueError,match='模拟'):
        verify(tmp_path,fixture_gold=True)
