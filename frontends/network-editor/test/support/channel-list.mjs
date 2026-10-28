// Drive the current channel-list control using its public labels.
export async function setChannels(page,label,channels){
 const group=page.getByRole('group',{name:label,exact:true});
 while(await group.locator('.channel-item').count()>channels.length)await group.locator('.channel-item').last().getByRole('button').click();
 while(await group.locator('.channel-item').count()<channels.length)await group.getByRole('button',{name:'添加频道',exact:true}).click();
 for(let index=0;index<channels.length;index++)await group.getByLabel(label+' '+(index+1),{exact:true}).fill(channels[index]);
}
