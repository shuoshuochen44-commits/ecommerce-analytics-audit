const { test } = require('node:test');
const assert = require('node:assert/strict');
const { scopeKey, resultMarkup, chartMarkup, canReplay } = require('../src/zhishu_inspection/web/analysis.js');

test('scope identity changes for source, snapshot or filters', () => {
  const scope = {source:'src_one',snapshot_run_id:'first',start:null,end:null,state:null};
  assert.equal(scopeKey(scope), scopeKey({...scope,start:undefined}));
  for (const [key,value] of [['source','src_two'],['snapshot_run_id','second'],['start','2026-01-01'],['state','广东省']]) {
    assert.notEqual(scopeKey(scope), scopeKey({...scope,[key]:value}));
  }
});

test('blocked answers never render unverified numbers or charts', () => {
  const run={verification_status:'blocked',answer:'核验不一致',result:[{value:'987654321.99'}],
    chart_spec:{mark:'bar',x:'dimension',y:'value',data:[{dimension:'x',value:'987654321.99'}]}};
  assert.doesNotMatch(resultMarkup(run, {metric:'amount'}), /987654321/);
  assert.equal(chartMarkup(run), '');
});

test('table labels are escaped and exact amounts stay visible', () => {
  const run={verification_status:'verified',result:[{dimension:'<img onerror="bad">',value:'123.45'}],
    dataset:{currency:'CNY',currency_label:'人民币'},question_id:'D01'};
  const html=resultMarkup(run,{metric:'amount'});
  assert.match(html,/123\.45/);
  assert.match(html,/&lt;img/);
  assert.doesNotMatch(html,/<img/);
});

test('unknown and null results remain explicitly empty', () => {
  assert.match(resultMarkup({verification_status:'verified',result:[{value:null}]},{metric:'amount'}),/暂无可计算值/);
  assert.equal(chartMarkup({verification_status:'verified',chart_spec:null}), '');
});

test('verified monthly data renders a labeled graph with escaped tooltip', () => {
  const run={verification_status:'verified',chart_spec:{mark:'line',x:'month',y:'value',data:[{month:'2026-01',value:'10.00'},{month:'2026-03',value:'20.00'}]}};
  assert.match(chartMarkup(run),/<svg/);
  assert.match(chartMarkup(run),/2026-03/);
});

test('missing totals are shown as gaps, never zero points or bars', () => {
  const run={verification_status:'needs_review',chart_spec:{mark:'line',x:'month',y:'value',data:[{month:'2026-01',value:'10.00'},{month:'2026-02',value:null},{month:'2026-03',value:'20.00'}]}};
  const line=chartMarkup(run);
  assert.equal((line.match(/<circle /g)||[]).length,2);
  assert.doesNotMatch(line,/L[0-9]/);
  assert.match(line,/缺少可计算/);
  run.chart_spec.mark='bar';
  assert.equal((chartMarkup(run).match(/class="fill"/g)||[]).length,2);
});

test('filter validation failures and unmatched questions cannot replay', () => {
  assert.equal(canReplay({question_id:'A01',snapshot_run_id:'first',filters:{}}),false);
  assert.equal(canReplay({question_id:null,snapshot_run_id:'first',filters:{start:null,end:null,state:null}}),false);
  assert.equal(canReplay({question_id:'A01',snapshot_run_id:'first',filters:{start:null,end:null,state:null}}),true);
});

test('removing the last source marks the retained answer stale and disables new analysis', async () => {
  const vm=require('node:vm'),fs=require('node:fs'),nodes=new Map();
  const get=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,listeners:{},
      classList:{hidden:false,toggle(name,value){this[name]=value},add(name){this[name]=true},remove(name){this[name]=false}},
      querySelectorAll(){return []},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn}});
    return nodes.get(id);
  };
  const filters={start:null,end:null,state:null};
  const run={run_id:'analysis_test',snapshot_run_id:'snapshot_one',question_id:'A01',filters,
    verification_status:'verified',result:[{value:'100.00'}],parameters:[],citations:[],verification:{},elapsed_ms:1};
  const context={titles:{},$:get,document:{},connectionState:{sources:[{id:'src_one',name:'订单来源'}]},
    current:{active_source:'src_one',run_id:'snapshot_one',dataset:{id:'customer_csv'},filters},
    render(){},async refreshSourceList(){context.current=null},setTimeout,clearTimeout,AbortController,
    fetch:async path=>({ok:true,json:async()=>path.endsWith('/questions')?{questions:['A01','A05','T01','D03'].map(id=>({id,text:id,kind:'data',metric:'amount'}))}:{run}})};
  vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../src/zhishu_inspection/web/analysis.js'),'utf8'),context);
  await new Promise(setImmediate);
  get('analysis-question').value='A01';get('analysis-form').listeners.submit({preventDefault(){}});
  await new Promise(setImmediate);
  assert.equal(get('analysis-result').classList.hidden,false);
  await context.refreshSourceList();
  assert.equal(get('analysis-submit').disabled,true);
  assert.equal(get('analysis-stale').classList.hidden,false);
  assert.match(get('analysis-scope').textContent,/请先导入/);
});
