// 实际采用前端拖拽装配器把制作器配置书签装入节点，再通过核心工具完成业务。
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import {startStudioProfile} from '../adapters/harness/studio/host.mjs';import {attachResource} from '../frontends/network-editor/src/resources.js';
const root=path.resolve(import.meta.dirname,'..'),directory=path.join(root,'build/wish-attachment-'+Date.now()),host=await startStudioProfile(path.join(root,'configs/npc_town_v3/profile.json'),{directory});
try{
 const preset=JSON.parse(await fs.readFile(path.join(root,'examples/component_presets/shop_credit.json'),'utf8')).presets[0],initial=await host.request('state'),catalog=await host.request('catalog'),before=initial.live.document.network.nodes.find(n=>n.node_id==='place/shop').modules['service.actions'];
 const document=attachResource(initial.live.document,'place/shop',{kind:'module',id:preset.module,config:preset.config},catalog);assert.deepEqual(document.network.nodes.find(n=>n.node_id==='place/shop').modules['service.actions'].access,before.access);
 await host.request('apply',{document,base_commit:initial.live.commit});
 const invoke=async(target,module,id,args={})=>{const entries=await host.rpc('executor_visit',{actor:'npc/sen',target}),entry=entries.tools.find(t=>t.module===module&&t.tool_id===id);assert.ok(entry,JSON.stringify(entries));return host.rpc('executor_invoke',{actor:'npc/sen',name:entry.alias,arguments:args});};
 // 操作名与Agent工具ID属于模块声明，借还动作ID来自制作器自己的合法配置。
 await invoke('place/home2','movement.here','move_here');await invoke('place/shop','movement.here','move_here');
 await invoke('place/shop','service.actions','perform',{action:'borrow_coins',quantity:5,key:'loan-bookmark'});await invoke('place/shop','service.actions','perform',{action:'buy_axe',quantity:1,key:'ordinary-buy'});
 const state=await host.request('state'),actor=state.live.document.network.nodes.find(n=>n.node_id==='npc/sen').modules['records.store'].state.values;assert.equal(actor.debt,5);assert.equal(actor.axe,2);assert.equal(actor.coins,8);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,config_only_bookmark_preserves_grants:true,core_tool_calls:true,loan:true,ordinary_trade_and_event_hooks:true,model_calls:0},null,2));console.log('PASS 配置书签拖入后保留授权并执行原有交易：'+directory);
}finally{await host.close();}
