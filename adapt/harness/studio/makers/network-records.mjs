// Read-only view fields derived from the current node records.
export const moduleTable=node=>Object.fromEntries((node.tables?.modules??[]).map(module=>[module.module_id,{...module,access:{channels:module.channels,strength:module.strength,channel_mode:module.channel_mode}}]));
export {edgeMetadata} from '../../../../frontends/shared/graph/links.js';
export const viewNodes=document=>document.network.nodes.map(node=>({...node,management_parent_id:document.network.properties?.[node.node_id]?.management_parent_id,offered_ports:document.network.properties?.[node.node_id]?.offered_ports??[]}));
