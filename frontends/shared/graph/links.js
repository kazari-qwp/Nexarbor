// Pure presentation metadata and its current Link record.
export const edgeMetadata=link=>({channels:link.channels??[],threshold:link.threshold??0,multiplier:link.processor?.factor??1,attributes:{...link.attributes,channel_mode:link.channel_mode??'allow'}});
export const linkRecord=(target,metadata)=>({target_id:target,channels:metadata.channels??[],threshold:metadata.threshold??0,processor:{type:'multiplier',factor:metadata.multiplier??1},channel_mode:metadata.attributes?.channel_mode??'allow',attributes:structuredClone(metadata.attributes??{})});
