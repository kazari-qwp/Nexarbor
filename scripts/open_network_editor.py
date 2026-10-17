"""Open a running local workbench; no frontend compiler is needed."""
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--storage',type=Path,default=ROOT/'editor-workspace/.datanet')
parser.add_argument('--connection',type=Path)
args=parser.parse_args()
files=[args.connection] if args.connection else sorted(args.storage.rglob('editor-connection.json'),key=lambda p:p.stat().st_mtime,reverse=True)
for file in files:
    try:
        connection=json.loads(file.read_text('utf-8'));url=urllib.parse.urlparse(connection['url'])
        if url.scheme!='http' or url.hostname!='127.0.0.1':raise ValueError('Only loopback workbenches are supported')
        token=urllib.parse.parse_qs(url.fragment)['token'][0]
        request=urllib.request.Request(urllib.parse.urlunparse(url._replace(path='/api',fragment='')),data=b'{"operation":"state","params":{}}',headers={'Content-Type':'application/json','X-Nexarbor-Token':token},method='POST')
        result=json.load(urllib.request.urlopen(request,timeout=3))
        if 'value' not in result:continue
        webbrowser.open(connection['url']);print('已打开本地网络工作台。');break
    except (OSError,ValueError,KeyError):continue
else:raise SystemExit('没有找到运行中的工作台。先在 Harness 的编辑器工作区打开一份根会话，或用 --connection 指定启动记录。')
