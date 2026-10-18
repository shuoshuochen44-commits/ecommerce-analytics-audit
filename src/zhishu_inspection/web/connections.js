// Sources refresh in the backend. SSE announces only source state and version IDs.
titles.connections=['连接数据，持续掌握经营','导入表格或连接数据库，自主选择手动、定时和变更监测。'];
const connectionState={sources:[],fields:[],selected:null,busy:false,preview:null};
const sourceStateNames={configured:'等待字段确认',ready:'已就绪',syncing:'同步中',error:'同步失败',credentials_required:'需要重新填写密码'};
const sourceKindNames={sqlite:'SQLite',duckdb:'DuckDB',mysql:'MySQL',mariadb:'MariaDB',postgresql:'PostgreSQL',mssql:'SQL Server',oracle:'Oracle'};
const liveBox=document.createElement('aside');liveBox.id='source-live';liveBox.className='source-live hidden';document.querySelector('.heading').after(liveBox);
const sourceGroup=document.createElement('optgroup');sourceGroup.label='已连接数据源';$('data-source').append(sourceGroup);
function sourceMessage(text,failure=false){$('connection-message').textContent=text;$('connection-message').classList.toggle('failure',failure)}
function dateLabel(value){return value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'尚未成功同步'}
function currentSource(){return connectionState.sources.find(s=>s.id===connectionState.selected)}
async function sourceRequest(path,data,extra={}){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),45000);
 try{
  const binary=data instanceof File||data instanceof Blob;
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':binary?'application/octet-stream':'application/json','X-Zhishu-Local':'1',...extra},body:binary?data:JSON.stringify(data),signal:controller.signal});
  const result=await response.json();if(!response.ok)throw Error(result.error||'接入未完成');return result;
 }catch(error){if(error.name==='AbortError')throw Error('来源读取超时，请检查连接或缩小数据范围');throw error}
 finally{clearTimeout(timeout)}
}
function renderSourceStatus(){
 const source=connectionState.sources.find(s=>s.id===activeSource);
 liveBox.classList.toggle('hidden',!source);
 if(source){
  const version=current?.active_source===source.id?current.run_id:'未展示';
  liveBox.innerHTML='<div><strong>'+esc(source.name)+' · '+esc(sourceStateNames[source.state]||source.state)+'</strong><p class="caption">最近检查 '+esc(dateLabel(source.last_check_at))+' · 成功更新 '+esc(dateLabel(source.last_success_at))+' · 最近采集/核验 '+esc(source.last_attempt_ms===undefined?'—':source.last_attempt_ms+' ms')+'</p><p class="caption">当前展示版本 '+esc(version)+(source.error?' · '+esc(source.error):'')+'</p></div><button class="button" id="source-live-refresh">立即刷新数据源</button>';
  $('source-live-refresh').disabled=source.state==='syncing'||!Object.keys(source.mapping||{}).length||source.credentials_required;
  $('source-live-refresh').addEventListener('click',()=>refreshSource(source.id));
 }
 const selected=currentSource();
 if(selected){
  $('connection-editor-state').textContent=(sourceStateNames[selected.state]||selected.state)+' · 最近检查 '+dateLabel(selected.last_check_at)+' · 成功更新 '+dateLabel(selected.last_success_at)+(selected.error?' · '+selected.error:'');
  $('connection-view').disabled=!selected.available;
  $('connection-manual').disabled=selected.state==='syncing'||!Object.keys(selected.mapping||{}).length||selected.credentials_required;
 }
}
async function refreshSourceList(reloadChanged=false){
 const response=await fetch('/api/sources');const data=await response.json();if(!response.ok)throw Error(data.error||'无法读取数据源');
 connectionState.sources=data.sources;connectionState.fields=data.fields;
 const defaultOption=$('data-source').querySelector('option[value="demo"]');defaultOption.textContent='工作区数据';defaultOption.hidden=!data.workspace_available;
 $('customer-option').hidden=!data.customer_available;
 $('data-source').disabled=!(data.workspace_available||data.customer_available||data.sources.some(s=>s.available));
 sourceGroup.innerHTML=data.sources.filter(s=>s.available).map(s=>'<option value="'+esc(s.id)+'">'+esc(s.name)+'</option>').join('');
 $('data-source').value=activeSource;
 $('connection-list').innerHTML=data.sources.length?data.sources.map(s=>'<article class="source-card '+(s.id===connectionState.selected?'selected':'')+'"><div class="card-head"><h3>'+esc(s.name)+'</h3><span class="source-badge '+(s.state==='error'?'error':'')+'">'+esc(sourceStateNames[s.state]||s.state)+'</span></div><p class="caption">'+esc(s.kind==='file'?(s.watchable?'本机文件 · 可监测':'上传副本'):'数据库连接')+' · '+esc(s.table||'未选择表')+'</p><p class="caption">定时 '+esc(s.refresh.interval_seconds?s.refresh.interval_seconds+' 秒':'关闭')+' · 监测 '+esc(s.refresh.watch_seconds?s.refresh.watch_seconds+' 秒':'关闭')+'</p><p class="caption">最近成功 '+esc(dateLabel(s.last_success_at))+'</p>'+(s.error?'<p class="caption failure">'+esc(s.error)+'</p>':'')+'<button class="text-btn" data-connection-id="'+esc(s.id)+'">配置与刷新 →</button></article>').join(''):'<p class="caption">尚未配置数据源。选择文件，或填写数据库连接后开始。</p>';
 for(const button of $('connection-list').querySelectorAll('[data-connection-id]'))button.addEventListener('click',()=>openSource(button.dataset.connectionId));
 for(const capability of data.database_capabilities){
  const option=$('connection-kind').querySelector('option[value="'+capability.kind+'"]');
  if(option){option.disabled=!capability.installed;option.textContent=(sourceKindNames[capability.kind]||capability.kind)+' 数据库'+(!capability.installed?'（需安装驱动）':capability.tested?'（本机实测）':'（需实测连接）')}
 }
 renderSourceStatus();
 if(!current){
  const first=data.sources.find(s=>s.available);
  if(first){activeSource=first.id;await load(true)}
 }
 const selected=connectionState.sources.find(s=>s.id===activeSource);
 if(reloadChanged&&selected?.available&&current?.active_source===selected.id&&current.run_id!==selected.snapshot_run_id)await load(false);
 return data;
}
function connectionFormMode(){
 const kind=$('connection-kind').value,network=!['upload','localfile','sqlite','duckdb'].includes(kind);
 $('connection-upload').classList.toggle('hidden',kind!=='upload');$('connection-path-box').classList.toggle('hidden',!['localfile','sqlite','duckdb'].includes(kind));$('connection-network').classList.toggle('hidden',!network);
 $('connection-submit').textContent=kind==='upload'?'读取文件并预览':kind==='localfile'?'读取本机文件':'测试连接并列出表';
 const ports={mysql:3306,mariadb:3306,postgresql:5432,mssql:1433,oracle:1521};if(ports[kind])$('connection-port').value=ports[kind];
}
$('connection-kind').addEventListener('change',connectionFormMode);
$('connection-form').addEventListener('submit',async event=>{
 event.preventDefault();if(connectionState.busy)return;connectionState.busy=true;$('connection-submit').disabled=true;sourceMessage('正在读取来源、识别表和字段…');
 try{
  const kind=$('connection-kind').value;let result;
  if(kind==='upload'){
   const file=$('connection-file').files[0];if(!file)throw Error('请先选择数据文件');if(file.size>20*1024*1024)throw Error('文件超过 20 MB');
   result=await sourceRequest('/api/sources/upload',file,{'X-Zhishu-Filename':encodeURIComponent(file.name)});
  }else if(kind==='localfile'){
   result=await sourceRequest('/api/sources/register',{kind:'file',path:$('connection-path').value.trim()});
  }else{
   const config=['sqlite','duckdb'].includes(kind)?{kind,path:$('connection-path').value.trim()}:{kind,host:$('connection-host').value.trim(),port:Number($('connection-port').value),database:$('connection-database').value.trim(),username:$('connection-user').value.trim(),password:$('connection-password').value};
   result=await sourceRequest('/api/sources/register',{kind:'database',config});$('connection-password').value='';
  }
  await refreshSourceList();await openSource(result.source.id);sourceMessage('来源已读取，请核对预览并确认九个字段的对应关系。');
 }catch(error){sourceMessage(error.message,true)}finally{connectionState.busy=false;$('connection-submit').disabled=false}
});
async function openSource(id){
 connectionState.selected=id;const source=currentSource();if(!source)return;
 $('connection-editor').classList.remove('hidden');$('connection-editor-title').textContent=source.name+' · 预览与字段映射';
 $('connection-table').innerHTML=source.tables.map(t=>'<option value="'+esc(JSON.stringify({table:t.name,schema:t.schema??null}))+'">'+esc((t.schema?t.schema+'.':'')+t.name)+'</option>').join('');
 $('connection-table').value=JSON.stringify({table:source.table,schema:source.schema??null});
 $('connection-interval-enabled').checked=source.refresh.interval_seconds!==null;$('connection-interval').value=source.refresh.interval_seconds||30;
 $('connection-watch-enabled').checked=source.refresh.watch_seconds!==null;$('connection-watch').value=source.refresh.watch_seconds||2;$('connection-watch-enabled').disabled=!source.watchable;
 $('connection-watch-note').textContent=source.watchable?'变更监测会读取并比较来源，成功生成新版本后推送页面。请根据数据规模选择间隔。':'上传的是静态副本；需要监测原文件时，请选择“监测本机文件”。';
 $('connection-confirm-grain').checked=Object.keys(source.mapping||{}).length===connectionState.fields.length;
 $('connection-reconnect').classList.toggle('hidden',!source.credentials_required);
 await previewSource();await refreshSourceList();
}
async function previewSource(){
 const source=currentSource();if(!source)return;
 try{
  if(source.credentials_required){
   if(!$('connection-reconnect-password').value)throw Error('重启后需要重新填写连接密码，再点击“重新预览”。');
   await sourceRequest('/api/sources/credentials',{source_id:source.id,password:$('connection-reconnect-password').value});$('connection-reconnect-password').value='';$('connection-reconnect').classList.add('hidden');await refreshSourceList();
  }
  const choice=JSON.parse($('connection-table').value);
  const data=await sourceRequest('/api/sources/preview',{source_id:source.id,...choice});connectionState.preview=data.preview;
  const preview=data.preview;$('connection-preview-note').textContent='共 '+num(preview.row_count)+' 行 · '+num(preview.columns.length)+' 列 · 下方只展示前五行；分析使用通过限额检查的完整选中表。';
  $('connection-preview-head').innerHTML='<tr>'+preview.columns.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>';
  $('connection-preview-body').innerHTML=preview.samples.map(row=>'<tr>'+preview.columns.map(c=>'<td>'+esc(row[c])+'</td>').join('')+'</tr>').join('');
  const same=choice.table===source.table&&(choice.schema??null)===(source.schema??null);
  const mapping=same&&Object.keys(source.mapping||{}).length?source.mapping:data.suggested_mapping;
  $('connection-mapping').innerHTML=connectionState.fields.map((field,index)=>'<div><label for="connection-map-'+index+'">业务字段：'+esc(field)+'</label><select id="connection-map-'+index+'" data-role="'+esc(field)+'"><option value="">请选择来源列</option>'+preview.columns.map(c=>'<option value="'+esc(c)+'"'+(mapping[field]===c?' selected':'')+'>'+esc(c)+'</option>').join('')+'</select></div>').join('');
  renderSourceStatus();
 }catch(error){connectionState.preview=null;$('connection-mapping').innerHTML='';$('connection-preview-body').innerHTML='';sourceMessage(error.message,true)}
}
$('connection-preview').addEventListener('click',previewSource);
$('connection-table').addEventListener('change',()=>{$('connection-confirm-grain').checked=false;previewSource()});
function refreshSettings(){return {interval_seconds:$('connection-interval-enabled').checked?Number($('connection-interval').value):null,watch_seconds:$('connection-watch-enabled').checked?Number($('connection-watch').value):null}}
$('connection-save').addEventListener('click',async()=>{
 const source=currentSource();if(!source||connectionState.busy)return;connectionState.busy=true;$('connection-save').disabled=true;
 try{
  if(!connectionState.preview)throw Error('请先完成来源表预览');if(!$('connection-confirm-grain').checked)throw Error('请先确认订单粒度与人民币金额口径');
  const mapping={};for(const select of $('connection-mapping').querySelectorAll('select')){if(!select.value)throw Error('请完成全部九个字段映射');mapping[select.dataset.role]=select.value}
  await sourceRequest('/api/sources/configure',{source_id:source.id,...JSON.parse($('connection-table').value),mapping,refresh:refreshSettings()});
  await refreshSource(source.id);sourceMessage('已保存映射，正在读取并核验。完成后可在看板中查看。');
 }catch(error){sourceMessage(error.message,true)}finally{connectionState.busy=false;$('connection-save').disabled=false}
});
async function refreshSource(id){
 try{await sourceRequest('/api/sources/refresh',{source_id:id});await refreshSourceList();sourceMessage('刷新已提交；数据未变化时保留原版本，失败时保留上次成功结果。')}
 catch(error){sourceMessage(error.message,true)}
}
$('connection-manual').addEventListener('click',()=>{if(currentSource())refreshSource(currentSource().id)});
$('connection-save-refresh').addEventListener('click',async()=>{
 const source=currentSource();if(!source)return;
 try{await sourceRequest('/api/sources/configure',{source_id:source.id,refresh:refreshSettings()});await refreshSourceList();sourceMessage('刷新设置已保存。手动、定时与变更监测共用采集流程。')}
 catch(error){sourceMessage(error.message,true)}
});
$('connection-view').addEventListener('click',async()=>{const source=currentSource();if(!source?.available)return;activeSource=source.id;await refreshSourceList();if(await load(true))tab('overview')});
$('connection-remove').addEventListener('click',async()=>{
 const source=currentSource();if(!source)return;
 try{await sourceRequest('/api/sources/remove',{source_id:source.id});connectionState.selected=null;$('connection-editor').classList.add('hidden');if(activeSource===source.id){current=null;activeSource='demo';tab('connections')}await initializeWorkspace();sourceMessage('已移除连接配置，历史快照仍保留。')}
 catch(error){sourceMessage(error.message,true)}
});
$('connection-list-refresh').addEventListener('click',()=>refreshSourceList(true).catch(error=>sourceMessage(error.message,true)));
$('data-source').addEventListener('change',renderSourceStatus);
const baseRender=render;render=function(data){baseRender(data);renderSourceStatus()};
const sourceEvents=new EventSource('/api/sources/events');
sourceEvents.onopen=()=>{$('connection-stream-state').textContent='更新推送已连接 · 采集完成后通知页面'};
sourceEvents.onerror=()=>{$('connection-stream-state').textContent='推送暂时断开，正在重连；仍保留当前成功结果'};
sourceEvents.addEventListener('source',async event=>{try{const change=JSON.parse(event.data);await refreshSourceList(change.type==='updated'||change.type==='reset')}catch(error){sourceMessage('更新状态暂时无法读取，正在等待重连。',true)}});
const statusPoll=setInterval(()=>refreshSourceList(true).catch(()=>{}),10000);
window.addEventListener('beforeunload',()=>{sourceEvents.close();clearInterval(statusPoll)});
connectionFormMode();
$('application-exit').addEventListener('click',async()=>{
 try{await sourceRequest('/api/application/exit',{});sourceEvents.close();clearInterval(statusPoll);document.querySelector('main').textContent='智数巡检已退出，可以关闭此页面。'}
 catch(error){sourceMessage(error.message,true)}
});
async function initializeWorkspace(){
 try{
  const data=await refreshSourceList();
  if(current)return;
  if(data.customer_available){activeSource='customer';await load(true)}
  else if(data.workspace_available){activeSource='demo';await load(true)}
  else{tab('connections');$('error').classList.add('hidden');$('busy').classList.add('hidden');$('data-source').disabled=true;$('download').setAttribute('aria-disabled','true')}
 }catch(error){tab('connections');sourceMessage(error.message,true)}
}
