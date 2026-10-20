const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');

// Each immutable profile owns a provider route and a credential reference.
module.exports=async function({host,native,root,credentials,defaults={}}){
 const {CredentialProvider}=native('dsh-credentials');
 class Credentials extends CredentialProvider{
  constructor(ctx){super(ctx);this.values=new Map();}
  resolve(ref){const value=this.values.get(ref);return Promise.resolve(value===undefined?undefined:{value,source:'memory'});}
  describe(ref){return Promise.resolve({configured:this.values.has(ref),writable:false});}
  readRecord(){return Promise.resolve(undefined);}
  listRecords(){return Promise.resolve([]);}
 }
 await host.plugin(Credentials);
 const profiles=new Map(),secrets=new Set();let apiFiber,apiProfiles={},registration=Promise.resolve();
 const redact=value=>{let text=String(value?.stack??value);for(const key of secrets)if(key)text=text.split(key).join('[已隐藏密钥]');return text;};
 async function resolve(profile){
  profile??={kind:'harness-account',credentials,signature:'legacy-default',model:{provider:'deepseek-account',model:'deepseek-flash',maxTokens:16000,contextWindow:500000,reasoningEffort:'low',...defaults}};
  if(profiles.has(profile.signature))return profiles.get(profile.signature);
  const pending=(async()=>{
   let supportsImages=true;
   const provider='nexarbor-'+crypto.createHash('sha256').update(profile.signature).digest('hex').slice(0,32),model={...profile.model,provider};
   if(profile.kind==='harness-account'){
    if(!profile.credentials)throw Error('请配置 Harness 账户授权或选择一个 API key 连接');
    const grant=require(path.join(path.dirname(process.execPath),'resources/app.asar/dsh/node_modules/yaml')).parse(await fs.readFile(profile.credentials,'utf8')).records?.['deepseek-account-platform/default'];
    if(grant?.kind!=='grant'||new URL(grant.payload.issuer).origin!=='https://platform.deepseek.com')throw Error('未找到受支持的 Harness DeepSeek 账户授权');
    secrets.add(grant.payload.token);const deepseek=native('dsh-llm-deepseek'),models=JSON.parse(await fs.readFile(path.join(root,'adapters/harness/runtime/models.json'),'utf8'));
    supportsImages=models.find(m=>m.id===model.model)?.inputModalities?.includes('image')===true;
    const connection=deepseek.resolveAdapterOptions({models,maxTokens:model.maxTokens,retryPolicy:{mode:'normal',maxRetries:0},streamIdleTimeoutMs:60000});
    host.llm.registerAdapter([provider],new deepseek.DeepSeekAdapter({options:()=>connection,resolveAttachments:()=>host.get('attachments'),resolveAuth:async c=>{if(new URL(c.baseURL).origin!=='https://api.deepseek.com')throw Error('账户授权只能用于官方 DeepSeek API');return {headers:{'x-dsh-auth-token':grant.payload.token}};},resolveUserId:()=> 'nexarbor',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
   }else{
    const api=native('dsh-llm-pi-ai'),ref='NEXARBOR_'+provider.replaceAll('-','_');if(profile.api_key){secrets.add(profile.api_key);host.credentials.values.set(ref,profile.api_key);}
    const config={api:profile.protocol,baseURL:profile.base_url,...(profile.api_key?{apiKeyEnv:ref}:{}),models:[{id:model.model,name:model.model,contextWindow:model.contextWindow,maxTokens:model.maxTokens,input:['text','image']}],streamIdleTimeoutMs:60000,retryPolicy:{mode:'normal',maxRetries:0}};
    // Keep immutable routes for existing sessions while adding new connections.
    const add=registration.then(async()=>{apiProfiles={...apiProfiles,[provider]:config};if(!apiFiber)apiFiber=await host.plugin(api,{providers:apiProfiles});else{apiFiber.update({providers:apiProfiles},true);await apiFiber.await();}});registration=add.catch(()=>{});await add;
   }
   return {model,signature:profile.signature,supportsImages};
  })();profiles.set(profile.signature,pending);
  try{return await pending;}catch(error){profiles.delete(profile.signature);throw Error(redact(error));}
 }
 return {resolve,redact};
};
