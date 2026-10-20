import {init} from '@mr_mint/elkjs-libavoid';
import wasmUrl from '../node_modules/@mr_mint/elkjs-libavoid/dist/libavoid.wasm?url';
import {sceneRouter,routingOptions} from './route-session.js';
const router=sceneRouter(),pictureRouter=sceneRouter({...routingOptions,crossingPenalty:0,idealNudgingDistance:4,nudgeOrthogonalSegmentsConnectedToShapes:false,nudgeOrthogonalTouchingColinearSegments:false});let latest,running=false,ready;
self.onmessage=async({data})=>{
  latest=data;if(running)return;running=true;
  while(latest){
    const request=latest;latest=null;
    const active=request.picture?pictureRouter:router;
    try{ready??=init(wasmUrl);await ready;const routes=await active.route(request.graph);self.postMessage({key:request.key,routes:[...routes]});}
    catch(error){active.destroy();self.postMessage({key:request.key,error:String(error.message??error)});}
  }
  running=false;
};
