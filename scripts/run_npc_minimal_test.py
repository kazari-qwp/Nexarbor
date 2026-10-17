"""Bounded native Mock integration, preserving every session for the stock client."""
import argparse,os,subprocess,sys
from datetime import datetime
from pathlib import Path
from harness_test_environment import harness_test_environment

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'build'/('npc-action-budget-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
parser.add_argument('--open-client',action='store_true')
args=parser.parse_args();output=args.output.resolve()
if not output.is_relative_to(ROOT/'build'):parser.error('Output must be under this repository build directory')
output.mkdir(parents=True,exist_ok=False)
env=harness_test_environment(ELECTRON_RUN_AS_NODE='1',DATANET_DURABLE_TEST='1',DATANET_TEST_OUTPUT=str(output))
exe=Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
with (output/'stdout.log').open('w',encoding='utf-8') as stdout,(output/'stderr.log').open('w',encoding='utf-8') as stderr:
    result=subprocess.run([str(exe),'--experimental-vm-modules',str(ROOT/'tests/native_npc_pulse_test.cjs')],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,timeout=150,creationflags=subprocess.CREATE_NO_WINDOW)
print((output/'stdout.log').read_text(encoding='utf-8'))
if result.returncode:print((output/'stderr.log').read_text(encoding='utf-8'));sys.exit(result.returncode)
print('Test records:',output)
if args.open_client:subprocess.run([sys.executable,str(ROOT/'scripts/open_harness_test_client.py'),str(output)],check=True)
