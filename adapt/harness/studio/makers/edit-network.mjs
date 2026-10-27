// Candidate-only commands. Runtime validation and administrator scope still apply at publish.
import {editorNode} from '../../framework/editor-nodes.js';
const merge=(left,right)=>right&&typeof right==='object'&&!Array.isArray(right)?Object.fromEntries(Object.entries({...left,...right}).map(([key,value])=>[key,Object.hasOwn(right,key)?merge(left?.[key],value):value])):structuredClone(right);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

export function editNetwork(original,commands,library){
 if(!Array.isArray(commands)||!commands.length||commands.length>100)throw Error('请提供 1–100 条组装命令');
 const document=structuredClone(original),nodes=new Map(document.network.nodes.map(n=>[n.node_id,n])),touched=new Set();
 const get=id=>{const node=nodes.get(id);if(!node)throw Error('节点不存在：'+id);touched.add(id);return node;};
 for(const [index,c] of commands.entries())try{
  if(!c||typeof c!=='object'||Array.isArray(c))throw Error('命令必须是对象');
  if(c.op==='node.create'){
   if(typeof c.id!=='string'||!c.id)throw Error('node.create 需要 id');
   if(nodes.has(c.id))throw Error('节点已存在：'+c.id+'；修改请用 node.update');
   const node=editorNode(c.kind??'node',c.id,c.name);
   nodes.set(c.id,node);touched.add(c.id);
   if(node.data)document.files[node.data.path]??='';
  }else if(c.op==='node.update'){
   if(!c.patch||typeof c.patch!=='object'||Array.isArray(c.patch)||Object.hasOwn(c.patch,'node_id'))throw Error('node.update 需要 patch，编号不能改变');
   nodes.set(c.node,merge(get(c.node),c.patch));
  }else if(c.op==='module.mount'){
   const node=get(c.node),release=library[c.module];if(!release)throw Error('模块未发布：'+c.module);
   const defaults=release.mount_defaults??{config:release.defaults??{},state:{},access:{strength:0,channels:[]}};
   node.tables??={modules:[]};
   const index=node.tables.modules.findIndex(module=>module.module_id===c.module),previous=index<0?null:node.tables.modules[index];
   let mount=merge({config:{},state:{},access:{strength:0,channels:[]}},previous?{config:previous.config,state:previous.state,access:{strength:previous.strength,channels:previous.channels,channel_mode:previous.channel_mode}}:defaults);
   for(const key of ['config','state','access'])if(Object.hasOwn(c,key))mount[key]=merge(mount[key],c[key]);
   const record={...previous,module_id:c.module,config:mount.config,state:mount.state,...mount.access};
   if(index<0)node.tables.modules.push(record);else node.tables.modules[index]=record;
  }else if(c.op==='module.remove'){
   const node=get(c.node);node.tables.modules=node.tables.modules.filter(module=>module.module_id!==c.module);
  }else if(c.op==='edge.add'||c.op==='edge.remove'){
   const source=get(c.source);get(c.target);const edges=source.links;
   if(c.op==='edge.add'){
    if(!Array.isArray(c.channels)||!c.channels.length)throw Error('edge.add 需要非空 channels');
    const metadata={threshold:c.threshold??1,multiplier:c.multiplier??1,channels:c.channels,attributes:c.attributes??{}},edge={target_id:c.target,channels:metadata.channels,threshold:metadata.threshold,processor:{type:'multiplier',factor:metadata.multiplier},channel_mode:metadata.attributes.channel_mode??'allow',attributes:metadata.attributes};
    if(!edges.some(e=>same(e,edge)))edges.push(edge);
   }else source.links=edges.filter(e=>e.target_id!==c.target||c.metadata&&!same({threshold:e.threshold,multiplier:e.processor.factor,channels:e.channels,attributes:e.attributes},c.metadata));
  }else if(c.op==='text.write'){
   if(typeof c.path!=='string'||!c.path||c.path.startsWith('/')||/[\\:]/.test(c.path)||c.path.split('/').includes('..')||typeof c.text!=='string')throw Error('text.write 使用项目内相对 path 和字符串 text');
   document.files[c.path]=c.text;
  }else throw Error('未知 op：'+c.op+'；按需读取 make-network 的 references/批量组装.md');
 }catch(error){throw Error('第 '+(index+1)+' 条命令：'+error.message+'；整批未保存');}
 document.network.nodes=[...nodes.values()];
 return {document,receipt:{commands:commands.length,touched:[...touched].slice(0,12),touched_count:touched.size,counts:{nodes:nodes.size,edges:document.network.nodes.reduce((sum,n)=>sum+n.links.length,0),files:Object.keys(document.files).length},hint:'草稿已保存；用 view_network / inspect_nodes 按需核对，再 validate 和试运行。'}};
}
