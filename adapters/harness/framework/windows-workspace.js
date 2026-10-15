// Owner ACL setup for the native Windows sandbox, once per mounted workspace.
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const execute=promisify(execFile);
const script=`$ErrorActionPreference='Stop'
$target=$env:DATANET_OWNER_WORKSPACE
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent()
$acl=[System.IO.Directory]::GetAccessControl($target)
if($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $identity.User.Value){exit 0}
$rights=[System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor [System.Security.AccessControl.FileSystemRights]::TakeOwnership
$inherit=[System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
$rule=[System.Security.AccessControl.FileSystemAccessRule]::new($identity.User,$rights,$inherit,[System.Security.AccessControl.PropagationFlags]::None,[System.Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($target,$acl)`;
export async function prepareWindowsWorkspace(workspace){
  if(process.platform!=='win32')return;
  await execute(path.join(process.env.SystemRoot??'C:/Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),['-NoProfile','-NonInteractive','-Command',script],{
    windowsHide:true,env:{...process.env,DATANET_OWNER_WORKSPACE:path.resolve(workspace)}
  });
}
