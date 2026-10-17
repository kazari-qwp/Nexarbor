// Prebuilt plain-JS client plugin. React is supplied by the Harness platform.
window.__ModuleLoader__.load({
  id: "datanet-harness",
  factory(require) {
    const React=require('react');
    function EditorAction({sessionId}) {
      const [state,setState]=React.useState({loading:true});
      const [retry,setRetry]=React.useState(0);
      React.useEffect(()=>{
        const controller=new AbortController();setState({loading:true});
        fetch('api/nexarbor/editor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId}),signal:controller.signal})
          .then(async response=>{if(response.status===404)return {hidden:true};const body=await response.json();if(!response.ok)throw new Error(body.error??'工作台暂不可用');return body;})
          .then(value=>{if(!controller.signal.aborted)setState(value);})
          .catch(error=>{if(!controller.signal.aborted)setState({error:error.message});});
        return()=>controller.abort();
      },[sessionId,retry]);
      if(state.hidden)return null;
      const style={color:'var(--dsw-alias-label-secondary)',fontSize:12,padding:'5px 9px',borderRadius:6,textDecoration:'none',border:'1px solid var(--dsw-alias-border-l2)',background:'transparent',cursor:'pointer',display:'inline-flex',alignItems:'center',gap:5};
      if(state.url)return React.createElement('button',{type:'button',role:'button','aria-label':'打开网络工作台',title:'在 Nexarbor 客户端中打开工作台',style,onClick:async()=>{
        try{const response=await fetch('api/nexarbor/editor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,open:true})});const value=await response.json();if(!response.ok)throw new Error(value.error??'无法启动客户端');}
        catch(error){setState({error:error.message});}
      }},'◇ 网络工作台');
      return React.createElement('span',{style:{display:'inline-flex',alignItems:'center',gap:6}},
        React.createElement('button',{type:'button',style,disabled:state.loading,onClick:()=>setRetry(n=>n+1),'aria-label':'打开网络工作台',title:state.error??'正在连接工作台'},state.loading?'连接工作台…':'重试工作台'),
        state.error&&React.createElement('small',{role:'status',style:{maxWidth:260,fontSize:11}},state.error));
    }
    return {
      inject:['slots'],
      apply(ctx) {
        ctx.slots.inject('conversation.session.header.actions',()=>ctx.slots.register({name:'conversation.session.header.actions',id:'nexarbor-editor',order:-30},EditorAction));
      }
    };
  }
});
