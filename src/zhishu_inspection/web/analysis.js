/* Fixed questions share the same pinned snapshot and deterministic verifier as CLI. */
(() => {
 const html = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const format = value => Number(value).toLocaleString('zh-CN', {maximumFractionDigits:2});
 function scopeKey(scope) {
  return JSON.stringify(['source','snapshot_run_id','start','end','state'].map(k=>scope?.[k]||null));
 }
 function canReplay(run) {
  return !!run?.question_id&&!!run?.snapshot_run_id&&['start','end','state'].every(k=>Object.hasOwn(run.filters||{},k));
 }
 function valueLabel(value, question, run) {
  if(value===null||value===undefined)return '暂无可计算值';
  const money=['amount','aov'].includes(question?.metric),rate=question?.metric==='repeat_rate';
  const number=money?Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):format(value);
  return number+(money?' '+(run.dataset?.currency==='CNY'?'元':run.dataset?.currency||''):rate?'%':'');
 }
 function resultMarkup(run, question) {
  if(run.verification_status==='blocked'||!run.result?.length)return '';
  if(run.result.length===1&&Object.keys(run.result[0]).length===1&&'value' in run.result[0]) {
   return '<div class="analysis-number">'+html(valueLabel(run.result[0].value,question,run))+'</div>';
  }
  const dimension=question?.dimension,labels={delivered:'已完成',shipped:'已发货',processing:'处理中',canceled:'已取消',
   matched:'金额一致',mismatch:'金额需核对',missing_items:'缺商品记录',missing_payment:'缺支付记录',missing_both:'缺商品和支付记录'};
  const headings={region:'地区',category:'商品分类',product:'商品编号',month:'月份',status:'订单状态',reconciliation:'核对状态'};
  return '<div class="table-wrap analysis-table"><table><thead><tr><th>'+html(headings[dimension]||'维度')+'</th><th>计算结果</th></tr></thead><tbody>'+run.result.map(row=>{
   const label=row.month??row.dimension;
   return '<tr><td>'+html(labels[label]||label)+'</td><td>'+html(valueLabel(row.value,question,run))+'</td></tr>';
  }).join('')+'</tbody></table></div>';
 }
 function chartMarkup(run) {
  if(run.verification_status==='blocked'||!run.chart_spec?.data?.length)return '';
  const spec=run.chart_spec,rows=spec.data.slice(0,60),present=row=>row.value!==null&&row.value!==undefined&&Number.isFinite(Number(row.value));
  if(!rows.some(present))return '<p class="caption">当前范围暂无可绘制的数值，详见结果表。</p>';
  const max=Math.max(...rows.filter(present).map(r=>Number(r.value)),1),missing=rows.some(r=>!present(r))?'<p class="caption">部分月份或维度缺少可计算值，图中不按零处理。</p>':'';
  if(spec.mark!=='line')return '<div class="analysis-bars">'+rows.map(row=>'<div class="bar-row"><div class="bar-label"><span class="label">'+html(row[spec.x])+'</span><span>'+html(present(row)?format(row.value):'暂无可计算值')+'</span></div>'+(present(row)?'<div class="track"><div class="fill" style="width:'+Math.max(0,Number(row.value)/max*100)+'%"></div></div>':'')+'</div>').join('')+'</div>'+missing;
  const W=700,H=220,L=55,R=25,T=20,B=35;
  const times=rows.map(r=>Number(String(r[spec.x]).slice(0,4))*12+Number(String(r[spec.x]).slice(5,7)));
  const span=times.at(-1)-times[0],x=i=>L+(W-L-R)*(span?(times[i]-times[0])/span:.5),y=v=>H-B-(H-T-B)*v/(max*1.12);
  const points=rows.map((r,i)=>present(r)?(i&&present(rows[i-1])?'L':'M')+x(i)+','+y(Number(r.value)):'').join(' ');
  const step=Math.max(1,Math.ceil(rows.length/6));
  return '<svg class="analysis-line" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="问题结果的月份趋势">'+[0,.5,1].map(t=>'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(max*t)+'" y2="'+y(max*t)+'" stroke="#dce7df"/><text x="'+(L-8)+'" y="'+(y(max*t)+4)+'" text-anchor="end" font-size="11" fill="#61796e">'+html(format(max*t))+'</text>').join('')+'<path d="'+points+'" fill="none" stroke="#146c50" stroke-width="2.5"/>'+rows.map((r,i)=>(present(r)?'<circle cx="'+x(i)+'" cy="'+y(Number(r.value))+'" r="4" fill="#146c50"><title>'+html(r[spec.x]+'：'+r.value)+'</title></circle>':'')+(i%step===0||i===rows.length-1?'<text x="'+x(i)+'" y="'+(H-9)+'" text-anchor="middle" font-size="11" fill="#61796e">'+html(r[spec.x])+'</text>':'')).join('')+'</svg>'+missing+(spec.data.length>60?'<p class="caption">图形展示前 60 个月；下表保留完整结果。</p>':'');
 }
 if(typeof module!=='undefined')module.exports={scopeKey,resultMarkup,chartMarkup,canReplay};
 if(typeof document==='undefined')return;

 titles.analysis=['问数据，答案有依据','选择一个经营问题，查看结果与计算依据。'];
 const state={questions:[],busy:false,run:null,scope:null};
 const categories={data:'经营分析',quality:'数据质量',knowledge:'指标口径',refusal:'数据能力边界'};
 const badges={verified:'独立核验通过',needs_review:'需关注数据质量',blocked:'当前无法回答',not_applicable:'口径说明'};
 function currentScope() {
  if(!current)return null;
  return {source:current.active_source||(current.dataset.id==='customer_csv'?'customer':'demo'),snapshot_run_id:current.run_id,...current.filters};
 }
 function describe(scope) {
  if(!scope)return '请先导入文件或连接数据库';
  const source=connectionState.sources.find(s=>s.id===scope.source)?.name||(scope.source==='customer'?'导入数据':'工作区数据');
  return source+' · '+(scope.start||scope.end?(scope.start||'最早')+' 至 '+(scope.end||'最新'):'全部日期')+' · '+(scope.state==='__unknown__'?'未填写地区':scope.state||'全部地区');
 }
 function sync() {
  const scope=currentScope();
  $('analysis-scope').textContent=describe(scope);
  $('analysis-submit').disabled=state.busy||!scope||!state.questions.length;
  $('analysis-question').disabled=state.busy||!state.questions.length;
  $('analysis-text').disabled=state.busy;
  $('analysis-replay').disabled=state.busy||!canReplay(state.run);
  for(const button of $('analysis-quick').querySelectorAll('button'))button.disabled=state.busy||!scope;
  const stale=!!state.run&&scopeKey(state.scope)!==scopeKey(scope);
  $('analysis-stale').classList.toggle('hidden',!stale);
  $('analysis-stale-text').textContent=scope?.source===state.scope?.source?'数据版本或筛选已变化。下面保留上次回答，可按当前范围重新分析。':'当前已切换数据来源。下面保留上次来源的回答，可重新分析当前数据。';
  $('analysis-rerun').disabled=state.busy||!scope||!state.run?.question_id;
 }
 function message(text,failed=false) {
  $('analysis-message').textContent=text;$('analysis-message').classList.toggle('failure',failed);
 }
 async function catalog() {
  try {
   const response=await fetch('/api/analysis/questions'),data=await response.json();
   if(!response.ok)throw Error(data.error||'问题目录读取失败');
   state.questions=data.questions;
   $('analysis-question').innerHTML=Object.entries(categories).map(([kind,label])=>'<optgroup label="'+html(label)+'">'+data.questions.filter(q=>q.kind===kind).map(q=>'<option value="'+html(q.id)+'">'+html(q.text)+'</option>').join('')+'</optgroup>').join('');
   $('analysis-quick').innerHTML=['A01','A05','T01','D03'].map(id=>{const q=data.questions.find(q=>q.id===id);return '<button class="analysis-chip" type="button" data-question="'+id+'">'+html(q.text)+'</button>'}).join('');
   for(const button of $('analysis-quick').querySelectorAll('button'))button.addEventListener('click',()=>{$('analysis-question').value=button.dataset.question;$('analysis-text').value='';submit()});
   $('analysis-catalog-retry').classList.add('hidden');message('支持目录中的 30 条固定问题；也可以输入目录问题原文。');sync();
  }catch(error){message(error.message,true);$('analysis-catalog-retry').classList.remove('hidden')}
 }
 function display(run,scope) {
  state.run=run;state.scope=scope;
  const question=state.questions.find(q=>q.id===run.question_id);
  $('analysis-result').classList.remove('hidden');
  $('analysis-result-title').textContent=question?.text||'问题处理结果';
  $('analysis-result-scope').textContent='回答范围：'+describe(scope);
  $('analysis-badge').textContent=badges[run.verification_status]||'未核验';
  $('analysis-badge').className='analysis-badge '+run.verification_status;
  $('analysis-answer').textContent=question?.dimension&&run.verification_status!=='blocked'?question.definition+' 下方展示当前范围内的聚合结果。':run.answer;
  $('analysis-values').innerHTML=resultMarkup(run,question);
  $('analysis-chart').innerHTML=chartMarkup(run);
  $('analysis-warnings').innerHTML=run.quality_warnings?.length?'<b>与本题相关的数据质量提示</b><p class="caption">检查覆盖整个数据版本，不随本题筛选缩小；各项记录数不能相加当作异常订单总数。</p><ul>'+run.quality_warnings.map(w=>'<li>'+html(w.label)+'：'+html(w.failed_count)+' 条</li>').join('')+'</ul>':'';
  $('analysis-warnings').classList.toggle('hidden',!run.quality_warnings?.length);
  $('analysis-sql').textContent=run.sql||'本题未执行 SQL（口径说明、规则统计或无法回答）。';
  $('analysis-parameters').textContent=JSON.stringify(run.parameters,null,2);
  $('analysis-definition').textContent=question?.definition||'问题未匹配目录，未执行查询。';
  $('analysis-evidence').textContent=JSON.stringify(run.citations,null,2);
  $('analysis-run').textContent=run.run_id;
  $('analysis-snapshot').textContent=run.snapshot_run_id||'未读取';
  $('analysis-fingerprint').textContent=run.input_fingerprint||'未读取';
  $('analysis-verification').textContent=(run.verification.method==='raw_tables_python_decimal'?'从原始数据独立复算':run.verification.method==='quality_rule_reexecution'?'重新执行质量规则核对':run.verification.method==='versioned_definition'?'引用版本化指标定义':run.verification.method==='explicit_refusal'?'数据或操作超出支持范围':'未完成数值核验')+' · 耗时 '+format(run.elapsed_ms)+' 毫秒'+(run.replay_of?' · 原运行 '+run.replay_of+' · '+(run.replay_matches?'重放一致':'重放不一致'):'');
  $('analysis-download').href='/api/analysis/download?'+new URLSearchParams({source:scope.source,run_id:run.run_id});
  $('analysis-download').download=run.run_id+'.json';
  sync();
 }
 async function submit(replaying=false) {
  if(state.busy)return;
  const scope=replaying?state.scope:currentScope();
  if(!scope){message('请先在数据接入中导入文件或连接数据库。',true);return}
  const question=$('analysis-text').value.trim()||$('analysis-question').value;
  if(!replaying&&!question){message('请先选择问题。',true);return}
  const oldRun=state.run;
  state.busy=true;sync();$('analysis-result').setAttribute('aria-busy','true');message(replaying?'正在用原数据版本重新计算…':'正在计算并独立核验，请稍候…');
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),60000);
  try{
   const response=await fetch(replaying?'/api/analysis/replay':'/api/analysis/ask',{
    method:'POST',headers:{'Content-Type':'application/json','X-Zhishu-Local':'1'},signal:controller.signal,
    body:JSON.stringify(replaying?{source:scope.source,run_id:oldRun.run_id}:{...scope,question})});
   const data=await response.json();if(!response.ok)throw Error(data.error||'分析未完成');
   display(data.run,{...scope,snapshot_run_id:data.run.snapshot_run_id,...data.run.filters});message(data.run.verification_status==='blocked'?'当前问题无法给出可靠结论，原因见下方。':'分析已完成，依据与运行记录已保存。');
  }catch(error){message(error.name==='AbortError'?'分析用时较长，请稍后重试；上次回答仍保留。':error.message,true)}
  finally{clearTimeout(timeout);state.busy=false;$('analysis-result').setAttribute('aria-busy','false');sync()}
 }
 $('analysis-form').addEventListener('submit',event=>{event.preventDefault();submit()});
 $('analysis-question').addEventListener('change',()=>{$('analysis-text').value=''});
 $('analysis-replay').addEventListener('click',()=>submit(true));
 $('analysis-rerun').addEventListener('click',()=>{if(state.run?.question_id)$('analysis-question').value=state.run.question_id;$('analysis-text').value='';submit()});
 $('analysis-catalog-retry').addEventListener('click',catalog);
 const previousRender=render;render=function(data){previousRender(data);sync()};
 const previousRefreshSources=refreshSourceList;refreshSourceList=async function(...args){try{return await previousRefreshSources(...args)}finally{sync()}};
 catalog();sync();
})();
