import {fileURLToPath} from 'node:url';
import {createAdapter} from '../../../../adapters/harness/framework/adapter.js';
export const name='nexarbor-npc-world';
export const inject=['agents','sessions','tools','skills','systemPrompt','sessionTitle'];
export async function apply(ctx,config={}){
  return createAdapter(ctx,{extensionRoot:fileURLToPath(new URL('../../',import.meta.url)),rootNetwork:'small_town',rootToolboxes:['world_operator'],...config});
}
