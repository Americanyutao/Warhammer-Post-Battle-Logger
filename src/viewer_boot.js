'use strict';
window.__WH3_EMBEDDED__=true;
(async()=>{
 try{
  const get=async(path,type)=>{const response=await fetch(path,{cache:'no-store'});if(!response.ok)throw Error('Could not load recording resources ('+response.status+').');return response[type]()};
  const resources=Promise.all([get('report.css','text'),get('preferences.json','json')]);
  const pause=()=>new Promise(resolve=>setTimeout(resolve,100));
  const status=async()=>{
   const value=await get('loading.json','json');
   if(value.error)throw Error(value.error);
   document.getElementById('viewer-loading').textContent=value.message+(value.stage==='reading'?' '+value.percent+'%':'');
   return value;
  };
  let loading;
  do{loading=await status();if(!loading.core_ready)await pause()}while(!loading.core_ready);
  const [data,[css,preferences]]=await Promise.all([get('summary.json','json'),resources]);
  const valueKey='wh3-report-values:'+String(data.metadata.started_pacific||data.start_s)+':'+String(data.units[0]?.id||'empty');
  const keys={graphs:'wh3-report-unit-graphs-v1',hide_explanations:'wh3-report-hide-graph-explanations-v1',unit_values:valueKey};
  const originalSet=Storage.prototype.setItem;
  for(const [name,key] of Object.entries(keys))if(preferences[name]!=null)originalSet.call(localStorage,key,preferences[name]);
  Storage.prototype.setItem=function(key,value){
   originalSet.call(this,key,value);
   const name=Object.keys(keys).find(name=>keys[name]===key);
   if(name)fetch('preferences.json',{method:'POST',headers:{'Content-Type':'application/json','X-WH3-Viewer':location.pathname.split('/')[1]},body:JSON.stringify({name,value:String(value)}),keepalive:true}).catch(()=>{});
  };
  document.getElementById('data').textContent=JSON.stringify(data);
  document.getElementById('app-style').textContent=css;
  const script=document.createElement('script');script.src='report_view.js';
  await new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=()=>reject(Error('Could not load report controls.'));document.body.appendChild(script)});
  document.body.classList.remove('is-loading');
  document.documentElement.dataset.viewerCoreReady='true';
  window.dispatchEvent(new Event('resize'));
  do{loading=await status();if(!loading.ready)await pause()}while(!loading.ready);
  applyReportAssets(await get('assets.json','json'));
  document.getElementById('viewer-loading').remove();
  document.documentElement.dataset.viewerReady='true';
 }catch(error){document.getElementById('viewer-loading').textContent='Cannot open this recording: '+error.message;document.documentElement.dataset.viewerError=error.message}
})();
