"""在E盘临时快照中复跑已收录组件测试，避免测试文件污染组件源码。"""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
folders=list((ROOT/'extensions/composable/capabilities').iterdir())+[ROOT/'extensions/foundation/capabilities'/x for x in ['place_info','move_here','tool_collector']]
dependencies={json.loads((f/'module.json').read_text(encoding='utf-8'))['id']:str(f) for f in folders if (f/'module.json').exists()}
profile=json.loads((ROOT/'extensions/development/extension.json').read_text(encoding='utf-8'))
env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/p) for p in ['python','extensions/development/capabilities/component_studio/python','extensions/foundation/capabilities/module_sdk/python']),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_TEST_MODULES=json.dumps(dependencies),DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(profile['select']),DATANET_COMPONENT_PROFILE='{}')
results=[]
with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='composable-check-') as temporary:
    for folder in folders:
        if not (folder/'tests').is_dir():continue
        destination=Path(temporary)/folder.name;shutil.copytree(folder,destination)
        result=subprocess.run([sys.executable,'-m','datanet.studio.worker',str(destination),'blank'],env={**env,'TEMP':temporary,'TMP':temporary},capture_output=True,text=True,encoding='utf-8',cwd=ROOT,timeout=60)
        output=result.stdout+result.stderr;name=json.loads((folder/'module.json').read_text(encoding='utf-8'))['id']
        print(name,'PASS' if result.returncode==0 else 'FAIL',output[-400:] if result.returncode==0 else output[-6000:],flush=True);results.append(dict(module=name,passed=result.returncode==0,log=output))
Path(ROOT/'build/composable-verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
