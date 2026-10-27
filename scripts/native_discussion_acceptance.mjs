// Actual 15-node project, real agents, original business modules, real SDK and API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {Bridge} from '../adapt/harness/framework/bridge.js';
import {NativeRunner} from '../adapt/harness/native/runner.mjs';
import {OfficialToolsRunner} from '../adapt/harness/official/official-runner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)), directory=path.resolve(process.argv[2]);
const key=process.env.DEEPSEEK_API_KEY,base=(process.env.DEEPSEEK_BASE_URL??'https://api.deepseek.com').replace(/\/$/,''),model=process.env.DEEPSEEK_MODEL??'deepseek-flash';
if(!key)throw Error('Missing configured DeepSeek API key');
const redact=value=>String(value?.stack??value).split(key).join('[已隐藏密钥]');
const calls=[];let requests=0,stage='setup';
const gateway=http.createServer(async(req,res)=>{
 try{
  let raw='';for await(const part of req)raw+=part;
  const id=++requests;
  if(id>360){res.writeHead(429,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'Acceptance request budget exceeded'}}));return;}
  const entry={request:id,stage,started:Date.now()};calls.push(entry);
  console.log(JSON.stringify({stage:'api_start',phase:stage,request:id}));
  const upstream=await fetch(base+req.url.replace(/^\/v1/,''),{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key},body:raw,signal:AbortSignal.timeout(180000),redirect:'error'});
  entry.status=upstream.status;
  res.writeHead(upstream.status,{'Content-Type':upstream.headers.get('content-type')??'application/json'});
  const decoder=new TextDecoder();let pending='';
  for await(const chunk of upstream.body){
   res.write(chunk);pending+=decoder.decode(chunk,{stream:true});
   const lines=pending.split('\n');pending=lines.pop();
   for(const line of lines){if(!line.startsWith('data:'))continue;try{
    const value=JSON.parse(line.slice(5).trim());
    if(value.usage){const usage=value.usage;entry.usage={input:usage.prompt_tokens??0,output:usage.completion_tokens??0,total:usage.total_tokens??0,cached:usage.prompt_cache_hit_tokens??usage.prompt_tokens_details?.cached_tokens??0};}
   }catch{}}
  }
  res.end();entry.elapsed_ms=Date.now()-entry.started;
  console.log(JSON.stringify({stage:'api_end',...entry}));
 }catch(error){if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:redact(error)}}));}
});
await new Promise(resolve=>gateway.listen(0,'127.0.0.1',resolve));
const profile={kind:'api-key',protocol:'openai-completions',base_url:'http://127.0.0.1:'+gateway.address().port+'/v1',api_key:'acceptance-proxy',
 signature:crypto.createHash('sha256').update('newcore-discussion:'+base+':'+model).digest('hex'),model:{model,maxTokens:10000,contextWindow:128000}};
const evidence={mode:'discussion_collaboration',directory,started:new Date().toISOString(),real_api:true,model,stages:[],turns:[],api_calls:calls,
 baseline_limit:'Old groups script refers to obsolete actor/task interfaces. Current actual application exercises discussion/session, four-way Git collaboration and acceptance; no same-task old performance baseline.'};
const save=async()=>fs.writeFile(path.join(directory,'verification.json'),JSON.stringify(evidence,null,2));
let bridge,native,official;
async function start(){
 official=new OfficialToolsRunner(directory);
 native=new NativeRunner(directory,(method,p)=>bridge.call(method,p,86460000),{noCredentials:true,modelResolver:async()=>profile});
 bridge=new Bridge(path.join(root,'.venv-runtime/Scripts/python.exe'),directory,['-B','-X','utf8','-m','adapt.harness.backend.server'],
                   {PYTHONPATH:root,NEXARBOR_APPLICATION:'discussion_collaboration'},
                   (method,p)=>method==='official-tool-invoke'?official.request('invoke',p):native.request(method,p));
 bridge.notifications.add(()=>native.notify());
}
async function stop(){await native?.close();await bridge?.close();await official?.close();bridge=null;native=null;official=null;}
const moduleState=(state,node,id)=>state.network.nodes.find(n=>n.node_id===node).tables.modules.find(m=>m.module_id===id).state;
const local=(node,id,operation,args={})=>bridge.call('module_call',{node_id:node,module_id:id,operation,arguments:args},86460000);
const run=async(actor,text)=>{const result=await bridge.call('executor_run',{actor,text},86460000);evidence.turns.push({actor,...result});await save();assert.equal(result.status,'completed');return result;};
const measure=async(name,action)=>{
 stage=name;const started=Date.now(),first=calls.length;
 console.log(JSON.stringify({stage:'phase_start',phase:name}));
 const value=await action();
 const selected=calls.slice(first),usage=selected.reduce((sum,entry)=>{for(const key of ['input','output','total','cached'])sum[key]+=entry.usage?.[key]??0;return sum;},{input:0,output:0,total:0,cached:0});
 const result={phase:name,elapsed_ms:Date.now()-started,requests:selected.length,usage};evidence.stages.push(result);await save();
 console.log(JSON.stringify({stage:'phase_end',...result}));return value;
};
const DISC='discussion.session.rev_697d80a33d',BOARD='collab.board.rev_9191e2380f.rev_96569f0263',GIT='git.integrator.rev_2863bbe53e.rev_c376775a7e';
const repo=path.join(directory,'workspace/repository');
function git(args,cwd=repo){const result=spawnSync('git',args,{cwd,encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr||result.stdout);return result.stdout.trim();}
const task=`请实现 workspace/repository/README.md 中的四项小功能。使用编排工具启动一次 rounds=1 的讨论，Leader 必须产出恰好四个独立任务，每项含该模块及其测试两个独占路径，由四名执行成员各自主认领一项。不要改 README 或共同文件。每位执行成员先读取自己的协作入口取得 self.branch，然后从 main 创建独立 worktree；实现、运行标准库 unittest、提交到自己的分支，complete 标记任务并 submit 提交真实哈希。不要替其他成员编码或提交。本轮根入口只 start 一次并返回 run 编号，不轮询状态、不调用 handoff/integrate/promote。请把这些协作要求写清楚传给讨论组。`;
try{
 await fs.mkdir(repo,{recursive:true});git(['init','-b','main']);git(['config','user.name','Nexarbor acceptance']);git(['config','user.email','acceptance@localhost']);
 await fs.writeFile(path.join(repo,'README.md'),`# 四项独立文本功能验收

使用 Python 标准库，无第三方依赖。四名成员各认领一个任务，每人只提交自己的模块与 tests/test_对应模块.py，不修改公共文件。

1. whitespace.py: normalize_whitespace(text) -> str，把任何空白序列合为一个空格并去掉首尾空白，支持 Unicode。测试 tests/test_whitespace.py。
2. words.py: count_words(text) -> int，按任意空白划分计数，空串或纯空白为 0。测试 tests/test_words.py。
3. lines.py: nonempty_lines(text) -> list[str]，按 splitlines 切分，逐行 strip，删除空行。测试 tests/test_lines.py。
4. clipping.py: clip_text(text, limit) -> str，返回前 limit 个 Unicode 字符；limit 为 0 返回空串，负数必须 ValueError。测试 tests/test_clipping.py。

每人用独立分支/worktree，branch 从协作入口 read.self.branch 获取。基线 main；仓库相对于宿主工作目录为 workspace/repository。任务 detail 须写入所属模块/测试路径、功能、验收命令及上述协作流程。自行编写覆盖普通/空白/Unicode/边界情况的 unittest。完成后提交真实 Git 哈希给协作入口 submit。不要创建或修改公共 __init__.py。全套验证：python -m unittest discover -s tests -p 'test_*.py'。
`);
 git(['add','README.md']);git(['commit','-m','Acceptance task input']);evidence.initial_commit=git(['rev-parse','HEAD']);
 await start();const initial=await bridge.call('state');assert.equal(initial.network.nodes.length,15);assert.equal(initial.network.nodes.filter(node=>node.type==='agent').length,10);
 await measure('discussion',async()=>{
  await run('root',task);await bridge.call('signals_wait',{},86460000);
  const status=await local('discussion',DISC,'status',{include_history:true});
  evidence.discussion=status;assert.equal(status.status,'completed',JSON.stringify(status));assert.equal(status.participants.length,5);assert.ok(status.speeches>=5);assert.equal(status.decision.tasks.length,4);
 });
 await measure('collaboration',async()=>{
  await run('root','本次只调用编排工具 handoff，把已完成的真实讨论成果交给执行组；不要重新 start，不要轮询，不要自己编码，不要 integrate。调用后返回 execution_run。');
  await bridge.call('signals_wait',{},86460000);
  const board=await local('collab',BOARD,'list');const integration=await local('collab',GIT,'read');evidence.board=board;evidence.submissions=integration.submissions;
  assert.equal(board.overview.total,4);assert.equal(board.overview.completed,4,JSON.stringify(board));assert.equal(integration.submissions.length,4,JSON.stringify(integration));
  for(const submission of integration.submissions)assert.equal(git(['rev-parse',submission.commit+'^{commit}']),submission.commit);
 });
 let candidate;
 await measure('review',async()=>{
  await run('root','四位执行成员已提交成果。本次只调用编排工具 integrate 形成真实 Git 候选并通知全员验收；不要轮询，不要 promote，返回候选编号即可。');
  await bridge.call('signals_wait',{},86460000);
  const state=await local('collab',GIT,'read',{include_history:true});candidate=state.candidate;evidence.candidate=candidate;
  assert.equal(candidate.status,'passed',JSON.stringify(state));assert.equal(candidate.required_members.length,4);assert.equal(candidate.approved_by.length,4);
 });
 await measure('publish',async()=>{
  await run('root','候选已获全部剩余成员认可。本次调用编排工具 promote 发布并返回实际状态，不再发起新任务。');
  const status=await local('root','app.coordinator.entry','status');evidence.coordinator=status;assert.equal(status.run.status,'completed');
  assert.equal(git(['rev-parse','nexarbor/integration']),candidate.commit);
  const checkout=path.join(directory,'candidate-verification');assert.ok(checkout.startsWith(directory+path.sep));git(['worktree','add','--detach',checkout,candidate.commit]);
  for(const name of ['whitespace','words','lines','clipping']){await fs.access(path.join(checkout,name+'.py'));await fs.access(path.join(checkout,'tests/test_'+name+'.py'));}
  const tests=spawnSync(path.join(root,'.venv-runtime/Scripts/python.exe'),['-B','-X','utf8','-m','unittest','discover','-s','tests','-p','test_*.py'],{cwd:checkout,encoding:'utf8',windowsHide:true});
  evidence.candidate_tests={exit_code:tests.status,stdout:tests.stdout,stderr:tests.stderr};assert.equal(tests.status,0,tests.stderr||tests.stdout);
  assert.ok(/Ran [1-9][0-9]* tests?/.test(tests.stderr),'Candidate must contain runnable unittest cases');
  const checks=`from whitespace import normalize_whitespace
from words import count_words
from lines import nonempty_lines
from clipping import clip_text
assert normalize_whitespace('  a\\t中\\n b  ') == 'a 中 b'
assert normalize_whitespace('') == ''
assert count_words(' a\\t中\\n b ') == 3
assert count_words('   ') == 0
assert nonempty_lines(' a\\n\\n 中 \\n') == ['a', '中']
assert clip_text('中文abc', 2) == '中文'
assert clip_text('abc', 0) == ''
try: clip_text('abc', -1)
except ValueError: pass
else: raise AssertionError('negative limit must raise ValueError')
print('FUNCTIONAL_BEHAVIOR_VERIFIED')`;
  const behavior=spawnSync(path.join(root,'.venv-runtime/Scripts/python.exe'),['-B','-X','utf8','-c',checks],{cwd:checkout,encoding:'utf8',windowsHide:true});
  evidence.candidate_behavior={exit_code:behavior.status,stdout:behavior.stdout,stderr:behavior.stderr};assert.equal(behavior.status,0,behavior.stderr||behavior.stdout);

 });
 await measure('reopen_continuation',async()=>{
  await bridge.call('executor_prepare',{actor:'root'});
  await bridge.call('executor_invoke',{actor:'root',name:'memory_append',arguments:{content:'\n验收记忆：四个文本功能已经由独立成员提交并全员验收。'}});
  await bridge.call('save',{full:true});const before=await bridge.call('state');evidence.sessions_before=Object.fromEntries(Object.entries(before.agents).filter(([,value])=>value.session_id).map(([id,value])=>[id,value.session_id]));
  await stop();await start();const after=await bridge.call('state');for(const [id,session]of Object.entries(evidence.sessions_before))assert.equal(after.agents[id]?.session_id,session);
  const result=await run('root','只读取你自己的私人记忆和编排状态，用两句话说明刚才的验收成果；本轮不要修改或新建任何业务。');assert.equal(result.session_id,evidence.sessions_before.root);evidence.continued=result;
  for(const id of Object.keys(evidence.sessions_before)){const chat=await bridge.call('executor_read',{actor:id});await fs.writeFile(path.join(directory,'transcript-'+id+'.json'),JSON.stringify(chat,null,2));}
 });
 evidence.passed=true;evidence.reopened=true;evidence.requests=requests;evidence.finished=new Date().toISOString();await save();console.log(JSON.stringify({passed:true,directory,requests,reopened:true,stages:evidence.stages}));
}catch(error){evidence.passed=false;evidence.requests=requests;evidence.error=redact(error);await save();console.error(evidence.error);process.exitCode=1;}
finally{await stop();await new Promise(resolve=>gateway.close(resolve));}
