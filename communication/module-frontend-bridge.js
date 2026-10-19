// 注入模块页面的最小接口；不提供宿主令牌、任意 RPC 或网络执行能力。
(()=>{
  const protocol='nexarbor-module-frontend/v1',listeners=new Set(),pending=new Map();let context=null,serial=0;
  const send=message=>parent.postMessage({protocol,...message},'*');
  const copy=value=>JSON.parse(JSON.stringify(value));
  window.addEventListener('message',event=>{
    if(event.source!==parent||event.data?.protocol!==protocol)return;
    const message=event.data;
    if(message.type==='context'){
      context=message.context;
      for(const callback of listeners)callback(copy(context));
    }else if(message.type==='result'){
      const request=pending.get(message.id);if(!request)return;
      pending.delete(message.id);clearTimeout(request.timer);
      message.error?request.reject(Error(message.error)):request.resolve(message.value);
    }
  });
  window.NexarborModule=Object.freeze({
    onContext(callback){listeners.add(callback);if(context)callback(copy(context));return()=>listeners.delete(callback);},
    getContext(){return context?copy(context):null;},
    setConfig(config){
      if(!context)return Promise.reject(Error('客户端尚未提供模块上下文'));
      const id=String(++serial);
      return new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{pending.delete(id);reject(Error('客户端未响应配置修改'));},5000);
        pending.set(id,{resolve,reject,timer});send({type:'set-config',id,instance:context.instance,config});
      });
    },
    preview(){
      if(!context)return Promise.reject(Error('客户端尚未提供模块上下文'));
      const id=String(++serial);
      return new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{pending.delete(id);reject(Error('预览超时'));},15000);
        pending.set(id,{resolve,reject,timer});send({type:'preview',id,instance:context.instance});
      });
    },
    resize(height){if(context)send({type:'resize',instance:context.instance,height});},
  });
  send({type:'ready'});
})();
