"""托管模式首次索引/检索才创建计算进程，科学库在该进程主线程导入。"""
import importlib
import importlib.util
import json
import os
from pathlib import Path
from queue import Queue,Empty
import subprocess
import sys
from threading import Lock,Thread

_managed=False
_directory=None
_worker=None
_mutex=Lock()
_state='idle'
_worker_info={}

class RemoteEmbedding:
    """仅表示同一嵌入配置可复用；真实模型始终留在计算进程。"""
    pass

def remote_enabled(config,model):
    return _managed and config is not None and (model is None or isinstance(model,RemoteEmbedding))

def require_vector_runtime():
    # 直接使用 Python API 时保留原语义；托管节点从 remote_call 进入独立进程。
    importlib.import_module('llama_index.embeddings.huggingface' if importlib.util.find_spec('sentence_transformers') else 'llama_index.core')

def status():
    return dict(state=_state,torch_imported='torch' in sys.modules,worker=dict(_worker_info))

def close():
    global _worker,_state
    record=_worker;_worker=None
    if not record:return
    process=record['process']
    try:
        process.stdin.close()
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    finally:
        record['log'].close()
        if _state!='error':_state='idle'

def remote_call(node,method,args=(),kwargs=None):
    global _worker,_state,_worker_info
    with _mutex:
        if _worker is None or _worker['process'].poll() is not None:
            close();_state='loading';_worker_info={}
            log=open(_directory/'vector-worker.log','a',encoding='utf-8')
            environment={**os.environ,'DATANET_DEFER_VECTORS':'0','DATANET_VECTOR_WORKER':'1'}
            try:
                process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except BaseException:
                log.close();_state='error';raise
            replies=Queue();_worker=dict(process=process,replies=replies,log=log)
            def receive():
                try:
                    for line in process.stdout:replies.put(json.loads(line))
                except BaseException as error:replies.put(dict(error=str(error)))
                finally:replies.put(dict(error='向量计算进程已退出，请查看 vector-worker.log'))
            Thread(target=receive,name='datanet-vector-replies',daemon=True).start()
            try:
                hello=replies.get(timeout=180)
                if not hello.get('ready'):raise RuntimeError(hello.get('error','向量计算初始化失败'))
                _worker_info=hello;_state='ready'
            except BaseException:
                _state='error';close();raise
        record=_worker
        request=dict(method=method,node=dict(id=node.node_id,name=node.name,storage=str(node.storage_path),embedding=node.embedding_config),args=args,kwargs=kwargs or {})
        try:
            record['process'].stdin.write(json.dumps(request,ensure_ascii=False)+'\n');record['process'].stdin.flush()
            result=record['replies'].get(timeout=180)
        except (Empty,BrokenPipeError,OSError,ValueError) as error:
            _state='error';close();raise RuntimeError('向量计算超时或连接已关闭') from error
        if 'error' in result:
            errors={'ValueError':ValueError,'TypeError':TypeError,'FileNotFoundError':FileNotFoundError}
            raise errors.get(result.get('type'),RuntimeError)(result['error'])
        return result['value']

def initialize(backend):
    global _managed,_directory
    _managed=os.environ.get('DATANET_DEFER_VECTORS')=='1'
    _directory=backend.directory
    if not _managed and os.name=='nt' and importlib.util.find_spec('sentence_transformers'):
        require_vector_runtime()

def register(registry):
    registry.initializers.append(initialize)
    registry.finalizers.append(lambda backend:close())
