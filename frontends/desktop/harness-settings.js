const input=document.getElementById('executable'),message=document.getElementById('message'),source=document.getElementById('source');
const bridge=window.nexarborHarness;
async function load(){const value=await bridge.settings();input.value=value.saved??'';source.textContent='当前使用：'+value.executable+(value.environment?'（由 DATANET_HARNESS_EXE 覆盖）':'')+(value.status?.version?'；版本 '+value.status.version:'');if(value.status&&!value.status.compatible)message.textContent=value.status.error??'当前 Harness 缺少所需服务，请选择 0.2.1 或兼容版本。';}
const controls=[input,...document.querySelectorAll('button')];controls.forEach(control=>control.disabled=true);load().catch(error=>message.textContent=error.message).finally(()=>controls.forEach(control=>control.disabled=false));
document.getElementById('browse').onclick=async()=>{try{const value=await bridge.browse();if(value.executable)input.value=value.executable;}catch(error){message.textContent=error.message;}};
document.getElementById('automatic').onclick=()=>{input.value='';message.textContent='点击保存后恢复自动查找。';};
document.getElementById('save').onclick=async()=>{const button=document.getElementById('save');button.disabled=true;message.textContent='正在检查 Harness…';try{await bridge.save(input.value);await load();message.textContent='已保存。重新打开项目后使用此路径。';}catch(error){message.textContent=error.message;}finally{button.disabled=false;}};
