// Git operations stay within this project's current Agent work branch.
export async function makerGit(manager,job,args={}){
 const project=manager.project;if(!project)throw Error('当前连接没有 Git 项目');
 const work=await manager.rpc('studio_read',{id:job.workspace});
 const save=async()=>{const git=await project.branch(work,{message:args.message});job.git=git;return git;};
 const remote=async()=>{const names=(await project.command(['remote'])).trim().split('\n').filter(Boolean),name=args.remote??'origin';if(!names.includes(name))throw Error('项目没有远程仓库 '+name+'；先用 remote 操作配置用户提供的仓库地址');return name;};
 try{
  if(args.action==='status')return {project:project.directory,work:work.id,branch:'agent-'+work.id,project_status:(await project.command(['status','--short'])).trim().split('\n').filter(Boolean),remotes:(await project.command(['remote'])).trim().split('\n').filter(Boolean)};
  if(args.action==='remote'){
   const name=args.remote??'origin';if(!/^[a-zA-Z0-9_.-]{1,64}$/.test(name))throw Error('远程仓库名称无效');
   if(!args.url)return {remotes:(await project.command(['remote'])).trim().split('\n').filter(Boolean)};
   if(typeof args.url!=='string'||args.url.length>2000||!(/^(https?:\/\/|ssh:\/\/|git@[^:]+:)/.test(args.url)))throw Error('请使用用户提供的 HTTPS 或 SSH 仓库地址');
   const existing=(await project.command(['remote'])).trim().split('\n');await project.command(['remote',existing.includes(name)?'set-url':'add',name,args.url]);return {remote:name,configured:true};
  }
  const git=await save();
  if(args.action==='commit')return git;
  if(args.action==='log'){const limit=Math.min(30,Math.max(1,args.limit??10));if(!Number.isInteger(limit))throw Error('历史条数无效');return {branch:git.branch,commits:(await project.command(['log','--first-parent','-'+limit,'--format=%H%x09%s',git.commit])).trim().split('\n').filter(Boolean).map(line=>{const [commit,...text]=line.split('\t');return {commit,message:text.join('\t')};})};}
  if(args.action==='diff'){
   let from=args.commit;if(from&&!/^[0-9a-f]{40}$/.test(from))throw Error('请使用 log 返回的完整提交编号');if(!from)try{from=(await project.command(['rev-parse',git.commit+'^'])).trim();}catch{return {branch:git.branch,first_commit:true,files:(await project.command(['ls-tree','-r','--name-only',git.commit])).trim().split('\n')};}
   const text=await project.command(['diff','--no-ext-diff','--no-textconv',from,git.commit,'--']),lines=text.split('\n'),start=args.start_line??1,count=args.line_count??160;if(!Number.isInteger(start)||start<1||!Number.isInteger(count)||count<1||count>300)throw Error('每次读取1至300行差异');return {branch:git.branch,from,to:git.commit,total_lines:lines.length,start_line:start,text:lines.slice(start-1,start-1+count).join('\n').slice(0,24000),more:start-1+count<lines.length};
  }
  if(args.action==='push'){
   const name=await remote(),branch=args.branch??git.branch;await project.command(['check-ref-format','refs/heads/'+branch]);await project.command(['push',name,git.branch+':refs/heads/'+branch],'',{GIT_TERMINAL_PROMPT:'0'});return {...git,remote:name,remote_branch:branch,pushed:true};
  }
  if(args.action==='restore'){
   if(!/^[0-9a-f]{40}$/.test(args.commit??''))throw Error('请先用 log 取得要恢复的完整提交编号');
   const module=work.kind==='network'?null:JSON.parse(work.files['module.json']).id,files=await project.workFiles({id:work.id,kind:work.kind,module,aliases:work.origin?.git_lineage??[],git:{commit:args.commit}}),manifest=module?JSON.parse(files['module.json']):null;
   const restored=await manager.rpc('studio_revision',{kind:work.kind,preserve_identity:true,source:manifest?{files,release:{id:manifest.id,manifest,version:manifest.version}}:undefined,document:manifest?undefined:JSON.parse(files['network.json']),origin:{git_restore:{commit:args.commit,previous:git},git_lineage:[work.id,...(work.origin?.git_lineage??[])],source:work.origin?.source},reference:'从 Git 提交 '+args.commit+' 恢复；原进度保留于 '+git.commit});
   const next=await project.branch(restored);job.workspace=restored.id;job.git=next;const session=manager.sessions.get(job.session_id);if(session)session.workspace=restored.id;return {restored:true,workspace:restored.id,previous:git,source_commit:args.commit,...next};
  }
  throw Error('未知 Git 操作');
 }catch(error){throw Error(String(error.message).replace(/(https?:\/\/)[^\s/@]+(?::[^\s/@]*)?@/g,'$1[已隐藏]@'));}
}
