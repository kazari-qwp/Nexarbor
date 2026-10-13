"""Run unchanged upstream tests against a frozen candidate in a separate directory."""
import json, os, shutil, subprocess, sys, uuid
from pathlib import Path

BASE = Path(sys.argv[3]).resolve() if len(sys.argv)>3 else Path(__file__).resolve().parent
REFERENCE = Path(sys.argv[4]).resolve() if len(sys.argv)>4 else BASE / 'evaluation/reference'
BASE.mkdir(parents=True, exist_ok=True)
CODE = '''
import unittest,io,json,sys
results=[]
for name in ['unit_tests','acceptance_tests']:
    stream=io.StringIO()
    suite=unittest.TestLoader().discover(name)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    results.append(dict(suite=name,total=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),output=stream.getvalue()))
print(json.dumps(results,ensure_ascii=False))
sys.exit(int(any(r['failures'] or r['errors'] or r['total']==0 for r in results)))
'''


def score(candidate, label):
    candidate = Path(candidate).resolve()
    directory = BASE / 'evaluation/scores' / (label + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    for name in ['unit_tests','acceptance_tests','data_file']:
        shutil.copytree(REFERENCE/name, directory/name)
    if (candidate/'hone').is_dir():
        shutil.copytree(candidate/'hone', directory/'hone', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    # Upstream unit_tests imports its fixture parser from the product namespace.
    # Supply that unchanged test helper only in the scoring copy, never the candidate.
    helper = directory/'hone/utils/test_utils.py'
    if not helper.exists():
        helper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REFERENCE/'hone/utils/test_utils.py', helper)
    env = {**os.environ, 'PYTHONUTF8':'1', 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':''}
    process = subprocess.run([sys.executable,'-c',CODE],cwd=directory,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
    report = dict(candidate=str(candidate),directory=str(directory),exit_code=process.returncode,stderr=process.stderr)
    report['suites'] = json.loads(process.stdout) if process.stdout.strip() else []
    (BASE/(label+'-score.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    report=score(sys.argv[1],sys.argv[2])
    print(json.dumps({k:v for k,v in report.items() if k!='suites'},ensure_ascii=False))
    print(json.dumps([{k:v for k,v in r.items() if k!='output'} for r in report['suites']],ensure_ascii=False))
    sys.exit(report['exit_code'])
