import React from 'react';

export function SignalAggregation({value='sum',onChange,label='信号汇总方式'}){
 return <label>{label}<select aria-label={label} value={value} onChange={event=>onChange(event.target.value)}>
  <option value="sum">求和</option><option value="max">最大值</option><option value="min">最小值</option><option value="mean">平均值</option>
 </select><small>同一轮信号在同一层到达时，先汇总各入边的强度，再加节点内散度。</small></label>;
}
