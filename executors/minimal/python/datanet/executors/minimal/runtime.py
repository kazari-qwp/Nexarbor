"""Optional reference executor; the model client and tool bindings are injected."""
from pathlib import Path
from threading import Lock
from hashlib import sha256
from types import SimpleNamespace
import json,os,tempfile
from datanet.core.execution import ExecutionResult
from datanet.core.agent_node import AgentNode
from .agent import Agent

class MinimalExecutor:
    def __init__(self,client,model='model',directory=None,max_tokens=2048):
        self.client,self.model,self.max_tokens=client,model,max_tokens
        self.directory=Path(directory or tempfile.mkdtemp(prefix='datanet-executor-'))
        self.agents={};self.states={};self.locks={};self.pending={};self.lock=Lock()
    def run(self,request,tools):
        if request.max_steps<1 or request.timeout_seconds<=0:raise ValueError('Execution budgets must be positive')
        with self.lock:lock=self.locks.setdefault(request.session_id,Lock())
        if not lock.acquire(False):return ExecutionResult('busy',error='Session already running')
        actor=None
        try:
            folder=self.directory/sha256(request.session_id.encode()).hexdigest();folder.mkdir(parents=True,exist_ok=True)
            metadata=folder/'session.json'
            identity={'node_id':request.node_id,'session_id':request.session_id}
            if metadata.exists() and json.loads(metadata.read_text(encoding='utf-8'))!=identity:raise ValueError('Session belongs to another node')
            metadata.write_text(json.dumps(identity),encoding='utf-8')
            sources=sorted(request.input_state.items())
            system='\n\n'.join([request.prompt,*[s['system_prompt'] for _,s in sources if s['system_prompt']]]).strip()
            prompt=folder/'prompt.md';prompt.write_text(system or 'Complete the requested task using the available tools.',encoding='utf-8')
            actor=Agent(self.client,self.model,prompt,request.tools,request.max_steps,self.max_tokens)
            actor.timeout_seconds=request.timeout_seconds
            history=folder/'messages.json'
            if history.exists():
                restored=json.loads(history.read_text(encoding='utf-8'))
                if not isinstance(restored,list):raise ValueError('Invalid saved session')
                actor.messages=restored
                actor.messages[0]={'role':'system','content':actor.system_prompt}
            from datanet.core.agent_inputs import digest
            for source,value in sources:
                for doc in value['context']:
                    body='[Nexarbor document '+digest([source,doc['id'],doc['text']])+']\n'+doc['text']
                    if not any(m.get('role')=='user' and m.get('content')==body for m in actor.messages):actor.messages.append(dict(role='user',content=body))
                for event in value['inputs']:
                    if event['status']!='pending':continue
                    body='[Nexarbor input '+digest([source,event['id']])+']\n'+event['text']
                    if not any(m.get('role')=='user' and m.get('content')==body for m in actor.messages):actor.messages.append(dict(role='user',content=body))
            actor.request_tail=[t for _,value in sources for t in value['tail']]
            node=AgentNode(request.node_id,request.node_id,file_path=folder/'memory.md');node.agent=actor
            for spec in request.tools:
                definition=spec.get('function',spec);name=definition['name']
                if name not in tools:raise ValueError('Tool has no authorized binding: '+name)
                node.register_agent_tool(name,tools[name],description=definition.get('description',''),parameters=definition.get('parameters',{'type':'object','properties':{}}))
            with self.lock:
                for message in self.pending.pop(request.session_id,[]):actor.send(message)
                self.agents[request.session_id]=actor;self.states[request.session_id]='running'
            try:
                text=actor.run(request.message,node=node)
                self.states[request.session_id]='completed';return ExecutionResult('completed',text,actor.steps)
            except InterruptedError as error:self.states[request.session_id]='canceled';return ExecutionResult('canceled',steps=actor.steps,error=str(error))
            except TimeoutError as error:self.states[request.session_id]='timeout';return ExecutionResult('timeout',steps=actor.steps,error=str(error))
            except Exception as error:self.states[request.session_id]='failed';return ExecutionResult('failed',steps=actor.steps,error=str(error))
            finally:
                temporary=history.with_suffix('.tmp');temporary.write_text(json.dumps(actor.messages,ensure_ascii=False),encoding='utf-8');os.replace(temporary,history)
        finally:lock.release()
    def status(self,session_id):return self.states.get(session_id,'idle')
    def cancel(self,session_id):
        actor=self.agents.get(session_id)
        if actor is None or self.status(session_id)!='running':return False
        actor.cancel_event.set();return True
    def send(self,session_id,message):
        if not isinstance(message,str):raise TypeError('Message must be text')
        with self.lock:
            actor=self.agents.get(session_id)
            if actor is not None and self.status(session_id)=='running':actor.send(message)
            else:self.pending.setdefault(session_id,[]).append(message)

class _Message:
    def __init__(self,data):
        self.data=data;self.content=data.get('content');self.tool_calls=[SimpleNamespace(id=t['id'],function=SimpleNamespace(**t['function'])) for t in (data.get('tool_calls') or [])]
    def model_dump(self,**unused):return dict(self.data)

class ModelClient:
    def __init__(self,complete):
        self.complete=complete;self.timeout=60;self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def set_timeout(self,seconds):self.timeout=seconds
    def create(self,**request):
        response=self.complete(request,self.timeout)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=c.get('finish_reason','stop'),message=_Message(c['message'])) for c in response.get('choices',[])])

class HTTPModelClient(ModelClient):
    def __init__(self,base_url,api_key):
        from urllib.parse import urlsplit
        if urlsplit(base_url).scheme not in ('http','https'):raise ValueError('Invalid model endpoint')
        def complete(payload,timeout):
            payload=dict(payload)
            payload.update(payload.pop('extra_body',{}) or {})
            import urllib.request
            request=urllib.request.Request(base_url.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+api_key})
            with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
        super().__init__(complete)

class MockExecutor(MinimalExecutor):
    def __init__(self,responses=None,**options):
        self.responses=iter(responses or [{'choices':[{'message':{'role':'assistant','content':'ok'}}]}])
        super().__init__(ModelClient(lambda request,timeout:next(self.responses)),**options)
