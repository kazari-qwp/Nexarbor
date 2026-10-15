import {fileURLToPath} from 'node:url';
import {createAdapter} from './adapters/harness/framework/adapter.js';
export const name='datanet-harness';
export const inject=['agents','sessions','tools','skills','systemPrompt','sessionTitle'];
export async function apply(ctx, config) {
  await createAdapter(ctx, {extensionRoot:fileURLToPath(new URL('./extensions/multi_agent/',import.meta.url)),...config});
}
