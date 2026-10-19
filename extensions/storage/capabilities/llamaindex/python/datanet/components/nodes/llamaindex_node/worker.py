"""私有管道计算器：不接受网络请求或任意函数名，索引仍使用原有文件锁和版本提交。"""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(os.environ['DATANET_PRODUCT_ROOT'])/'adapters/harness/backend'))
import config
import json
from collections import OrderedDict
from dataclasses import asdict,is_dataclass
from threading import current_thread,main_thread
output=sys.stdout
sys.stdout=sys.stderr
from datanet.components.nodes.llamaindex_node.startup import require_vector_runtime
require_vector_runtime()
from datanet.components.nodes.llamaindex_node.llamaindex_node import LlamaIndexNode

def reply(value):
    output.write(json.dumps(value,ensure_ascii=False)+'\n');output.flush()

reply(dict(ready=True,pid=os.getpid(),loaded_on_main_thread=current_thread() is main_thread(),torch_imported='torch' in sys.modules))
models=OrderedDict()
for line in sys.stdin:
    try:
        request=json.loads(line);method=request['method'];spec=request['node']
        if method not in ('ingest','load','update_documents','delete_documents','search'):raise ValueError('未知索引计算操作')
        key=json.dumps(spec['embedding'],sort_keys=True)
        node=LlamaIndexNode(spec['id'],spec['name'],spec['storage'],embedding_config=spec['embedding'])
        if key in models:node._embed_model=models.pop(key)
        value=getattr(node,method)(*request['args'],**request['kwargs'])
        if node._embed_model is not None:
            models[key]=node._embed_model
            while len(models)>4:models.popitem(last=False)
        reply(dict(value=asdict(value) if is_dataclass(value) else value))
    except Exception as error:reply(dict(error=str(error) or type(error).__name__,type=type(error).__name__))
