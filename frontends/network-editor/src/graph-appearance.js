// Shared by the editor and Agent pictures. Bright strokes stay legible at overview zoom.
export const edgeColors=['#36cfff','#ffb72e','#ba8cff','#3ce79e','#ff6eae','#daef48','#ff795b','#7bafff'];
export function sourceColor(source){
 let hash=0;for(const c of source)hash=(hash*31+c.charCodeAt(0))>>>0;
 return edgeColors[hash%edgeColors.length];
}
export const nodeDimensions=type=>type==='subnode'?{width:100,height:34}:{width:84,height:84};
