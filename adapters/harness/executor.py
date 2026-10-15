"""Portable executor facade over the Harness host-operation port."""
from datanet.core.execution import ExecutionResult

class HarnessExecutor:
    def __init__(self,port):self.port=port;self.sessions={}
    def run(self,request,tools):
        if tools:raise ValueError('Harness tools must be mounted by the native tool registry')
        self.sessions[request.session_id]=request.node_id
        try:
            value=self.port('run',{'actor':request.node_id,'text':request.message,'timeout_ms':int(request.timeout_seconds*1000)})
            return ExecutionResult('completed',value if isinstance(value,str) else str(value))
        except Exception as error:return ExecutionResult('failed',error=str(error))
    def cancel(self,session_id):return self.port('cancel-agent',{'actor':self.sessions[session_id]})
    def status(self,session_id):return self.port('inspect',{'actor':self.sessions[session_id]})['status']
    def send(self,session_id,message):return self.port('steer',{'actor':self.sessions[session_id],'text':message})
