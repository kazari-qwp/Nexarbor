"""Dedicated v8 development host; old application components are not loaded."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import config
from transport import Transport
from datanet.core.backend import Backend
from remote import HarnessRemote
from executor import NativeExecutor
import asyncio
import os,json

class StudioTransport(Transport):
    def __init__(self,backend,output=None):
        super().__init__(backend,output)
        # Reverse Agent callbacks must permit the explicit finite execution deadline.
        self.host_timeout=lambda method,params: max(86460,params.get('timeout_seconds',86400)+60)

    def error_message(self,error):
        from datanet.studio.diagnostics import error_message
        return error_message(error)

    def dispatch(self,method,p):
        if method=='skill_parse':
            from skill_resources import parse_skill
            return parse_skill(p)
        # Long Agent work yields to callback RPCs; each tool still commits atomically.
        if method=='studio_vector_close':
            from datanet.components.nodes.llamaindex_node.startup import close
            close();return True
        if method=='studio_vector_status':
            from datanet.components.nodes.llamaindex_node.startup import status
            return status()
        if method=='studio_official_needed':
            return any(o['ref'].startswith('harness:') for n in self.backend.network.nodes.values() for o in n.offered_tools)
        if method=='studio_apply':
            # 业务处理返回时外围事务尚未提交；在同一事务锁内返回最终编号。
            with self.backend._transaction_lock:
                result=super().dispatch(method,p)
                result['commit']=self.backend.store.head
                return result
        if method=='studio_frontend_preview':
            # 只读模块可能等待异步读取，不能持跨线程的全局事务锁。
            return self.backend.studio.frontend_preview(p)
        if method=='data_preview':
            return self.backend.components.routes['data_preview'](self.backend,p)
        if method=='official_register':
            async def execute(actor,name,arguments):
                return await asyncio.to_thread(self.host,'official-tool-invoke',dict(actor=actor,name=name,arguments=arguments))
            from jsonschema import Draft202012Validator
            contracts=p.get('contracts',{})
            for name,contract in contracts.items():
                if name not in {tool['name'] for tool in p['tools']} or contract.get('format')!='harness-tool-result/v1':raise ValueError('官方工具返回契约无效')
                Draft202012Validator.check_schema(contract['value_schema'])
            self.backend.external_tools.register('harness',p['tools'],execute)
            self.backend.port_contracts={**getattr(self.backend,'port_contracts',{}),**{'harness:'+name:contract for name,contract in contracts.items()}}
            return self.backend.external_tools.catalog()
        if method in ('executor_invoke','executor_prepare','executor_visit'):
            with self.backend.node_locks.import_owner(p.get('node_access_ticket'),p.get('actor')):
                result=getattr(self.executor,method.removeprefix('executor_'))(p)
            self.backend.dispatch('save',{})
            return result
        if method in ('executor_ack','executor_bind','executor_prune'):
            with self.backend.node_locks.import_owner(p.get('node_access_ticket'),p.get('actor')):
                result=getattr(self.executor,method.removeprefix('executor_'))(p)
            self.backend.dispatch('save',{})
            return result
        if method=='module_access':
            result=self.backend.runtime.run(self.backend.modules.call(p['node'],p['module'],p['operation'],p.get('arguments',{})))
            self.backend.dispatch('save',{})
            return result
        if method=='data_clear':
            return self.backend.runtime.run(self.backend.components.routes['data_clear'](self.backend,p))
        if method=='studio_pulse':return self.backend.studio.pulse(p)
        if method=='executor_run':return asyncio.run(self.backend.execute_agent(p['actor'],p.get('text','')))
        if method=='executor_read':
            with self.backend.node_locks.access_sync([p['actor']]):
                node=self.backend.network.nodes[p['actor']]
                with self.backend.node_locks.export_owner(node.node_id) as ticket:
                    return self.host('agent-read',dict(actor=node.node_id,name=node.name,session_id=self.backend.agents.get(node.node_id,{}).get('session_id'),context_cursor=node.context_cursor,node_access_ticket=ticket,model=(node.execution_binding or {}).get('model'),model_signature=self.backend.agents.get(node.node_id,{}).get('model_signature')))
        return super().dispatch(method,p)

def main():
    initial=os.environ.get('DATANET_INITIAL_NETWORK')
    document=json.loads(Path(initial).read_text(encoding='utf-8')) if initial else None
    if document:
        for node in document['network']['nodes']:
            file=node.get('parameters',{}).get('file_path')
            if node['type']!='text_file' and file is not None and (Path(file).is_absolute() or '..' in Path(file).parts):raise ValueError('应用初始网络的文本与记忆路径必须在运行目录内')
    backend=Backend(sys.argv[1],initial_document=document);remote=HarnessRemote(backend.studio)
    backend.studio.workspace_busy=lambda id:any(j['workspace']==id and j['status']=='running' for j in remote.jobs.values())
    for method in ['connect','start','read','cancel','status']:
        backend.components.rpc('studio_agent_'+method,lambda b,p,method=method:getattr(remote,method)(p))
    backend.components.finalizers.append(lambda b:remote.close())
    transport=StudioTransport(backend);transport.executor=NativeExecutor(backend,transport);backend.studio_executor=transport.executor
    transport.run(sys.stdin)

if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8')
    try:main()
    except Exception:
        # 初始化中途失败也可能已经创建运行线程；必须退出并释放本进程的工作区锁。
        import traceback
        traceback.print_exc();sys.stderr.flush();os._exit(1)
