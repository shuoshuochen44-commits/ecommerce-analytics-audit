const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../src/zhishu_inspection/web/connections.js'),'utf8');
const context={};vm.createContext(context);vm.runInContext(source.split('// Sources refresh')[0],context);
const {mappingSummary,validationMarkup}=context;

test('mapping completion rejects duplicate source selections and missing fields',()=>{
 assert.equal(JSON.stringify(mappingSummary(['订单号','买家编号'],{'订单号':'id','买家编号':'id'})),JSON.stringify({complete:2,total:2,duplicate:true,ready:false}));
 assert.equal(mappingSummary(['订单号','买家编号'],{'订单号':'id'}).ready,false);
 assert.equal(mappingSummary(['订单号','买家编号'],{'订单号':'id','买家编号':'buyer'}).ready,true);
});
test('validation markup escapes column labels and makes bounded errors clear',()=>{
 const html=validationMarkup({valid:false,error_count:51,truncated:true,issues:[{row_number:4,source_column:'<script>',target_field:'订单号',reason:'重复',suggestion:'合并明细'}]});
 assert.match(html,/51/);assert.match(html,/4/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/前 50/);
});
test('successful validation states rows and exact date range',()=>{
 const html=validationMarkup({valid:true,row_count:12000,date_min:'2026-01-01',date_max:'2026-03-31'});
 assert.match(html,/12000/);assert.match(html,/2026-01-01/);assert.match(html,/2026-03-31/);
});

function browserHarness(fetch){
 const nodes=new Map();
 function element(){return {value:'upload',checked:false,disabled:false,textContent:'',innerHTML:'',dataset:{},files:[],listeners:{},classList:{toggle(){},add(){},remove(){}},addEventListener(name,callback){this.listeners[name]=callback},querySelector(){return element()},querySelectorAll(){return []},after(){},before(){},append(){},setAttribute(){}}}
 const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const context={titles:{},$:get,document:{createElement:element,querySelector:element},window:{addEventListener(){}},EventSource:class{close(){}addEventListener(){}},setInterval(){},clearInterval(){},setTimeout,clearTimeout,AbortController,File:class{},Blob:class{},fetch,render(){},esc:String,num:String,activeSource:'demo',current:null};
 vm.createContext(context);vm.runInContext(source,context);
 get('connection-table').value='{"table":"orders","schema":null}';get('connection-confirm-grain').checked=true;
 get('connection-mapping').querySelectorAll=()=>[{dataset:{role:'订单号'},value:'id'}];
 vm.runInContext("connectionState.selected='src_test';connectionState.fields=['订单号'];connectionState.preview={};connectionState.sources=[{id:'src_test'}]",context);
 return {context,get};
}

test('re-preview while a check is in flight invalidates the older response',async()=>{
 let complete;const {context}=browserHarness(()=>new Promise(resolve=>{complete=resolve}));
 const pending=vm.runInContext('checkMappedData()',context);
 vm.runInContext('connectionState.previewVersion++',context);
 complete({ok:true,json:async()=>({validation:{valid:true,row_count:1}})});
 await assert.rejects(pending,/变化/);
});

test('save does not submit configure when full-table validation fails',async()=>{
 const requests=[];const {get}=browserHarness(async(path)=>{requests.push(path);return {ok:true,json:async()=>({validation:{valid:false,error_count:1,issues:[]}})}});
 await get('connection-save').listeners.click();
 assert.deepEqual(requests,['/api/sources/validate']);
 assert.match(get('connection-message').textContent,/未通过/);
});

test('late configure errors from a previous source do not replace current diagnostics',async()=>{
 let finishConfigure,configured;
 const started=new Promise(resolve=>{configured=resolve});
 const {context,get}=browserHarness(async(path)=>{
  if(path==='/api/sources/validate')return {ok:true,json:async()=>({validation:{valid:true,row_count:1}})};
  if(path==='/api/sources/configure'){configured();return new Promise(resolve=>{finishConfigure=resolve})}
  throw Error('unexpected request '+path);
 });
 const pending=get('connection-save').listeners.click();await started;
 vm.runInContext("connectionState.selected='src_other';connectionState.previewVersion++",context);
 get('connection-validation-result').innerHTML='B diagnostics';get('connection-message').textContent='B message';
 finishConfigure({ok:false,json:async()=>({error:'A failure',diagnostics:{valid:false,error_count:1,issues:[{row_number:777,source_column:'id',target_field:'订单号',reason:'重复',suggestion:'修改'}]}})});
 await pending;
 assert.equal(get('connection-validation-result').innerHTML,'B diagnostics');
 assert.equal(get('connection-message').textContent,'B message');
});

test('late configure success refreshes its own source without replacing another editor message',async()=>{
 let finishConfigure,configured;const refreshed=[];
 const started=new Promise(resolve=>{configured=resolve});
 const {context,get}=browserHarness(async(path,options)=>{
  if(path==='/api/sources/validate')return {ok:true,json:async()=>({validation:{valid:true,row_count:1}})};
  if(path==='/api/sources/configure'){configured();return new Promise(resolve=>{finishConfigure=resolve})}
  if(path==='/api/sources/refresh'){refreshed.push(JSON.parse(options.body).source_id);return {ok:true,json:async()=>({})}}
  throw Error('unexpected request '+path);
 });
 context.refreshSourceList=async()=>{};
 const pending=get('connection-save').listeners.click();await started;
 vm.runInContext("connectionState.selected='src_other';connectionState.previewVersion++",context);
 get('connection-message').textContent='B message';
 finishConfigure({ok:true,json:async()=>({})});await pending;
 assert.deepEqual(refreshed,['src_test']);
 assert.equal(get('connection-message').textContent,'B message');
});
