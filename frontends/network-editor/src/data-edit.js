import {moduleTable} from '../../shared/graph/node-records.js';
// 只合并仍与请求前相同的数据节点；不会覆盖等待期间的其他草稿修改。
const normal=value=>value.replaceAll('\\','/');
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function mergeDataEdit(document,value){
 const {beforeNode,beforeFiles,node,files}=value,nodes=document.network?.nodes??document.nodes,current=nodes.find(n=>n.node_id===beforeNode.node_id);
 if(!same(current,beforeNode)||node.node_id!==beforeNode.node_id)throw Error('节点配置已经变化，请重新读取后保存数据');
 const roots=beforeNode.data?.path?[normal(beforeNode.data.path)]:[];
 const owned=source=>Object.fromEntries(Object.entries(source??{}).map(([key,data])=>[normal(key),data]).filter(([key])=>roots.some(root=>key===root||key.startsWith(root.replace(/\/$/,'')+'/'))).sort(([a],[b])=>a.localeCompare(b)));
 if(!same(owned(document.files),owned(beforeFiles)))throw Error('节点数据已经变化，请重新读取后保存');
 const next=structuredClone(document),target=next.network?.nodes??next.nodes;target[target.findIndex(n=>n.node_id===node.node_id)]=structuredClone(node);Object.assign(next.files,structuredClone(files));return next;
}

export const isDataNode=node=>!['agent','knowledge_catalog'].includes(node?.type)&&!!node?.data||!!node&&!!moduleTable(node)['knowledge.collection'];
const dataBinding=node=>JSON.stringify([node.type,node.data?.type,node.data?.path,node.data?.directory??false,node.data?.parameters?.table_name,node.data?.parameters?.key_column]);
export function mergeClearedData(document,value){
 const {beforeNode,node,files,roots=[]}=value,next=structuredClone(document),nodes=next.network?.nodes??next.nodes,current=nodes.find(n=>n.node_id===beforeNode.node_id);
 if(!current||dataBinding(current)!==dataBinding(beforeNode))throw Error('真实数据已清空，但草稿的存储位置已改变，请刷新查看');
 if(moduleTable(node)['knowledge.collection']&&moduleTable(current)['knowledge.collection'])moduleTable(current)['knowledge.collection'].state=structuredClone(moduleTable(node)['knowledge.collection'].state);
 for(const name of Object.keys(next.files))if(roots.some(([root,kind])=>normal(name)===normal(root)||kind==='directory'&&normal(name).startsWith(normal(root).replace(/\/$/,'')+'/')))delete next.files[name];
 Object.assign(next.files,structuredClone(files));return next;
}
