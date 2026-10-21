const input=document.getElementById('executable'),message=document.getElementById('message'),source=document.getElementById('source');
const bridge=window.nexarborHarness;
async function load(){const value=await bridge.settings();input.value=value.saved??'';source.textContent='当前使用：'+value.executable+(value.environment?'（由 DATANET_HARNESS_EXE 覆盖）':'');}
load().catch(error=>message.textContent=error.message);
document.getElementById('browse').onclick=async()=>{try{const value=await bridge.browse();if(value.executable)input.value=value.executable;}catch(error){message.textContent=error.message;}};
document.getElementById('automatic').onclick=()=>{input.value='';message.textContent='点击保存后恢复自动查找。';};
document.getElementById('save').onclick=async()=>{try{await bridge.save(input.value);await load();message.textContent='已保存。重新打开项目后使用此路径。';}catch(error){message.textContent=error.message;}};
