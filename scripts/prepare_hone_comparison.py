"""Three isolated real-client arms; unchanged public fixtures and external graders."""
import json,shutil,socket,subprocess,sys,uuid,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'build/hone-guide-20261014-r1'
BASE=ROOT/'build/hone-comparison-20261014-r1';BASE.mkdir(exist_ok=False)
OUR=BASE/'datanet'
subprocess.run([sys.executable,str(ROOT/'scripts/prepare_hone_retest.py'),str(OUR)],check=True)
common="""请在当前客户端完成 hone 项目实现，付费 API 已获授权，最终中文回复交付结果。
资料位于 {workspace}/task/INPUTS.md，其中列出需求、架构、接口和公开样本。请完成 CSV 转嵌套 JSON 的 Python 包及 python -m hone 入口，接口与行为以资料为准，核心功能只使用标准库。
交付可导入 hone 包、CLI、自编测试及README。README包含转换、指定schema、文件输出、标准输出和运行测试的命令。自行实现、自测、修复并完成Git提交，最后给出成果绝对路径、最终提交ID、完成内容、自测命令与真实结果、已知问题。若未完成，说明阻塞和保存成果，不把部分成功写成全部完成。
严格在当前工作区工作，不修改task中的公开输入，不读取其他测试目录、评分目录、参考实现或密钥，不修改客户端配置。总时间上限30分钟，从收到本任务开始计时。模型参数为high thinking、500k上下文、50k单次最大输出。
"""
for arm in ['datanet','single','subagents']:
 b=BASE/arm
 if arm!='datanet':
  profile=b/'home/profiles/desktop';profile.mkdir(parents=True);work=b/'workspace';work.mkdir();(work/'project').mkdir()
  for name in ['client_api.py','monitor.cjs','judge.py','cli_judge.py','grader-path.txt','materials.json']:shutil.copy2(OLD/name,b/name)
  shutil.copytree(OLD/'workspace/task',work/'task',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  shutil.copy2(OLD/'home/.credentials.yaml',b/'home/.credentials.yaml')
  sid='session-'+str(uuid.uuid4())
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  meta=dict(base=str(b),home=str(b/'home'),workspace=str(work),profile=str(profile),authority=f'127.0.0.1:{port}',provider='deepseek-official',model='deepseek-flash',reasoningEffort='high',contextWindow=500000,maxTokens=50000,version='stock',sessionId=sid,title='hone 原版'+('单Agent' if arm=='single' else '子Agent深度4数量15')+'对比',totalMinutes=30,arm=arm)
  (b/'meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
  (profile/'package.json').write_text(json.dumps({'name':'dsh-profile-desktop','private':True,'dsh':{'profile':{'bundles':['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}},indent=2),encoding='utf-8')
  (profile/'cordis.yml').write_text('[]\n',encoding='utf-8');(profile/'pnpm-workspace.yaml').write_text('packages:\n  - .\nnodeLinker: hoisted\nautoInstallPeers: false\n',encoding='utf-8')
  depth=0 if arm=='single' else 4
  patch=f"""- id: webserver
  config: {{host: 127.0.0.1, port: {port}}}
- id: ui-settings-general
  config: {{welcomeNoticeVersion: 2026-09-28.1}}
- id: ui-settings-account
  config: {{version: 1, step: done, usage: detailed, developerTools: true, completion: api-key}}
- id: ui-chat
  config: {{transcriptView: standard, performanceUsage: detailed}}
- id: subagent
  config: {{maxDepth: {depth}, maxActiveSubagents: 15}}
- id: tool-subagent
  disabled: {'true' if arm=='single' else 'false'}
  config:
    maxDepth: {depth}
    agentOptions: {{provider: deepseek-official, model: deepseek-flash, reasoningEffort: high, maxTokens: 50000}}
- id: tool-subagent-fork
  disabled: true
"""
  if arm=='single':patch+='- id: tool-subagent-control\n  disabled: true\n- id: tool-subagent-list-agents\n  disabled: true\n'
  # Provider configuration uses only shipped native plugins, no DataNet bundle.
  provider=(ROOT/'cordis.patch.yml').read_text(encoding='utf-8').split('- id: agent-loop',1)[0]
  (profile/'cordis.patch.yml').write_text(patch+provider,encoding='utf-8')
  prompt=common.format(workspace=str(work))+'\n在 '+str(work/'project')+' 目录内实现并提交项目。\n'
  prompt+=('全程由你独立完成，不允许调用子Agent或智能体团队。' if arm=='single' else '请实际使用官方subagent功能完成任务，自主安排分工。最多创建15个子Agent（含嵌套子Agent累计），最大递归深度4，最多并发15个。所有成员用同一个项目目录协作，避免相互覆盖；你负责整合、验收和最终交付。')
  (b/'root-task.txt').write_text(prompt,encoding='utf-8')
 else:
  meta=json.loads((b/'meta.json').read_text());meta.update(arm=arm,title='hone DataNet讨论精简对比 · 0.3.15',sourceCommit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),baseline=str(OLD));(b/'meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
  cfg=json.loads((OLD/'test-config.json').read_text());cfg.update(workspace=meta['workspace'],storage=meta['workspace']+'/.datanet');(b/'test-config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
  patch=(Path(meta['profile'])/'cordis.patch.yml').read_text();a=patch.index('  config: ',patch.index('- id: datanet-harness'));z=patch.index('\n  disabled:',a);patch=patch[:a]+'  config: '+json.dumps(cfg,ensure_ascii=False)+patch[z:];(Path(meta['profile'])/'cordis.patch.yml').write_text(patch,encoding='utf-8')
  for name in ['state.py','finalize.py','observe_summary.py','analyze_cache.py','error_summary.py']:shutil.copy2(OLD/name,b/name)
 runner=(OLD/'run_client.py').read_text(encoding='utf-8');(b/'run_client.py').write_text(runner,encoding='utf-8')
 work=Path(meta['workspace']);(b/'input-baseline.json').write_text(json.dumps({str(f.relative_to(work/'task')).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in (work/'task').rglob('*') if f.is_file()},ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared comparison:',BASE)
