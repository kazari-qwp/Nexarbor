// Optional, operator-only UI entry. Harness Connection owns authentication.
export function registerEditorLauncher(ctx, resolve) {
  ctx.inject(['connection'], scope => {
    scope.effect(() => scope.connection.fetch.register({
      path: '/api/nexarbor/editor', methods: ['POST'], requestBody: 'buffered',
      async fetch(request) {
        const reply=(status,value)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
        try {
          const input=await request.json();
          if(typeof input.session_id!=='string'||!input.session_id||input.session_id.length>256)return reply(400,{error:'请选择一份会话'});
          const value=await resolve(input.session_id);
          const url=new URL(value.url);
          if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.hash.startsWith('#token='))throw new Error('工作台启动地址无效');
          return reply(200,value);
        } catch(error) {return reply(400,{error:String(error.message??error)});}
      }
    }), 'nexarbor.editor.launcher');
  });
}
