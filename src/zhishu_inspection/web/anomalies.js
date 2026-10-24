/* A report keeps its original source/snapshot even after page data refreshes. */
(() => {
 const html=value=>String(value??'暂无').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const labels={completed_product_amount:'每日商品销售额',completed_order_count:'每日完成订单数',order_product_amount:'单笔订单金额'};
 const statuses={ALERT:'需核查',NORMAL:'未超阈值',INSUFFICIENT_HISTORY:'历史不足',INSUFFICIENT_ACTIVITY:'交易稀疏',INCOMPLETE_DATA:'金额覆盖不足'};
 function scopeKey(scope){return JSON.stringify(['source','snapshot_run_id','start','end','state','category'].map(key=>scope?.[key]??null))}
 function resultsMarkup(run,showAll=false){
  if(!run||run.status==='BLOCKED_QUALITY')return '<p class="caption">质量检查未通过，未运行统计检测。</p>';
  if(run.status==='NO_DATA')return '<p class="caption">所选范围没有可评估的数据。</p>';
  const selected=(run.results||[]).filter(row=>showAll||row.status==='ALERT'),visible=selected.slice(0,200);
  if(!visible.length)return '<p class="caption">当前规则没有检出告警。可勾选“显示全部评估”查看历史不足等状态。</p>';
  return '<div class="table-wrap anomaly-table"><table><thead><tr><th>指标 / 状态</th><th>发生日期</th><th>实际值 / 历史中位数</th><th>解释与证据</th></tr></thead><tbody>'+visible.map(row=>
   '<tr><td><b>'+html(labels[row.metric]||row.metric)+'</b><span class="anomaly-status '+(row.status==='ALERT'?'warning':'neutral')+'">'+(row.severity==='warning'?'警告 · ':'提示 · ')+html(statuses[row.status]||row.status)+'</span></td><td>'+html(row.observed_at)+'</td><td class="anomaly-exact">'+html(row.actual_value)+'<small>历史：'+html(row.baseline_value)+'</small></td><td>'+html(row.explanation_zh)+'<details><summary>查看规则与定位证据</summary><p>'+html(row.rule_id)+' / '+html(row.rule_version)+'</p><pre>'+html(JSON.stringify({threshold:row.threshold,score:row.confidence_or_score,evidence:row.evidence,limitations:row.limitations},null,2))+'</pre></details></td></tr>'
  ).join('')+'</tbody></table></div>'+(selected.length>200?'<p class="caption">页面展示前 200 条；下载 JSON 或 HTML 可查看完整告警与记录。</p>':'');
 }
 if(typeof module!=='undefined')module.exports={scopeKey,resultsMarkup};
 if(typeof document==='undefined')return;
 titles.anomalies=['异常检测，变化有解释','按当前数据版本检查销售额、订单量和单笔金额。'];
 const state={busy:false,loading:false,run:null,scope:null,currentSource:null};
 function currentScope(){
  if(!current)return null;
  return {source:current.active_source||(current.dataset.id==='customer_csv'?'customer':'demo'),
   snapshot_run_id:current.run_id,...current.filters,category:$('anomaly-category').value||null};
 }
 function describe(scope){
  if(!scope)return '请先在数据接入中选择来源';
  const source=connectionState.sources.find(row=>row.id===scope.source)?.name||(scope.source==='customer'?'导入数据':'工作区数据');
  return source+' · '+(scope.start||scope.end?(scope.start||'最早')+' 至 '+(scope.end||'最新'):'全部日期')+' · '+(scope.state||'全部地区')+' · '+(scope.category||'全部品类');
 }
 function sync(){
  const source=current?.active_source||(current?.dataset?.id==='customer_csv'?'customer':current?'demo':null);
  let selected=$('anomaly-category').value||'';
  if(source!==state.currentSource){selected='';state.currentSource=source}
  const categories=[...new Set((current?.categories||[]).map(row=>row.category))];
  if(selected&&!categories.includes(selected))categories.push(selected);
  $('anomaly-category').innerHTML='<option value="">全部品类</option>'+categories.map(value=>'<option value="'+html(value)+'">'+html(value)+'</option>').join('');
  $('anomaly-category').value=selected;
  const scope=currentScope();
  $('anomaly-scope').textContent=describe(scope);
  $('anomaly-submit').disabled=state.busy||state.loading||!scope;
  $('anomaly-category').disabled=state.busy||state.loading||!scope;
  $('anomaly-stale').classList.toggle('hidden',!state.run||scopeKey(scope)===scopeKey(state.scope));
 }
 function message(text,failed=false){$('anomaly-message').textContent=text;$('anomaly-message').classList.toggle('failure',failed)}
 function display(run,scope){
  state.run=run;state.scope=scope;
  $('anomaly-result').classList.remove('hidden');
  $('anomaly-result-scope').textContent='检测范围：'+describe(scope);
  $('anomaly-summary').textContent='完成订单样本 '+run.sample_size+'；规则告警 '+run.alert_count+' 条。不同规则可能指向同一天或订单，不能相加当作异常订单去重数。';
  $('anomaly-values').innerHTML=resultsMarkup(run,$('anomaly-show-all').checked);
  $('anomaly-evidence').textContent=JSON.stringify({snapshot_id:run.snapshot_id,source_fingerprint:run.source_fingerprint,
   run_id:run.run_id,config:run.config,quality_evidence:run.quality_evidence},null,2);
  const query={source:scope.source,run_id:run.run_id};
  $('anomaly-json').href='/api/anomalies/download?'+new URLSearchParams({...query,format:'json'});
  $('anomaly-html').href='/api/anomalies/download?'+new URLSearchParams({...query,format:'html'});
  $('anomaly-snapshot').href='/api/anomalies/snapshot?'+new URLSearchParams(query);
  sync();
 }
 async function submit(){
  if(state.busy||state.loading)return;
  const scope=currentScope();if(!scope){message('请先导入文件或连接数据库。',true);return}
  state.busy=true;sync();message('正在读取当前快照并检查异常…');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000);
  try{
   const response=await fetch('/api/anomalies/detect',{method:'POST',signal:controller.signal,
    headers:{'Content-Type':'application/json','X-Zhishu-Local':'1'},body:JSON.stringify(scope)});
   const data=await response.json();if(!response.ok)throw Error(data.error||'检测未完成');
   if(data.source!==scope.source||data.run.snapshot_id!==scope.snapshot_run_id)throw Error('返回版本与提交范围不一致，请重新检测');
   display(data.run,scope);message('检测完成，结果与来源证据已保存。');
  }catch(error){message(error.name==='AbortError'?'检测用时较长，请稍后重试；上次结果仍保留。':error.message,true)}
  finally{clearTimeout(timer);state.busy=false;sync()}
 }
 $('anomaly-form').addEventListener('submit',event=>{event.preventDefault();submit()});
 $('anomaly-category').addEventListener('change',sync);
 $('anomaly-show-all').addEventListener('change',()=>{if(state.run)$('anomaly-values').innerHTML=resultsMarkup(state.run,$('anomaly-show-all').checked)});
 const previousRender=render;render=function(data){previousRender(data);sync()};
 const previousRefresh=refreshSourceList;refreshSourceList=async function(...args){try{return await previousRefresh(...args)}finally{sync()}};
 if(typeof setBusy==='function'){const previousBusy=setBusy;setBusy=function(value){state.loading=value;previousBusy(value);sync()}}
 sync();
})();
