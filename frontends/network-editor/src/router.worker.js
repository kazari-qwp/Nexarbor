import {init} from '@mr_mint/elkjs-libavoid';
import wasmUrl from '../node_modules/@mr_mint/elkjs-libavoid/dist/libavoid.wasm?url';
import {sceneRouter} from './route-session.js';
const router=sceneRouter();let latest,running=false,ready;
self.onmessage=async({data})=>{
  latest=data;if(running)return;running=true;
  while(latest){
    const request=latest;latest=null;
    try{ready??=init(wasmUrl);await ready;const routes=await router.route(request.graph);self.postMessage({key:request.key,routes:[...routes]});}
    catch(error){router.destroy();self.postMessage({key:request.key,error:String(error.message??error)});}
  }
  running=false;
};
