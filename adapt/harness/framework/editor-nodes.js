// Node records for new drafts; assembly fills the actual component tool tables.
const labels={node:'普通节点',agent:'Agent 节点',markdown:'Markdown 节点',pulse:'脉冲节点',network_admin:'网络管理员'};
export function editorNode(kind,id,name){
 if(!Object.hasOwn(labels,kind))throw Error('未知节点类型');
 const administrator=kind==='network_admin';
 const node={type:administrator?'node':kind,node_id:id,name:name||labels[kind],description:'',bias:-1,aggregation:'sum',links:[],tables:{modules:[]}};
 if(kind==='markdown'||kind==='agent')node.data={type:'markdown',path:'data/'+id+'.md',save_data:true};
 if(kind==='agent'){node.agent={inputs:{}};node.execution=null;}
 if(kind==='pulse')node.parameters={channels:['world.tick'],strength:4};
 if(administrator)node.tables.modules.push({module_id:'network.administrator',config:{allow_component_creation:false,max_nodes:40,timeout_seconds:600},state:{},channels:['admin','tools','info','records','chat'],strength:2,channel_mode:'allow'});
 return node;
}
export function editorNodes(){
 return Object.entries(labels).map(([id,name])=>{const node=editorNode(id,'template-'+id,name);return {id,name,description:{node:'通用节点，可装配模块与工具。',agent:'Agent 节点，可配置模型执行与上下文。',markdown:'Markdown 节点，可编辑关联文档。',pulse:'脉冲节点，可配置频道与传播强度。',network_admin:'按自身可达范围组装和提交局部网络，可选择是否委托制作组件。'}[id],mode:'internal',snapshot:{nodes:[node],files:node.data?{[node.data.path]:''}:{},positions:{[node.node_id]:{x:0,y:0}}}};});
}
