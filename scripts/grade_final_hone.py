"""以原12项库测试和6项CLI检查独立判分冻结提交；不调用模型。"""
import argparse,importlib.util,io,json,os,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RESOURCE=ROOT/'tests/evaluation/hone'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def score(repository,revision,output):
 repository=Path(repository).resolve();output=Path(output).resolve()
 if not repository.is_relative_to(ROOT/'build') or not output.is_relative_to(ROOT/'build'):raise ValueError('仅验收隔离build中的真实成果')
 output.mkdir(parents=True,exist_ok=False)
 def git(*arguments):
  r=subprocess.run(['git','-C',str(repository),*arguments],capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if r.returncode:raise RuntimeError(r.stderr.decode('utf8',errors='replace'))
  return r.stdout
 commit=git('rev-parse','--verify',revision+'^{commit}').decode('ascii').strip();candidate=output/'candidate';candidate.mkdir()
 archive=git('archive','--format=tar',commit)
 if len(archive)>50*1024*1024:raise ValueError('候选归档超过原验收上限')
 with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
  for item in tar.getmembers():
   target=(candidate/item.name).resolve()
   if not target.is_relative_to(candidate):raise ValueError('归档文件越界')
   if item.isdir():target.mkdir(parents=True,exist_ok=True)
   elif item.isfile():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(tar.extractfile(item).read())
   else:raise ValueError('归档只接受普通文件和目录')
 upstream=load('historical_hone_upstream',RESOURCE/'judge.py');upstream.BASE=output;upstream.REFERENCE=RESOURCE/'reference'
 cli=load('historical_hone_cli',RESOURCE/'cli_judge.py');cli.BASE=output
 (output/'grader-path.txt').write_text(str(RESOURCE),encoding='utf8')
 u=upstream.score(candidate,'upstream');c=cli.score(candidate)
 passed=u['exit_code']==0 and sum(item['total'] for item in u['suites'])==12 and c['passed']==c['total']==6
 report={'passed':passed,'model_calls':0,'repository':str(repository),'frozen_commit':commit,'candidate':str(candidate),'upstream':u,'cli':c,'protocol_approval':'产物判分独立于组网、讨论、Git工作区及全体验收协议审计。'}
 (output/'independent-hone-score.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'passed':passed,'frozen_commit':commit,'upstream':[dict(suite=x['suite'],total=x['total'],passed=x['passed']) for x in u['suites']],'cli':{'passed':c['passed'],'total':c['total']},'model_calls':0},ensure_ascii=False))
 return 0 if passed else 1
def main():
 p=argparse.ArgumentParser();p.add_argument('repository');p.add_argument('revision');p.add_argument('output');a=p.parse_args();return score(a.repository,a.revision,a.output)
if __name__=='__main__':raise SystemExit(main())
