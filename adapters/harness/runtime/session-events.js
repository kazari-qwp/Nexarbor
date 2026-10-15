// Extension records remain available to our replay, while native readers may skip them.
export const DATANET_LOG_EVENTS=new Set(['datanet/request-tail','datanet/request-recovery']);
export function durableEvent(event){
  return DATANET_LOG_EVENTS.has(event.type)&&event.ignorable!==true?{...event,ignorable:true}:event;
}
// Wrap the actual owned handle, rather than patching an optional Cordis service
// during plugin startup. The persistence service may be loaded after AgentLoop.
const liveWriters=new WeakSet();
export function durableSessionHandle(handle){
  // The native JSONL backend routes session/event directly to enqueueLive;
  // wrapping append alone misses every event emitted after publication.
  if(typeof handle.enqueueLive==='function'&&!liveWriters.has(handle)){
    const enqueueLive=handle.enqueueLive;
    handle.enqueueLive=function(event,...rest){return enqueueLive.call(this,durableEvent(event),...rest);};
    liveWriters.add(handle);
  }
  return new Proxy(handle,{get(target,key){
    if(key==='append')return (events,...rest)=>target.append(events.map(durableEvent),...rest);
    const value=Reflect.get(target,key,target);
    return typeof value==='function'?value.bind(target):value;
  }});
}
