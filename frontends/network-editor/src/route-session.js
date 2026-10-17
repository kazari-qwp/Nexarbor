// libavoid owns obstacle avoidance, crossing costs, shared trunks and nudging.
import {createRoutingSession} from '@mr_mint/elkjs-libavoid';
export const routingOptions={routingType:'orthogonal',shapeBufferDistance:12,segmentPenalty:35,reverseDirectionPenalty:80,crossingPenalty:25,idealNudgingDistance:7,
  nudgeOrthogonalSegmentsConnectedToShapes:true,nudgeOrthogonalTouchingColinearSegments:true,nudgeSharedPathsWithCommonEndPoint:false};
export function sceneRouter(){
  let session,signature;
  return {
    async route(graph){
      const next=JSON.stringify([graph.children.map(({x,y,...node})=>node),graph.edges]);
      if(next!==signature){session?.destroy();session=undefined;signature=undefined;session=await createRoutingSession(graph,routingOptions);signature=next;}
      else for(const node of graph.children)session.moveNode(node.id,{x:node.x,y:node.y});
      return session.processTransaction();
    },
    destroy(){session?.destroy();session=undefined;signature=undefined;},
  };
}
