"""从已校验的原提交和 DSH 日志断点恢复小镇到独立目录；不调用模型。"""
import argparse
import json
import os
from pathlib import Path
import shutil
from hashlib import sha256
import sqlite3
import subprocess
import sys
from tempfile import mkdtemp

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.persistence.state_journal import apply,checksum
from app.persistence.recovery import restore_bundle
from projects.npc_town.runtime import TownModules

def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--harness-exe',type=Path,required=True);args=parser.parse_args()
    source=args.source.resolve();meta=json.loads((source/'verified-tick-16-meta.json').read_text(encoding='utf-8'))
    document=json.loads((source/'verified-tick-16.json').read_text(encoding='utf-8'));commit=meta['commit_id']
    db=sqlite3.connect((source/'checkpoints.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        row=db.execute('SELECT id,document,state_hash FROM checkpoints WHERE id<=? ORDER BY id DESC LIMIT 1',(commit,)).fetchone()
        state=json.loads(row[1]);last=row[0];digest=checksum(state);assert digest==row[2]
        for seq,parent,expected,delta in db.execute('SELECT id,parent_hash,state_hash,delta FROM commits WHERE id>? AND id<=? ORDER BY id',(last,commit)):
            assert seq==last+1 and parent==digest
            state=apply(state,json.loads(delta));digest=checksum(state);assert digest==expected;last=seq
        assert last==commit and digest==meta['state_hash'] and state==document
        assert not db.execute('SELECT id FROM pending').fetchall()
    finally:db.close()
    setup=Path(mkdtemp(prefix='town-resume-',dir=ROOT/'build'));runtime=setup/'runtime';audit=setup/'contexts.json'
    env={**os.environ,'ELECTRON_RUN_AS_NODE':'1','DATANET_HARNESS_EXE':str(args.harness_exe)}
    def native(script,*arguments):
        result=subprocess.run([str(args.harness_exe),'--experimental-vm-modules',str(Path(__file__).parent/script),*map(str,arguments)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        print(result.stdout.strip(),flush=True)
    native('contexts.cjs',source,audit);verified=json.loads(audit.read_text(encoding='utf-8'));assert verified['passed']
    for actor,cursor in verified['contexts'].items():document['agents'][actor]['context_cursor']=cursor
    point={'id':'verified-completed-tick-16-commit-'+str(commit),'commit_id':commit,'kind':'full','contexts':verified['contexts'],'derived_from_journal':True}
    bundle={'version':1,'point':point,'document':document,'checksum':checksum({'point':point,'document':document})}
    (setup/'bundle.json').write_text(json.dumps(bundle,ensure_ascii=False),encoding='utf-8')
    restore_bundle(bundle,runtime,saver=TownModules().saver)
    shutil.copytree(source/'native-logs',runtime/'native-logs')
    if (source/'attachments').exists():
        shutil.copytree(source/'attachments',runtime/'attachments')
        for original in (source/'attachments').rglob('*'):
            if original.is_file():assert sha256(original.read_bytes()).digest()==sha256((runtime/'attachments'/original.relative_to(source/'attachments')).read_bytes()).digest()
    shutil.copyfile(source/'initial-state.json',runtime/'initial-state.json')
    (runtime/'temp').mkdir()
    from dotenv import dotenv_values
    for key,value in dotenv_values(ROOT/'.env').items():
        if key in ('DEEPSEEK_BASE_URL','DEEPSEEK_MODEL') and value:env[key]=value
    native('bind.mjs',runtime)
    record={'directory':str(source),'commit_id':commit,'state_hash':meta['state_hash'],'completed_tick':16,'audit':str(audit),'bundle':str(setup/'bundle.json'),'user_authorized_checkpoint_resume':True}
    (runtime/'resume-source.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Resume directory: '+str(runtime),flush=True)

if __name__=='__main__':main()
