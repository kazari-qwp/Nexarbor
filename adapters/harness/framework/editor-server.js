// Composition boundary: resource persistence and chat belong to this host.
import {startEditorServer as startTransport} from '../../../communication/editor-server.js';
import {editorLibrary} from './editor-library.js';

export function startEditorServer({request,chat,recover,runtime,...options}){
 const library=editorLibrary(options.directory,{runtime,catalog:()=>request('catalog',{}),inspect:p=>request('resource.inspect',p),purge:p=>request('resource.purge',p)});
 return startTransport({...options,request:(operation,params)=>
  ['editor.library','editor.library.index','editor.library.update','editor.resource.inspect','editor.resource.load'].includes(operation)?library(operation,params):
  operation?.startsWith('chat.')?chat(operation,params):operation==='recover'?recover(params):request(operation,params)});
}
