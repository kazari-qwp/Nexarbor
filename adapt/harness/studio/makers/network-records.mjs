// Read-only view fields derived from the current node records.
export const moduleTable=node=>Object.fromEntries((node.tables?.modules??[]).map(module=>[module.module_id,{...module,access:{channels:module.channels,strength:module.strength,channel_mode:module.channel_mode}}]));
export const edgeMetadata=link=>({channels:link.channels??[],threshold:link.threshold??0,multiplier:link.processor?.factor??1,attributes:{...link.attributes,channel_mode:link.channel_mode??'allow'}});
export const viewNodes=document=>document.network.nodes.map(node=>({...node,management_parent_id:document.node_properties?.[node.node_id]?.management_parent_id,offered_ports:document.node_properties?.[node.node_id]?.offered_ports??[]}));
