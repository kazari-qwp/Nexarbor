import {fileURLToPath} from 'node:url';
import {createAdapter} from '../../../../adapters/harness/framework/adapter.js';
export const name='nexarbor-network-editor';
export const inject=['agents','sessions','tools','skills','systemPrompt','sessionTitle'];
export async function apply(ctx,config={}) {
  return createAdapter(ctx,{
    extensionRoot:fileURLToPath(new URL('../../',import.meta.url)),
    allowedAgentToolboxes:['world_resident'],
    ...config,
    editor:{...config.editor,enabled:true},
  });
}
