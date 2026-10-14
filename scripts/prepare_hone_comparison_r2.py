"""Four fresh offline client arms with one shared task and external grader."""
import hashlib,json,re,shutil,socket,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'build/hone-comparison-20261014-r1'
BASE=ROOT/'build/hone-comparison-20261014-r2';BASE.mkdir(exist_ok=False)
ARMS=['datanet','free','single','subagents']
# Move only the hidden evaluator checkout, not the product or backup directories.
origin=Path((OLD/'datanet/grader-path.txt').read_text(encoding='utf-8').strip()).resolve()
expected=Path(r'C:\Users\Dried Fish\Documents\Codex\2026-10-11\e-e-harness-discussion-plugin\work\hone-evaluation').resolve()
if not origin.is_relative_to(expected):raise ValueError('Unexpected evaluator source')
private=Path('E:/DataNet-离线测试验收')/uuid.uuid4().hex
private.parent.mkdir(exist_ok=True);shutil.move(str(origin),str(private))
constraint='''离线与独立实现约束（同样适用于所有子Agent）：仅依据本工作区task提供的需求、架构、接口、公开样本，以及本次任务中你和同伴自己编写的代码实现。不允许读取、查找、导入、复制或执行任何已有hone实现，包括GitHub/镜像源码、PyPI发行版、已安装hone包、缓存、旧测试成果、评分目录或其他工作区。task中的示例和期望JSON可以正常阅读。不允许联网：不得使用网页搜索/抓取、curl/wget/Invoke-WebRequest、git clone/fetch、pip下载、requests/urllib/socket等任何方式访问网络。模型服务调用由客户端处理；这不授予Agent联网权限。只在当前工作区内修改文件，不改task资料或客户端配置。创建或委托子Agent时必须传递这些约束。'''
common='''完成 hone 项目：CSV转嵌套JSON的Python包与python -m hone入口。资料：{workspace}/task/INPUTS.md。行为和接口以资料为准，核心功能仅用标准库。交付包、CLI、自编测试、README，README包含转换、指定schema、文件输出、标准输出和测试命令。自行实现、自测、修复、Git提交。中文最终回复：成果绝对路径、提交ID、完成内容、自测命令与真实结果、已知问题。未完成时说明阻塞和保存成果，不把部分成功写成全部完成。总限时30分钟；high thinking，500k上下文，50k输出上限。'''
for arm in ARMS:
 b=BASE/arm
 if arm in ['datanet','free']:
  subprocess.run([sys.executable,str(ROOT/'scripts/prepare_hone_retest.py'),str(b)],check=True)
  m=json.loads((b/'meta.json').read_text(encoding='utf-8'))
  cfg=json.loads((OLD/'datanet/test-config.json').read_text(encoding='utf-8'))
  cfg.update(workspace=m['workspace'],storage=m['workspace']+'/.datanet')
  if arm=='free':
   cfg.pop('toolboxes',None)
   cfg['rootToolboxes']=['node_operations','network_management_skill','official_tools','official_skills','topology_inspection','self_repair','cooperation']
   cfg['allowedAgentToolboxes']=['network_access','node_operations','network_management_skill','engineering','official_tools','official_readonly','official_skills','discussion_member','topology_inspection','self_repair','cooperation']
  (b/'test-config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
  profile=Path(m['profile']);patch=(profile/'cordis.patch.yml').read_text(encoding='utf-8')
  a=patch.index('  config: ',patch.index('- id: datanet-harness'));z=patch.index('\n  disabled:',a)
  patch=patch[:a]+'  config: '+json.dumps(cfg,ensure_ascii=False)+patch[z:]
  for name in ['state.py','observe_summary.py','analyze_cache.py','error_summary.py']:
   shutil.copy2(OLD/'datanet'/name,b/name)
  public=constraint+'\n\n'+(b/'project-source.txt').read_text(encoding='utf-8')
  (b/'project-source.txt').write_text(public,encoding='utf-8')
  sys.path.insert(0,str(ROOT/'tests'));from test_components import Rpc
  backend=Rpc(Path(cfg['storage'])/'networks'/m['sessionId'].encode().hex(),binary=True)
  try:backend.result('load_root_network',package='project_root',entry_point='root');backend.result('write',actor='root',target='root/project',key='content',value=public,strength=100);backend.result('save')
  finally:backend.close()
  if arm=='datanet':prompt=(OLD/'datanet/root-task.txt').read_text(encoding='utf-8').replace(str(OLD).replace('\\','/'),str(BASE).replace('\\','/'))
  else:prompt=common.format(workspace=m['workspace'])+'\n请实际使用DataNet创建并委托Agent完成项目，由你自主选择拓扑、预设、人数、协作顺序和分工，最多15个子Agent，不使用官方subagent。项目资料已放在查询文本root/project。成果最终整合到当前工作区project目录并提交Git（可从小组成果复制整合），报告该目录的提交ID。'
 else:
  b.mkdir();profile=b/'home/profiles/desktop';profile.mkdir(parents=True);work=b/'workspace';work.mkdir();(work/'project').mkdir()
  for name in ['client_api.py','monitor.cjs','judge.py','cli_judge.py','materials.json']:
   shutil.copy2(OLD/arm/name,b/name)
  shutil.copytree(OLD/arm/'workspace/task',work/'task',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  shutil.copy2(OLD/arm/'home/.credentials.yaml',b/'home/.credentials.yaml')
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  m=dict(base=str(b),home=str(b/'home'),workspace=str(work),profile=str(profile),authority=f'127.0.0.1:{port}',provider='deepseek-official',model='deepseek-flash',reasoningEffort='high',contextWindow=500000,maxTokens=50000,version='stock',sessionId='session-'+str(uuid.uuid4()),totalMinutes=30)
  for name in ['package.json','cordis.yml','pnpm-workspace.yaml']:shutil.copy2(OLD/arm/'home/profiles/desktop'/name,profile/name)
  patch=(OLD/arm/'home/profiles/desktop/cordis.patch.yml').read_text(encoding='utf-8')
  patch=re.sub(r'port: \d+',f'port: {port}',patch)
  prompt=common.format(workspace=str(work))+'\n在'+str(work/'project')+'目录实现并提交。'+('全程独立完成，不允许子Agent。' if arm=='single' else '实际使用官方subagent完成，自主分工；最大递归深度4，最多并发15个，累计最多创建15个子Agent。所有成员协作同一project目录，你负责整合验收。')
 patch+='\n- id: web-search-deepseek\n  disabled: true\n- id: web-fetch-http\n  disabled: true\n'
 (profile/'cordis.patch.yml').write_text(patch,encoding='utf-8')
 m.update(arm=arm,title={'datanet':'hone 固定DataNet','free':'hone 自主组网DataNet','single':'hone 原版单Agent','subagents':'hone 原版子Agent'}[arm]+' · 离线复测',sourceCommit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
 (b/'meta.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
 (b/'root-task.txt').write_text(constraint+'\n\n'+prompt,encoding='utf-8')
 (b/'grader-path.txt').write_text(str(private),encoding='utf-8')
 runner=(OLD/arm if arm!='free' else OLD/'datanet')/'run_client.py'
 text=runner.read_text(encoding='utf-8')
 # On deadline a separate process watchdog also terminates this isolated client's tree.
 (b/'run_client.py').write_text(text,encoding='utf-8')
 work=Path(m['workspace']);(b/'input-baseline.json').write_text(json.dumps({str(f.relative_to(work/'task')).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in (work/'task').rglob('*') if f.is_file()},indent=2),encoding='utf-8')
 offline=b/'offline-python';offline.mkdir()
 (offline/'sitecustomize.py').write_text('''import socket\ndef blocked(*args, **kwargs):\n raise PermissionError("Offline benchmark: network access is forbidden")\nsocket.socket.connect=blocked\nsocket.socket.connect_ex=blocked\nsocket.create_connection=blocked\nsocket.getaddrinfo=blocked\n''',encoding='utf-8')
# Reuse logging/grading logic, parameterized to the four new arms.
for filename in ['observe_hone_comparison.py','finalize_hone_comparison.py']:
 text=(ROOT/'scripts'/filename).read_text(encoding='utf-8').replace('hone-comparison-20261014-r1','hone-comparison-20261014-r2').replace("['datanet','single','subagents']","['datanet','free','single','subagents']")
 (ROOT/'scripts'/filename.replace('.py','_r2.py')).write_text(text,encoding='utf-8')
print('Prepared four offline arms',BASE)
