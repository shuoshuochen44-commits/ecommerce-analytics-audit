"""Offline auditable analysis against one pinned, successful data snapshot."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter as monotonic

import duckdb
import sqlglot

from .answer_verifier import expected_result
from .pipeline import load_snapshot
from .query_gateway import SCHEMA, execute_readonly, validate_sql
from .question_catalog import resolve_question, validate_filters, prepare_query


VERSION = 'offline-templates-1.0'


def digest(value):
    encoded = json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def save_run(output_root, response):
    directory = Path(output_root)/'analysis_runs'
    directory.mkdir(parents=True,exist_ok=True)
    response['record_sha256'] = digest(response)
    # Exclusive creation prevents accidental overwrite; administrators can still edit files.
    with (directory/f"{response['run_id']}.json").open('x',encoding='utf-8') as stream:
        json.dump(response,stream,ensure_ascii=False,indent=2,allow_nan=False)
    return response


def get_run(output_root,run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'analysis_[0-9a-f]{32}',run_id):
        raise ValueError('无效分析运行 ID')
    response = json.loads((Path(output_root)/'analysis_runs'/f'{run_id}.json').read_text(encoding='utf-8'))
    if not isinstance(response,dict):
        raise ValueError('运行记录完整性校验失败')
    recorded = response.pop('record_sha256',None)
    if response.get('run_id') != run_id or digest(response) != recorded:
        raise ValueError('运行记录完整性校验失败')
    response['record_sha256'] = recorded
    return response


def citations(snapshot,question):
    return [
        {'source':'docs/data-model.md','section':'四项指标（1.0）/质量与对账',
         'definition':question.definition if question else '仅支持目录中的固定问题'},
        {'source':'snapshot_manifest','snapshot_run_id':snapshot['run_id'],
         'input_fingerprint':snapshot['manifest']['input_fingerprint'],
         'inputs':[{'filename':r['filename'],'sha256':r['sha256']} for r in snapshot['manifest']['inputs']]},
    ]


def quality_warnings(snapshot,question,*,state=None):
    dependencies=set(question.rules)
    if state is not None and question.metric!='failed_rules':
        dependencies.add('Q06')
    warnings = [
        {'rule_id':r['rule_id'],'label':r['label'],'failed_count':r['failed_count'],
         'scope':'full_snapshot','severity':r['severity']}
        for r in snapshot['quality'] if r['rule_id'] in dependencies and r['failed_count']>0
    ]
    if question.metric in ('amount','aov') or question.dimension in ('category','product'):
        missing = execute_readonly(snapshot['directory']/'data.duckdb',
            "SELECT count(*) AS value FROM dwd_orders WHERE order_status='delivered' AND item_count=0")[0]['value']
        if missing:
            warnings.append({'rule_id':'COVERAGE_ITEMS','label':'已交付订单缺少商品明细',
                             'failed_count':missing,'scope':'full_snapshot','severity':'warning'})
    return warnings


def analyze(output_root,question_text,*,start=None,end=None,state=None,snapshot_run_id=None,_replay=None):
    started = monotonic()
    question = resolve_question(question_text)
    response = {
        'run_id':'analysis_'+uuid.uuid4().hex,
        'created_at':datetime.now(timezone.utc).isoformat(),
        'kernel_version':VERSION,'catalog_version':'1.0','schema_sha256':digest(SCHEMA),
        'engine_versions':{'duckdb':duckdb.__version__,'sqlglot':sqlglot.__version__},
        'mode':'offline_templates','llm_calls':0,'llm_cost':0,
        'question_id':question.id if question else None,
        'snapshot_run_id':None,'input_fingerprint':None,'dataset':None,
        'filters':{},'answer':'','sql':None,'parameters':[],'result':[],
        'chart_spec':None,'citations':[],'verification_status':'blocked',
        'verification':{'matched':None,'method':'not_run'},'quality_warnings':[],'stages':[],
    }
    try:
        snapshot = load_snapshot(output_root,run_id=snapshot_run_id)
        response.update(snapshot_run_id=snapshot['run_id'],
                        input_fingerprint=snapshot['manifest']['input_fingerprint'],
                        dataset=snapshot['manifest']['dataset'],citations=citations(snapshot,question))
        response['stages'].append({'stage':'snapshot','status':'pinned'})
        if question is None:
            response['answer']='当前离线版本只支持问题目录中的固定问题，请使用目录文本或问题 ID；未执行查询。'
        else:
            try:
                validate_filters(snapshot,start=start,end=end,state=state)
            except (ValueError,TypeError) as error:
                response['answer']=str(error) if isinstance(error,ValueError) else '日期和地区必须使用规定的文本格式。'
                raise ValueError('筛选校验失败') from None
            response['filters']={'start':start,'end':end,'state':state}
            response['stages'].append({'stage':'route','status':question.kind})
            if question.kind=='refusal':
                response['answer']=question.definition
                response['verification']={'matched':None,'method':'explicit_refusal'}
            elif question.kind=='knowledge':
                response['verification_status']='not_applicable'
                response['verification']={'matched':None,'method':'versioned_definition'}
                response['answer']=question.definition
                if question.id=='K04':
                    data = response['dataset']
                    response['answer']=f"{data['currency_label']}（{data['currency']}）；{data['description']}"
            else:
                sql,parameters = prepare_query(question,**response['filters'])
                if sql:
                    response['sql'] = validate_sql(sql)[0]
                    response['parameters'] = parameters
                    response['result'] = execute_readonly(snapshot['directory']/'data.duckdb',response['sql'],parameters)
                else:
                    response['result']=[{'value':sum(r['failed_count']>0 for r in snapshot['quality'])}]
                response['stages'].append({'stage':'execution','status':'complete'})
                expected = expected_result(snapshot,question,**response['filters'])
                matched = response['result']==expected
                response['verification']={'matched':matched,'method':('quality_rule_reexecution' if not sql else 'raw_tables_python_decimal'),
                                          'expected_result_sha256':digest(expected),'actual_result_sha256':digest(response['result'])}
                response['quality_warnings']=quality_warnings(snapshot,question,state=state)
                response['verification_status']=('blocked' if not matched else 'needs_review' if response['quality_warnings'] else 'verified')
                response['stages'].append({'stage':'verification','status':response['verification_status']})
                if not matched:
                    response['answer']='独立核验不一致，当前结果已阻止用于业务结论，请核查数据快照与查询。'
                else:
                    summary = (str(response['result'][0]['value']) if len(response['result'])==1 and set(response['result'][0])=={'value'}
                               else f"返回 {len(response['result'])} 行聚合结果，详见 result。")
                    if summary=='None': summary='当前范围没有可计算值'
                    warning = '存在影响该问题的数据质量提示，需核查。' if response['quality_warnings'] else ''
                    response['answer']=f'{question.text}：{summary}。{question.definition}{warning}'
                if matched and question.dimension:
                    response['chart_spec']={'mark':'line' if question.dimension=='month' else 'bar',
                                            'x':'month' if question.dimension=='month' else 'dimension',
                                            'y':'value','data':response['result']}
        if _replay:
            response['replay_of']=_replay['run_id']
            response['replay_matches']=response['result']==_replay['result'] and response['verification_status']==_replay['verification_status']
    except FileNotFoundError:
        response.update(answer='未找到可读取的成功数据快照，请先运行数据加工。',verification_status='blocked')
    except (ValueError,TypeError) as error:
        # Validation errors are controlled messages; raw input and exception details are never persisted.
        response.update(answer=response['answer'] or '输入校验、执行预算或独立核验失败，请检查问题目录、日期和地区后重试。',verification_status='blocked')
        response['stages'].append({'stage':'failure','status':type(error).__name__})
        response['result']=[]
        response['chart_spec']=None
    except Exception:
        response.update(answer='分析未完成，当前结果不可核验；请检查成功快照和本地依赖。',verification_status='blocked')
        response['stages'].append({'stage':'failure','status':'internal_error'})
        response['result']=[]
        response['chart_spec']=None
    response['elapsed_ms']=round((monotonic()-started)*1000,3)
    return save_run(output_root,response)


def replay(output_root,run_id):
    original = get_run(output_root,run_id)
    if original['kernel_version']!=VERSION or original['question_id'] is None or not original['snapshot_run_id']:
        raise ValueError('该运行不可由当前内核重放')
    if original['engine_versions'] != {'duckdb':duckdb.__version__,'sqlglot':sqlglot.__version__} or original['schema_sha256'] != digest(SCHEMA):
        raise ValueError('重放需要相同引擎版本和字段策略')
    snapshot = load_snapshot(output_root,run_id=original['snapshot_run_id'])
    if snapshot['manifest']['input_fingerprint']!=original['input_fingerprint']:
        raise ValueError('重放数据指纹不一致')
    return analyze(output_root,original['question_id'],snapshot_run_id=original['snapshot_run_id'],
                   **original['filters'],_replay=original)
