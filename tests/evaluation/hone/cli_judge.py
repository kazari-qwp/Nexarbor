"""Supplement upstream library scoring with documented CLI contract checks."""
import csv,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
BASE=Path(__file__).resolve().parent

def score(candidate):
    stage=BASE/'evaluation'/('cli-'+uuid.uuid4().hex[:8]);stage.mkdir(parents=True)
    shutil.copytree(Path(candidate)/'hone',stage/'hone')
    data=Path((BASE/'grader-path.txt').read_text(encoding='utf-8'))/'reference/data_file/small_cats_dataset'
    inp=data/'dataset.csv';expected=json.loads((data/'nested_dataset.json').read_text(encoding='utf-8'))
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':''}
    results=[]
    def run(name,args,expected_json=None,stdin=None,outfile=None):
        try:
            proc=subprocess.run([sys.executable,'-m','hone',*args],cwd=stage,env=env,input=stdin,text=True,encoding='utf-8',capture_output=True,timeout=60)
            actual=(Path(outfile).read_text(encoding='utf-8') if outfile else proc.stdout)
            valid=proc.returncode==0
            if expected_json is not None:valid=valid and json.loads(actual)==expected_json
            results.append(dict(name=name,passed=valid,exit_code=proc.returncode,stderr=proc.stderr,stdout=proc.stdout))
        except Exception as error:results.append(dict(name=name,passed=False,error=str(error)))
    run('help',['--help'])
    run('file-to-stdout',[str(inp),'-'],expected)
    dest=stage/'result.json';run('file-output',[str(inp),str(dest)],expected,outfile=dest)
    run('stdin-to-stdout',['-','-'],expected,stdin=inp.read_text(encoding='utf-8'))
    rows=list(csv.DictReader(inp.open(encoding='utf-8',newline='')))
    run('explicit-json-schema',['--schema',json.dumps({'cat':'name'}),str(inp),'-'],[{'cat':row['name']} for row in rows])
    run('explicit-delimiters',['--delimiters','["|"]',str(inp),'-'],rows)
    report=dict(candidate=str(candidate),passed=sum(r['passed'] for r in results),total=len(results),checks=results)
    (BASE/'cli-score.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    report=score(sys.argv[1]);print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False));sys.exit(int(report['passed']!=report['total']))
