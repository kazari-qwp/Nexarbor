import {fileURLToPath} from 'node:url';
import {createAdapter} from '../../../../adapters/harness/framework/adapter.js';
export const name='nexarbor-knowledge-base';
export const inject=['agents','sessions','tools','skills','systemPrompt','sessionTitle'];
export async function apply(ctx,config={}){
  return createAdapter(ctx,{extensionRoot:fileURLToPath(new URL('../../',import.meta.url)),rootNetwork:'knowledge_base',rootToolboxes:['knowledge_base'],...config});
}
