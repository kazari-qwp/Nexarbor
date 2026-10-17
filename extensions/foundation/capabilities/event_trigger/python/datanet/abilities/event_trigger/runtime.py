"""Match immutable event envelopes and await the selected execution graphs."""
import asyncio
from dataclasses import asdict
from datanet.core.application import Component
from datanet.core.json_values import freeze,thaw,names
from datanet.abilities.langgraph_backend.backend import validate,resolve


def validate_rules(rules,graphs,operations):
    if not isinstance(rules,list) or len(rules)>64:raise ValueError('Expected at most 64 event rules')
    graphs={key:validate(value,operations) for key,value in graphs.items()}
    seen=set()
    for rule in rules:
        if set(rule)!={'id','event','channels','where','graph'}:raise ValueError('Invalid event rule fields')
        if not isinstance(rule['id'],str) or not rule['id'] or rule['id'] in seen:raise ValueError('Duplicate event rule ID')
        seen.add(rule['id'])
        if not isinstance(rule['event'],str) or not rule['event']:raise ValueError('Invalid event name')
        names(rule['channels'],'channels')
        if not isinstance(rule['where'],dict) or any(not k.startswith('/') for k in rule['where']):raise ValueError('Event conditions require JSON Pointer keys')
        if rule['graph'] not in graphs:raise ValueError('Unknown execution graph')
    return thaw(freeze(rules)),graphs


class Plugin(Component):
    def install(self):self.bindings={}

    def bind(self,node,rules,graphs,operations,*,access_strength=0,on_error=None,binding='host'):
        rules,graphs=validate_rules(rules,graphs,operations)
        if any(not callable(fn) for fn in operations.values()):raise TypeError('Operation must be callable')
        bindings=self.bindings.setdefault(node,{})
        signal_rules=any(rule['event']=='signal/received' for rule in rules)
        if signal_rules and any(key!=binding and value[4]!=access_strength for key,value in bindings.items() if any(rule['event']=='signal/received' for rule in value[0])):
            raise ValueError('Signal bindings on one node must use the same access strength')
        saved=dict(rules=rules,graphs=graphs)
        if self.r.backend.extension_state.get('event_triggers',{}).get(node,{}).get(binding)!=saved:
            self.r.rpc('event_trigger_configure',actor='root',target=node,binding=binding,configuration=saved)
        registration=(rules,graphs,dict(operations),on_error,access_strength)
        bindings[binding]=registration
        if signal_rules:
            async def handle(context):
                event=dict(type='signal/received',channels=list(context.signal.channels),payload=dict(signal=context.signal.to_dict(),delivery=asdict(context.delivery)))
                return await self.emit(node,event,context)
            self.r.backend.signals.bind(node,handle,access_strength=access_strength)
        elif not any(any(rule['event']=='signal/received' for rule in value[0]) for value in bindings.values()):
            runtime=getattr(self.r.backend.network,'_signal_runtime',None)
            if runtime:runtime.unbind(node)

    async def emit(self,node,event,context=None,*,binding=None):
        if self.id not in self.r.enabled:raise PermissionError('Event trigger is disabled')
        event=thaw(freeze(event))
        if set(event)!={'type','channels','payload'} or not isinstance(event['type'],str):raise ValueError('Invalid event envelope')
        names(event['channels'],'channels');completed=[]
        bindings=self.bindings.get(node,{})
        selected=list(bindings.items()) if binding is None else [(binding,bindings[binding])]
        for key,registration in selected:
            rules,graphs,operations,on_error,_=registration
            # Keep synchronous operations synchronous so the executor moves them to a worker.
            def grant(name,fn):
                import inspect
                def check():
                    if self.id not in self.r.enabled or self.bindings.get(node,{}).get(key) is not registration:raise PermissionError('Event binding was revoked')
                if inspect.iscoroutinefunction(fn):
                    async def invoke(context,**args):check();return await fn(context,**args)
                else:
                    def invoke(context,**args):check();return fn(context,**args)
                return invoke
            grants={name:grant(name,fn) for name,fn in operations.items()}
            try:
                for rule in rules:
                    if rule['event']!=event['type']:continue
                    if rule['channels'] and not set(rule['channels']).intersection(event['channels']):continue
                    try:matches=all(resolve({'$ref':pointer},event)==value for pointer,value in rule['where'].items())
                    except (KeyError,IndexError,TypeError):matches=False
                    if not matches:continue
                    result=await self.r.plugins['capabilities/module_execution'].execute(node,graphs[rule['graph']],grants,event,context)
                    completed.append(dict(id=rule['id'],graph=rule['graph'],**result))
            except BaseException as error:
                if on_error:
                    try:await on_error(context,error)
                    except Exception as cleanup:error.add_note('Event cleanup failed: '+str(cleanup))
                raise
        return dict(matched=len(completed),executions=completed)

    def emit_sync(self,node,event,context=None,*,binding=None):
        try:asyncio.get_running_loop()
        except RuntimeError:return asyncio.run(self.emit(node,event,context,binding=binding))
        raise RuntimeError('Use await event_trigger.emit inside an async event loop')

    def unbind(self,node,*,binding='host'):
        bindings=self.bindings.get(node,{})
        bindings.pop(binding,None)
        if not bindings:self.bindings.pop(node,None)
        if not any(any(rule['event']=='signal/received' for rule in value[0]) for value in bindings.values()):
            runtime=getattr(self.r.backend.network,'_signal_runtime',None)
            if runtime:runtime.unbind(node)
