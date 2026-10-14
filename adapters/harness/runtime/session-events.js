// Extension records are opaque to the native persistence reader.
export const DATANET_LOG_EVENTS=new Set(['datanet/request-tail','datanet/request-recovery']);
export function durableEvent(event){
  return DATANET_LOG_EVENTS.has(event.type)&&event.ignorable!==true?{...event,ignorable:true}:event;
}
const installed=new WeakSet();
export function installSessionEventPersistence(ctx){
  const storage=ctx.get('sessionPersistence');
  if(!storage||installed.has(storage))return;
  installed.add(storage);
  const originals=new Map();
  for(const method of ['create','open']){
    const original=storage[method];
    const wrapped=async function(...args){
      const handle=await original.apply(this,args);
      return new Proxy(handle,{get(target,key){
        if(key==='append')return (events,...rest)=>target.append(events.map(durableEvent),...rest);
        const value=Reflect.get(target,key,target);
        return typeof value==='function'?value.bind(target):value;
      }});
    };
    originals.set(method,{original,wrapped});storage[method]=wrapped;
  }
  ctx.on('dispose',()=>{
    for(const [method,{original,wrapped}] of originals)if(storage[method]===wrapped)storage[method]=original;
    installed.delete(storage);
  });
}
