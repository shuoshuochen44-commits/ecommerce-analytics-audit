// Practical actions share the currently displayed source, filters, and immutable version.
let orderPage=1, orderSequence=0, uploadContent=null, importBusy=false, orderSourceKey=null;
const orderStatusNames={delivered:'已完成',shipped:'已发货',processing:'处理中',canceled:'已取消',created:'已创建',approved:'已确认',invoiced:'已开票',unavailable:'不可用'};
const metricNames={completed_product_amount:'商品销售额',completed_order_count:'已完成订单',completed_average_order_value:'平均每单金额',completed_unique_customer_count:'购买人数'};

function renderTools(d){
 const sourceKey=activeSource+':'+d.run_id;
 if(orderSourceKey!==sourceKey){$('order-search').value='';$('order-status').value='';orderSourceKey=sourceKey}
 $('customer-option').disabled=!d.customer_available;
 $('customer-option').textContent=d.customer_available?'导入数据':'导入数据（未导入）';
 $('data-source').value=activeSource;
 if(d.dataset.id==='customer_csv'){
  $('region-label').textContent='看哪个省';
  $('quality-note').textContent='基础指标已通过核对。表格未提供交付日期时，会保留缺失提示；金额差异请按订单核查。';
 }
 const comparison=d.comparison;
 $('comparison').classList.toggle('hidden',!comparison?.available);
 if(!comparison||!comparison.available){
  $('comparison').innerHTML='<h2>和上个月比一比</h2><p class="caption">'+esc(comparison?.reason||'选择一个月份查看比较')+'</p>';
 }else{
  $('comparison').innerHTML='<h2>和上个月比一比</h2><p class="caption">对比 '+esc(monthLabel(comparison.previous_start.slice(0,7)))+' · 相同地区范围</p><div class="comparison-grid">'+Object.entries(comparison.changes).map(([key,v])=>{
   const pct=v.percent===null?'暂无可比百分比':(Number(v.percent)>0?'↑ ':Number(v.percent)<0?'↓ ':'持平 ')+num(Math.abs(Number(v.percent)),2)+'%';
   const diff=v.difference===null?'本期或上期无可用金额':Number(v.difference)===0?'与上月相同':(Number(v.difference)>0?'增加 ':'减少 ')+num(Math.abs(Number(v.difference)),key.includes('amount')||key.includes('value')?2:0)+(key.includes('amount')||key.includes('value')?' '+unit():key.includes('customer')?' 人':' 单');
   return '<div><span>'+esc(metricNames[key])+'</span><b>'+esc(pct)+'</b><span>'+esc(diff)+'</span></div>';
  }).join('')+'</div>';
 }
 const technicalParams=new URLSearchParams({source:activeSource,run_id:d.run_id});
 document.querySelector('a[href^="/report.md"]').href='/report.md?'+technicalParams;
 document.querySelector('a[href^="/manifest.json"]').href='/manifest.json?'+technicalParams;
 ++orderSequence;$('order-submit').disabled=false;$('order-body').innerHTML='';$('order-message').textContent='点击“查订单”查看当前范围的明细。';
 $('order-export').setAttribute('aria-disabled','true');$('order-prev').disabled=true;$('order-next').disabled=true;$('order-page').textContent='';
 if($('lookup').classList.contains('active'))loadOrders(1);
}

function orderParams(page){
 const params=paramsFor(current.filters);params.set('run_id',current.run_id);
 params.set('source',current.dataset.id==='customer_csv'?'customer':'demo');
 params.set('search',$('order-search').value.trim());params.set('status',$('order-status').value);
 if(page)params.set('page',page);return params;
}

async function loadOrders(page=1){
 if(!current)return;
 const request=++orderSequence,version=current.run_id,params=orderParams(page);
 $('order-submit').disabled=true;$('order-prev').disabled=true;$('order-next').disabled=true;
 $('order-export').setAttribute('aria-disabled','true');$('order-message').classList.remove('failure');$('order-message').textContent='正在查找订单…';
 $('order-body').innerHTML='';$('order-page').textContent='';
 try{
  const response=await fetch('/api/orders?'+params),d=await response.json();
  if(request!==orderSequence||version!==current.run_id)return;
  if(!response.ok)throw Error(d.error||'订单查询失败');
  orderPage=page;
  $('order-scope').textContent=$('scope').textContent+' · 包含取消和未交付订单 · 金额单位：'+current.dataset.currency_label;
  $('order-message').textContent='共找到 '+num(d.total)+' 笔订单，每页显示 20 笔。';
  $('order-body').innerHTML=d.orders.length?d.orders.map(r=>'<tr><td class="order-id">'+esc(r.order_id)+'<p class="caption">'+esc(r.customer_unique_id)+'</p></td><td>'+esc(r.purchase_date)+'<p class="caption">'+esc(r.customer_state||'未填写地区')+'</p></td><td>'+esc(orderStatusNames[r.order_status]||r.order_status)+'</td><td>'+num(r.product_amount,2)+'</td><td>'+num(r.freight_amount,2)+'</td><td>'+num(r.payment_amount,2)+'</td><td><span class="status '+(r.reconciliation_status==='matched'?'':'warn')+'">'+esc(statusNames[r.reconciliation_status]||r.reconciliation_status)+'</span></td></tr>').join(''):'<tr><td colspan="7">没有找到匹配的订单，换个编号或状态试试。</td></tr>';
  $('order-page').textContent='第 '+page+' / '+Math.max(1,Math.ceil(d.total/20))+' 页';$('order-prev').disabled=page<=1;$('order-next').disabled=page*20>=d.total;
  params.delete('page');$('order-export').href='/orders.csv?'+params;$('order-export').setAttribute('aria-disabled','false');
 }catch(e){if(request!==orderSequence)return;$('order-message').classList.add('failure');$('order-message').textContent='查询未完成：'+e.message+'。请检查启动窗口并重新查询。'}
 finally{if(request===orderSequence)$('order-submit').disabled=false}
}

$('data-source').addEventListener('change',()=>{activeSource=$('data-source').value;load(true)});
$('order-form').addEventListener('submit',e=>{e.preventDefault();loadOrders(1)});
function invalidateOrderFilter(){
 ++orderSequence;$('order-submit').disabled=false;$('order-prev').disabled=true;$('order-next').disabled=true;
 $('order-export').setAttribute('aria-disabled','true');$('order-body').innerHTML='';$('order-page').textContent='';
 $('order-message').textContent='查询条件已改变，请点击“查询订单”查看新结果。';
}
$('order-search').addEventListener('input',invalidateOrderFilter);$('order-status').addEventListener('change',invalidateOrderFilter);
$('order-prev').addEventListener('click',()=>loadOrders(orderPage-1));$('order-next').addEventListener('click',()=>loadOrders(orderPage+1));
$('order-export').addEventListener('click',e=>{if($('order-export').getAttribute('aria-disabled')==='true')e.preventDefault()});

function importMessage(text,failure=false){$('import-message').textContent=text;$('import-message').classList.toggle('failure',failure)}
function setImportBusy(busy){importBusy=busy;for(const id of ['import-preview','import-file','import-confirm'])$(id).disabled=busy}
$('import-file').addEventListener('change',()=>{uploadContent=null;$('import-preview-box').classList.add('hidden');importMessage('已选择文件，请先点击“检查并预览”。')});

async function submitImport(path,content){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),120000);
 try{
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'text/csv','X-Zhishu-Local':'1'},body:content,signal:controller.signal});
  const data=await response.json();if(!response.ok)throw Error(data.error||'处理失败');return data;
 }catch(e){if(e.name==='AbortError')throw Error('等待时间较长，请稍后查看“我的导入数据”或启动窗口；不要连续提交');throw e}
 finally{clearTimeout(timeout)}
}

$('import-preview').addEventListener('click',async()=>{
 const file=$('import-file').files[0];uploadContent=null;$('import-preview-box').classList.add('hidden');
 if(!file||!file.name.toLowerCase().endsWith('.csv')){importMessage('请先选择 CSV 文件。Excel 表格请另存为“CSV UTF-8”。',true);return}
 if(file.size>5*1024*1024||!file.size){importMessage('请选择非空、且不超过 5 MB 的 CSV 文件。',true);return}
 setImportBusy(true);importMessage('正在检查表格，尚未写入数据…');
 try{
  const bytes=new Uint8Array(await file.arrayBuffer()),d=await submitImport('/api/import/preview',bytes);uploadContent=bytes;
  $('import-summary').innerHTML='<b>检查通过，请核对后确认</b>共 '+num(d.order_count)+' 笔订单，日期 '+esc(d.date_min)+' 至 '+esc(d.date_max)+'；已完成订单商品金额 '+num(d.completed_amount,2)+' 元。';
  $('import-samples').innerHTML=d.samples.map(r=>'<tr><td>'+esc(r['订单号'])+'</td><td>'+esc(r['下单日期'])+'</td><td>'+esc(r['省份'])+'</td><td>'+num(r['商品金额'],2)+'</td><td>'+esc(r['订单状态'])+'</td></tr>').join('');
  $('import-preview-box').classList.remove('hidden');importMessage('预览的是前五笔订单。当前还未导入，请点击下方确认按钮。');
 }catch(e){importMessage(e.message,true)}finally{setImportBusy(false)}
});
$('import-confirm').addEventListener('click',async()=>{
 if(!uploadContent||importBusy)return;setImportBusy(true);importMessage('正在导入、核对并生成看板，请稍等…');
 try{
  await submitImport('/api/import/confirm',uploadContent);activeSource='customer';
  const loaded=await load(true);uploadContent=null;$('import-preview-box').classList.add('hidden');
  importMessage('导入成功，可通过页面上方切换“我的导入数据”和演示数据。');if(loaded)tab('overview');
 }catch(e){importMessage(e.message,true)}finally{setImportBusy(false)}
});
