import {useOnViewportChange} from '@xyflow/react';
export function WorkspaceViewport({onChange}){useOnViewportChange({onEnd:onChange});return null;}
