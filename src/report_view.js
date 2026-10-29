'use strict';
const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
if($('recording-warning')&&D.recording_warnings?.length){$('recording-warning').hidden=false;$('recording-warning').textContent=D.recording_warnings.join(' ')}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>v==null?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
const seconds=v=>fmt(v,0);
const battleTime=v=>fmt(v,0);
const HEALING_CAP_TIP='Remaining healing allowance, read from the game. The normal base is 75% of maximum HP; healing-cap modifiers change it.';
const CHARACTER_VALUE_TIP='Lords and heroes default to 500 gold per level, or level 1 if unknown. Edit the value for this report.';
const FATIGUE_NAMES=['Fresh','Active','Winded','Tired','Very tired','Exhausted','Maximum'];
const fatigueName=v=>Number.isInteger(v)&&v>=0&&v<6?FATIGUE_NAMES[v]:'Unknown';
const displayFatigueState=a=>Number.isFinite(a?.fatigue_points)&&D.fatigue_rules?.maximum>0&&a.fatigue_points>=D.fatigue_rules.maximum?6:Number.isInteger(a?.fatigue_state_native??a?.fatigue_state)&&(a.fatigue_state_native??a.fatigue_state)>=0&&(a.fatigue_state_native??a.fatigue_state)<6?(a.fatigue_state_native??a.fatigue_state):null;
const displayFatigueName=a=>FATIGUE_NAMES[displayFatigueState(a)]||'Unknown';
const A=D.assets||{stats:{},units:{},images:{},provenance:{}};
// One battle-time selection is shared by the page and its owned popouts.
const synchronizedGraphs=new Map();let sharedTime=null;
let hoverCanvas=null,hoverAnchor={x:.5,y:.5},tooltipCorner=0,tooltipsEnabled=true;
const hoverDocuments=new Set();
function clearGraphHover(){
 hoverCanvas=null;
 for(let graph of synchronizedGraphs.values()){let tip=graph.doc.getElementById(graph.id+'-tooltip');if(tip)tip.hidden=true}
}
function beginGraphHover(canvas,event){
 const r=canvas.getBoundingClientRect();hoverCanvas=canvas;
 hoverAnchor={x:Math.max(0,Math.min(1,(event.clientX-r.left)/(r.width||1))),y:Math.max(0,Math.min(1,(event.clientY-r.top)/(r.height||1)))};
}
function showGraphTooltip(canvas,tip,html){
 if(!tip)return;if(!hoverCanvas||!tooltipsEnabled||tooltipCorner===4){tip.hidden=true;return}
 tip.innerHTML=html;const remote=canvas!==hoverCanvas,doc=canvas.ownerDocument||document,win=doc.defaultView||window,r=canvas.getBoundingClientRect(),width=win.innerWidth||window.innerWidth||1280,height=win.innerHeight||window.innerHeight||800;
 const top=r.top||0,bottom=r.bottom??top+(r.height||210);
 if(remote&&(bottom<0||top>height)){tip.hidden=true;return}
 const expanded=!remote&&canvas.id==='effects'&&showAllActiveFlags&&!simplifiedEffectTooltip;
 tip.className='chart-tooltip'+(remote?' remote-tooltip':expanded?' effects-all-tooltip':'');tip.style.width='';tip.hidden=false;
 if(expanded)fitEffectTooltip(tip,width,height);
 const box=tip.getBoundingClientRect(),tw=Math.min(box.width||230,width-16),th=box.height||60,x=(r.left||0)+hoverAnchor.x*r.width,y=top+hoverAnchor.y*(r.height||210),right=tooltipCorner===0||tooltipCorner===1,above=tooltipCorner===1||tooltipCorner===2;
 let px=right?x+12:x-tw-12,py=remote?(above?top-th-6:bottom+6):(above?y-th-12:y+12);
 if(remote&&(py<0||py+th>height)){tip.hidden=true;return}
 tip.style.left=Math.max(8,Math.min(width-tw-8,px))+'px';tip.style.top=Math.max(8,Math.min(height-th-8,py))+'px';
}
function fitEffectTooltip(tip,width,height){
 tip.style.width=Math.min(350,width-16)+'px';
 const columns=tip.querySelector?.('.effect-tooltip-columns');
 if(columns){columns.style.columnCount='1';if(tip.scrollHeight>height-16){tip.style.width=Math.min(720,width-16)+'px';columns.style.columnCount='2'}}
}
function rotateGraphTooltip(canvas,event){beginGraphHover(canvas,event);tooltipCorner=(tooltipCorner+1)%5;if(sharedTime!==null)publishTime(sharedTime,canvas);const graph=synchronizedGraphs.get(canvas),tip=graph?.doc.getElementById(graph.id+'-tooltip');if(tip?.className?.includes('chart-tooltip'))showGraphTooltip(canvas,tip,tip.innerHTML);else if(graph?.id==='movement'&&tip)tip.hidden=!tooltipsEnabled||tooltipCorner===4}
function registerTimeGraph(id,doc,render){
 const canvas=doc.getElementById(id);if(!canvas)return;
 synchronizedGraphs.set(canvas,{id,doc,canvas,render});
 const win=doc.defaultView||window;if(!hoverDocuments.has(doc)){hoverDocuments.add(doc);win.addEventListener('blur',clearGraphHover);win.addEventListener('scroll',event=>{if(!event?.target?.closest?.('.effects-all-tooltip'))clearGraphHover()},{capture:true,passive:true})}
 if(sharedTime!==null)render(sharedTime,null);
}
function publishTime(time,source=null){
 if(!Number.isFinite(time))return;
 const start=D.timeline_start_s??D.start_s??0,end=D.end_s??time;
 sharedTime=Math.max(start,Math.min(end,time));
 for(let [canvas,graph] of synchronizedGraphs){
  if(graph.doc.defaultView?.closed||graph.doc.getElementById(graph.id)!==canvas){synchronizedGraphs.delete(canvas);continue}
  if((graph.id==='movement'||graph.id==='movement-time')&&view==='unit'&&movementState(D.units.find(u=>u.id===selected)||{}).locked)continue;
  canvas._sharedTime=sharedTime;graph.render(sharedTime,source);
 }
}
function dropTimeGraphs(doc){for(let [canvas,graph] of synchronizedGraphs)if(graph.doc===doc)synchronizedGraphs.delete(canvas)}
const icon=(key)=>{let secondary=key.endsWith(':2'),base=secondary?key.slice(0,-2):key,src=A.images[A.stats[base]];return src?(secondary?'<span class="secondary-icon"><img class="stat-icon" alt="" src="'+src+'"><sub>2</sub></span>':'<img class="stat-icon" alt="" src="'+src+'">'):''};
const unitName=u=>A.labels?.[u.name]?A.labels[u.name]+(u.display_name||u.name).slice(u.name.length):u.display_name||u.name;
const unitCard=u=>A.unit_cards?A.unit_cards[u.id]:A.units[u.name];
const cardNote=u=>A.unit_notes?.[u.id]||A.unit_notes?.[u.name];
function cardImage(u,small=false){let name=unitCard(u),src=A.images[name];if(A.icons_enabled===false)return '<img class="'+(small?'mini-card':'unit-card')+'" src="'+A.images[A.stats.other]+'" alt="Unit icon disabled">';return src?'<img class="'+(small?'mini-card':'unit-card')+'" src="'+src+'" alt="'+esc(u.name)+' game unit card" title="'+esc(name)+'">':small?icon('other'):'<span class="missing-card" title="Unit card not mapped yet">'+icon('other')+'</span>'}
// Missing live values stay unknown. Inactive/removed units may display the
// last readable HP/model count; this does not infer final HP or an exit cause.
const known=(u,k)=>(k==='hp_cached'?u.terminal_result?.hp:k==='models'?u.terminal_result?.models:null)??u.last[k]??(['hp_max_cached','models_initial','damage','gold_damage','kills','damage_by_source'].includes(k)||(['hp_cached','models'].includes(k)&&(u.last.alive===false||u.last.left_battlefield===true))?u.last_observed?.[k]?.value:null)??null;
const DIRECT_TIP='Mortis Engines, Spirit Leech, and other abilities that deal damage through a debuff.';
const MISSILE_TIP='Missile damage and some spells, such as vortex spells. Needs more testing.';
const MELEE_TIP='All melee damage, including charge and collision damage.';
const HEALING_TIP='Damage taken = (initial ceiling − current ceiling) × max HP. Healing received = current HP + damage taken − starting HP. Uses the deployment baseline when available; assumes equal healing-budget spending.';
const HEALING_BUDGET_TIP='Healing budget remaining = initial budget − healing received. Initial budget = initial ceiling × max HP − starting HP. Ceiling fractions include HP and unused budget.';
const OTHER_TIP='Other damage not counted as direct damage, melee, charge, collision or missiles.';
const SELF_TIP='Damage to the unit itself, including miscast damage, crumbling and area effects.';
const SHARE_TIP='Percentage of this unit’s damage dealt to enemies. Friendly fire and self damage are shown as flat HP values.';
const sourceValue=(u,category,relation='enemy')=>{let s=known(u,'damage_by_source');if(!s)return null;let keys=category==='melee_combined'?['melee','charge','melee_collision']:[category],vs=keys.map(k=>s[k]?.[relation]);return vs.every(Number.isFinite)?vs.reduce((a,b)=>a+b,0):null};
const relationTotal=(u,r)=>{let s=known(u,'damage_by_source');return s?Object.values(s).reduce((n,v)=>n+v[r],0):null};
const friendly=u=>relationTotal(u,'ally');
const AMMO_KEYS={primary_ammo_initial:['primary','initial'],primary_ammo_expended:['primary','expended'],secondary_ammo_initial:['secondary','initial'],secondary_ammo_expended:['secondary','expended']};
const ammoValue=(u,key)=>{let [pool,field]=AMMO_KEYS[key]||[];return u.ammo?.[pool]?.[field]??null};
const AMMO_TIP='Starting ammo minus ending ammo. Replenishment is not separately accounted for.';
const isAmmoExpended=k=>k==='primary_ammo_expended'||k==='secondary_ammo_expended';
function ammoPercent(u,key){let spent=ammoValue(u,key),initial=ammoValue(u,key.replace('_expended','_initial'));return Number.isFinite(spent)&&initial>0?spent/initial*100:null}
const everFlew=u=>u.ever_flying===true||u.first?.flying===true||u.last?.flying===true||(u.history||[]).some(p=>p.flying===true);
const visibleActivity=(u,key)=>!(['flying','grounded'].includes(key)&&!everFlew(u))&&!(key==='firing'&&!(ammoValue(u,'primary_ammo_initial')>0||ammoValue(u,'secondary_ammo_initial')>0));
const leftBattle=u=>u.last.left_battlefield===true||u.last_observed?.left_battlefield?.value===true;
const isSummon=u=>u.first?.spawned===true||u.last.spawned===true;
const statusRank=u=>isSummon(u)?8:u.terminal_result?.status==='Dead'?6:u.terminal_result?.status==='Retreated'?7:leftBattle(u)||u.last.alive===false?4:!u.fresh?5:u.last.shattered===true?2:u.last.withdrawing===true?3:u.last.routing===true?1:u.last.alive===true?0:5;
const statusName=u=>['Alive','Routed','Shattered','Retreating','Dead / retreated','Unknown / missing','Dead','Retreated','Summon'][statusRank(u)];
// A withdrawal order does not prove the unit has actually left the battlefield.
const value=(u,k)=>AMMO_KEYS[k]?ammoValue(u,k):k==='name'?unitName(u):k==='status'?statusRank(u):k==='friendly'?friendly(u):k==='self'?relationTotal(u,'self'):k==='damage_taken'?u.damage_taken_estimate??null:k==='healing_applied'?u.healing_received_estimate??null:k==='trade'?tradePercent(u):k==='hp_and_models'?known(u,'hp_cached'):k.startsWith('source:')?sourceValue(u,k.slice(7)):known(u,k);
const CATEGORIES={
 simple:{name:'Simple',icon:'damage',sort:'damage',columns:[['Damage dealt','damage','damage'],['Gold damage dealt','gold_damage','gold'],['Damage taken','damage_taken','hp'],['Last observed status','status','status'],['HP remaining','hp_cached','hp'],['Models remaining','models','models']],note:''},
 damage:{name:'Damage breakdown',icon:'damage',sort:'damage',columns:[['Damage dealt','damage','damage'],['Gold damage dealt','gold_damage','gold'],['Kills','kills','kills'],['Direct damage','source:ability','ability'],['Melee','source:melee_combined','melee'],['Missiles','source:missile','missile'],['Other','source:other','other'],['Friendly fire','friendly','damage'],['Self damage','self','hp']],note:''},
 ranged:{name:'Ranged damage',icon:'missile',sort:'primary_ammo_expended',columns:[['Initial ammo','primary_ammo_initial','ammo'],['Ammo expended','primary_ammo_expended','firing'],['Missile damage','source:missile','missile'],['Initial secondary ammo','secondary_ammo_initial','ammo:2'],['Secondary ammo expended','secondary_ammo_expended','firing:2']],note:''},
 gold:{name:'Gold damage',icon:'gold',sort:'gold_damage',columns:[['Gold damage dealt','gold_damage','gold'],['Trade','trade','trade']],note:''},
 taken:{name:'Damage taken',icon:'hp',sort:'damage_taken',columns:[['Damage taken','damage_taken','hp'],['HP remaining','hp_cached','hp']],note:''},
 healing:{name:'Healing received',icon:'healing',sort:'healing_applied',columns:[['Healing received','healing_applied','healing'],['Healing budget remaining','healing_budget_remaining_hp','healing']],note:''},
 barrier:{name:'Barrier',icon:'barrier',sort:'name',columns:[],workInProgress:true,note:''},
 remaining:{name:'HP & models',icon:'hp',sort:'hp_cached',columns:[['HP remaining','hp_cached','hp'],['Models remaining','models','models'],['Initial models / max models','models_initial','models'],['Last observed status','status','status']],note:''}
};
let category='simple',side='Allied',sort='damage',ascending=false,selected=null,view='main',unitHeaderMinimized=false;
const percentText=(v,whole=false)=>fmt(whole?Math.floor(v):v,whole?0:1);
const percentDamage=(v,total,whole=false)=>v==null?'—':'('+(total>0?percentText(v/total*100,whole):total===0&&v===0?'0':'—')+'%) '+fmt(v);
const hpText=(u,whole=false)=>{let hp=known(u,'hp_cached'),max=known(u,'hp_max_cached');return '('+(hp!=null&&max>0?percentText(hp/max*100,whole):'—')+'%) '+fmt(hp)+'/'+fmt(max)};
const modelsText=u=>fmt(known(u,'models'))+'/'+fmt(known(u,'models_initial'));
function cellText(u,k){if(isAmmoExpended(k)){let percent=ammoPercent(u,k);return (percent==null?'':'('+percentText(percent,true)+'%) ')+fmt(ammoValue(u,k))}if(k==='status')return esc(statusName(u));if(k==='hp_and_models')return hpText(u)+' ('+modelsText(u)+')';if(k==='hp_cached')return hpText(u,true);if(k==='models')return modelsText(u);if(k==='models_initial')return fmt(u.initial_models_observed??u.first?.models)+'/'+fmt(u.initial_models_maximum??u.first?.models_initial??known(u,'models_initial'));if(k==='trade')return value(u,k)==null?'—':percentText(value(u,k),true)+'%';if(k.startsWith('source:'))return percentDamage(value(u,k),known(u,'damage'),true);if(k==='damage_taken')return percentDamage(value(u,k),u.damage_taken_calculation?.baseline?.maximum_hp,true);return fmt(value(u,k))}
function cellTip(k){return AMMO_KEYS[k]?(k.endsWith('_initial')?'Starting ammunition pool.':AMMO_TIP):({
 'source:ability':DIRECT_TIP,'source:melee_combined':MELEE_TIP,'source:missile':MISSILE_TIP,'source:other':OTHER_TIP,
 self:SELF_TIP,friendly:'Damage dealt to other units on the same side.',healing_applied:HEALING_TIP,
 healing_budget_remaining_hp:HEALING_BUDGET_TIP,trade:'Enemy gold damage / unit value × 100. Edit unit value in Unit view.',
 gold_damage:'Enemy gold-damage credit recorded by the game.',damage:'HP damage dealt to enemies. Excludes barrier absorption.',
 hp_cached:'Last recorded HP / maximum HP.',models:'Last recorded models / initial models.',models_initial:'Starting models / maximum models.',
 status:'Last recorded unit status.'
 }[k]||'')}
const VALUE_STORAGE='wh3-report-values:'+String(D.metadata.started_pacific||D.start_s)+':'+String(D.units[0]?.id||'empty');
let unitValues={};try{let raw=JSON.parse(localStorage.getItem(VALUE_STORAGE));if(raw&&typeof raw==='object'&&!Array.isArray(raw))for(let[k,v]of Object.entries(raw))if(Number.isFinite(v)&&v>=0)unitValues[k]=v}catch(_){}
function unitWorth(u){if(Object.hasOwn(unitValues,u.id))return {value:unitValues[u.id],source:'Manual value',description:'Unit value entered for this report. '+CHARACTER_VALUE_TIP};let captured=u.last.unit_gold_value??u.last_observed?.unit_gold_value?.value??u.first?.unit_gold_value;if(Number.isFinite(captured)&&captured>=0)return {value:captured,source:'Captured value',description:'Unit value provided by the capture. '+CHARACTER_VALUE_TIP};if(A.unit_info?.[u.id]?.character||u.last.has_character_rank===true||u.first?.has_character_rank===true){let level=u.last.character_level??u.last_observed?.character_level?.value??u.first?.character_level;let recorded=Number.isInteger(level)&&level>0;level=recorded?level:1;return {value:500*level,source:recorded?'500 gold × level '+level:'500 gold × assumed level 1',description:CHARACTER_VALUE_TIP+' '+(recorded?'Captured level: '+level+'.':'Character level was not recorded.')}}if(u.last.spawned===true||u.first?.spawned===true)return {value:null,source:'Value needed',description:'Summoned units have no verified purchase value; enter a value to calculate Trade.'};let candidates=(A.unit_values_by_id?.[u.id]??A.unit_values?.[u.name]??[]).filter(c=>!c.summoned_variant),values=[...new Set(candidates.map(c=>c.value))];return values.length===1?{value:values[0],source:'Base MP value',description:'Base multiplayer database price. Excludes upgrades, ranks, items and campaign adjustments; edit it for this battle. '+CHARACTER_VALUE_TIP}:{value:null,source:'Value needed',description:'No unambiguous unit value was captured; variants may have different prices. Enter this unit’s value. '+CHARACTER_VALUE_TIP}}
function tradePercent(u){let price=unitWorth(u).value,gold=known(u,'gold_damage');return price>0&&gold!=null?gold/price*100:null}
function showUnitValue(u){let w=unitWorth(u);$('unit-value').value=w.value??'';$('unit-value-label').title=w.description;$('unit-value-source').textContent=w.source}
$('unit-value').onchange=()=>{let u=D.units.find(u=>u.id===selected);if(!u)return;let raw=$('unit-value').value.trim(),v=Number(raw);if(raw==='')delete unitValues[u.id];else if(Number.isFinite(v)&&v>=0)unitValues[u.id]=v;try{localStorage.setItem(VALUE_STORAGE,JSON.stringify(unitValues))}catch(_){}showUnitValue(u);renderTable()};
const METRICS=[['hp_cached','Health'],['models','Models'],['damage','Damage dealt'],['damage_taken_estimate','Calculated damage taken'],['healing_received_estimate','Calculated healing received'],['primary_ammo_expended','Primary ammo expended'],['secondary_ammo_expended','Secondary ammo expended'],['fatigue_state','Fatigue state'],['fatigue_points','Fatigue points'],['leadership','Leadership'],['healing_cap_remaining','Max healing cap'],['healing_budget_remaining_hp','Healing budget left'],['elevation','Elevation'],...['ability','melee','missile','charge','melee_collision','other'].map(k=>['native:'+k,'Damage: '+({ability:'Direct damage',missile:'Missiles',melee_collision:'collision'}[k]||k)])];
const GRAPH_IDS=['view-1','view-2','view-4','view-5'],GRAPH_STORAGE='wh3-report-unit-graphs-v1';
let graphMetrics=['hp_cached','models','damage','healing_cap_remaining'];try{let saved=JSON.parse(localStorage.getItem(GRAPH_STORAGE));if(Array.isArray(saved))graphMetrics=graphMetrics.map((v,i)=>METRICS.some(m=>m[0]===(saved[i]==='primary_ammo'?'primary_ammo_expended':saved[i]==='secondary_ammo'?'secondary_ammo_expended':saved[i]))?(saved[i]==='primary_ammo'?'primary_ammo_expended':saved[i]==='secondary_ammo'?'secondary_ammo_expended':saved[i]):v)}catch(_){}
{let used=new Set();graphMetrics=graphMetrics.map(v=>{if(used.has(v))v=METRICS.find(([k])=>!used.has(k)&&!graphMetrics.includes(k))[0];used.add(v);return v})}
const minis=[],MINI_PREFIX='wh3-mini-'+Math.random().toString(36).slice(2);let miniCounter=0,miniWatcher=null;
function chartOccupied(unitId,metric,owner){
 if(!owner?.startsWith('main-'))return false;
 return selected===unitId&&GRAPH_IDS.some((id,i)=>'main-'+i!==owner&&layout.some(p=>p.id===id&&p.visible)&&graphMetrics[i]===metric);
}

function miniMessage(message){$('mini-status').textContent=message}
function miniUnitOptions(m){return D.units.filter(u=>m.scope==='All'||u.side===m.scope).map(u=>'<option value="'+esc(u.id)+'" '+(u.id===m.unitId?'selected':'')+'>'+esc(unitName(u))+'</option>').join('')}
function miniDocument(m,win){
 const doc=win.document;doc.head.innerHTML='<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Battle graph</title>';doc.body.innerHTML='';
 let style=doc.createElement('style');style.textContent=document.querySelector('style').textContent;doc.head.appendChild(style);doc.body.className='mini-report';
 win.addEventListener('resize',()=>drawMini(m));win.addEventListener('pagehide',()=>{if(m.win===win)removeMini(m)});
}
function drawMini(m){const u=D.units.find(u=>u.id===m.unitId);if(!u||m.win.closed)return;plot('mini-chart',u.history,[m.metric],['#d9bd78'],u,m.win.document);let label=m.win.document.getElementById('mini-metric');if(label)label.title=hideGraphExplanations?'':metricNote(m.metric,u);let note=m.win.document.getElementById('mini-note');if(note){note.textContent=metricNote(m.metric,u);note.hidden=hideGraphExplanations}}
function renderMini(m){
 if(m.win.closed)return;const doc=m.win.document,u=D.units.find(u=>u.id===m.unitId);if(!u)return;
 doc.title=unitName(u)+' · '+(METRICS.find(([k])=>k===m.metric)?.[1]||'Graph');
 doc.body.innerHTML='<div class="mini-heading"><b>'+esc(unitName(u))+'</b><span>'+esc(u.side)+'</span></div><div class="mini-controls"><label>Show<select id="mini-scope">'+['Allied','Enemy','All'].map(s=>'<option '+(s===m.scope?'selected':'')+'>'+s+'</option>').join('')+'</select></label><label>Unit<select id="mini-unit">'+miniUnitOptions(m)+'</select></label><label>Graph<select id="mini-metric">'+metricOptions(m.metric,m.unitId,m.id)+'</select></label></div>'+chartMarkup('mini-chart',metricTitle(m.metric))+'<p id="mini-note" class="graph-note muted"></p>';
 doc.getElementById('mini-unit').onchange=e=>changeMiniUnit(m,e.target.value);
 doc.getElementById('mini-metric').onchange=e=>{if(!chartOccupied(m.unitId,e.target.value,m.id)){m.metric=e.target.value;refreshMinis()}};
 doc.getElementById('mini-scope').onchange=e=>{let next=e.target.value,us=D.units.filter(u=>next==='All'||u.side===next);if(!us.length){miniMessage('No units recorded for this side.');renderMini(m);return}m.scope=next;changeMiniUnit(m,us.some(u=>u.id===m.unitId)?m.unitId:us[0].id)};
 drawMini(m);
}
function changeMiniUnit(m,id){if(!D.units.some(u=>u.id===id))return;m.unitId=id;refreshMinis()}
function renderMiniTray(){
 $('mini-tray').hidden=!minis.length;$('mini-tray').innerHTML=minis.map(m=>'<span class="mini-entry"><button data-mini-focus="'+m.id+'">'+esc(unitName(D.units.find(u=>u.id===m.unitId)))+' · '+esc(METRICS.find(([k])=>k===m.metric)?.[1])+'</button><button data-mini-close="'+m.id+'" aria-label="Close mini graph">×</button></span>').join('');
}
function refreshMinis(){for(let m of [...minis])if(!m.win.closed)renderMini(m);renderMiniTray()}
function syncMiniViews(){renderPanels();refreshMinis()}
function removeMini(m){let i=minis.indexOf(m);if(i<0)return;dropTimeGraphs(m.win.document);minis.splice(i,1);if(!minis.length&&miniWatcher!==null){window.clearInterval(miniWatcher);miniWatcher=null}syncMiniViews();miniMessage(minis.length+' / 4 mini windows open')}
function miniForSlot(index){return minis.find(m=>m.originIndex===index&&!m.win.closed)}
function reapClosedMinis(){for(let m of [...minis])if(m.win.closed)removeMini(m)}
function openMini(index){
 const u=D.units.find(u=>u.id===selected);if(!u||!Number.isInteger(index)||index<0||index>3)return;
 reapClosedMinis();let existing=miniForSlot(index);if(existing){existing.win.focus();return}
 if(minis.length>=4){miniMessage('Four mini windows are already open. Close one to open another.');return}
 const win=window.open('',MINI_PREFIX+'-'+(++miniCounter),'popup,width=760,height=470');if(!win){miniMessage('The browser blocked the mini window. Allow pop-ups for this report and try again.');return}
 const m={id:'mini-'+miniCounter,unitId:selected,metric:graphMetrics[index],scope:side,originIndex:index,win};minis.push(m);if(miniWatcher===null&&window.setInterval)miniWatcher=window.setInterval(reapClosedMinis,500);miniDocument(m,win);syncMiniViews();miniMessage(minis.length+' / 4 mini windows open');
}
$('mini-tray').onclick=e=>{let b=e.target.closest('[data-mini-focus],[data-mini-close]');if(!b)return;let id=b.dataset.miniFocus||b.dataset.miniClose,m=minis.find(m=>m.id===id);if(!m)return;if(b.dataset.miniFocus)m.win.focus();else{m.win.close();removeMini(m)}};
window.addEventListener('pagehide',()=>{for(let m of [...minis])m.win.close()});
function metricOptions(chosen,unitId=selected,owner=null){return METRICS.map(([key,name])=>{let used=chartOccupied(unitId,key,owner);return '<option value="'+key+'" '+(key===chosen?'selected ':'')+(used?'disabled ':'')+'>'+esc(name)+(used?' · already shown':'')+'</option>'}).join('')}
$('unit-panels').onchange=e=>{let i=Number(e.target.dataset.graph);if(Number.isInteger(i)&&i>=0&&i<4&&METRICS.some(m=>m[0]===e.target.value)&&!chartOccupied(selected,e.target.value,'main-'+i)){graphMetrics[i]=e.target.value;try{localStorage.setItem(GRAPH_STORAGE,JSON.stringify(graphMetrics))}catch(_){}renderPanels();refreshMinis()}};
$('unit-panels').onclick=e=>{let b=e.target.closest('[data-popout]');if(b)openMini(Number(b.dataset.popout))};
const layout=[8,7,3,1,2,4,5,6].map(i=>({id:'view-'+i,visible:true}));
function armyUnits(a){return D.units.filter(u=>String(u.army)===String(a.last.id)&&u.side===a.last.side)}
function armyRaceNames(a){
 const units=armyUnits(a),named=units.filter(u=>A.unit_info?.[u.id]?.culture),lords=named.filter(u=>A.unit_info[u.id].caste==='lord');
 return [...new Set((lords.length?lords:named).map(u=>A.race_names?.names?.[A.unit_info[u.id].culture]).filter(Boolean))].sort();
}
function armyLabel(a,index){
 const own=a.last.side==='Allied'&&armyUnits(a).some(u=>u.first?.controlled===true||u.last?.controlled===true),base=own?'Own army':a.last.side==='Allied'?'Allied army':'Enemy army',races=armyRaceNames(a);
 const showRace=!own&&(a.last.side==='Allied'||D.armies.filter(v=>v.last.side==='Enemy').length>1);
 let name=base+(showRace&&races.length?' ('+races.join(', ')+')':'');
 if(!races.length&&D.armies.filter(v=>v.last.side===a.last.side).length>1&&!own)name+=' '+(D.armies.slice(0,index+1).filter(v=>v.last.side===a.last.side).length);
 return name;
}
function metricTitle(metric){return METRICS.find(([key])=>key===metric)?.[1]||'Graph'}
function panelTitle(p){return GRAPH_IDS.includes(p.id)?metricTitle(graphMetrics[GRAPH_IDS.indexOf(p.id)]):p.id==='view-3'?'Movement & occupancy':p.id==='view-6'?'Winds vs reserves':p.id==='view-8'?'Statline & buffs/debuffs':'Time spent doing each activity'}
const EXPLANATIONS_STORAGE='wh3-report-hide-graph-explanations-v1';
let hideGraphExplanations=false;try{hideGraphExplanations=localStorage.getItem(EXPLANATIONS_STORAGE)==='true'}catch(_){}
function syncExplanationVisibility(){
 $('hide-graph-explanations').checked=hideGraphExplanations;
 const u=D.units.find(u=>u.id===selected);
 for(let i=0;i<4;i++){let heading=$('graph-heading-'+i);if(heading)heading.title=hideGraphExplanations?'':metricNote(graphMetrics[i],u);let note=$('graph-note-'+i);if(note){note.textContent=metricNote(graphMetrics[i],u);note.hidden=hideGraphExplanations}}
 for(let [id,tip] of [['movement-heading','All units with recorded positions are shown. Brighter white cells combine both sides. Unit dots are green for allies and red for enemies. Hover the time strip to choose a sample; click to lock or unlock this map only. Hover dots for unit names. Missing intervals and counter resets are excluded.'],['winds-heading','Gold: usable Winds. Blue: reserves. Recharge transfers reserves into usable Winds.'],['activity-heading','Bars join consecutive active samples at recorded battle times. Unknown readings and recording gaps break the bars.'],['effects-heading','Statline shows the nearest recorded unit-card snapshot. Move across the timeline or use the time controls. Effect bars join consecutive detections at recorded battle times, assuming the effect continued between them. Missing or unreadable ticks and recording gaps break the bar. Hover a name or bar for listed effects and configured healing/damage rates at the recorded intensity. Internal effects hidden by the game may not appear.']]){let heading=$(id);if(heading)heading.title=hideGraphExplanations?'':tip}
 for(let mini of minis)if(!mini.win.closed){let node=mini.win.document.getElementById('mini-metric');if(node)node.title=hideGraphExplanations?'':metricNote(mini.metric,D.units.find(u=>u.id===mini.unitId));let note=mini.win.document.getElementById('mini-note');if(note){note.textContent=metricNote(mini.metric,D.units.find(u=>u.id===mini.unitId));note.hidden=hideGraphExplanations}}
}
function setExplanationsHidden(hidden){hideGraphExplanations=!!hidden;try{localStorage.setItem(EXPLANATIONS_STORAGE,String(hideGraphExplanations))}catch(_){}syncExplanationVisibility()}
$('hide-graph-explanations').onchange=e=>setExplanationsHidden(e.target.checked);
$('show-graph-tooltips').checked=tooltipsEnabled;$('show-graph-tooltips').onchange=e=>{tooltipsEnabled=!!e.target.checked;syncTooltipOptions();clearGraphHover()};
function syncTooltipOptions(){
 for(let[id,disabled]of [['show-active-flags',!tooltipsEnabled||simplifiedEffectTooltip],['show-activity-flags',!tooltipsEnabled],['simplified-effects-tooltip',!tooltipsEnabled]]){let box=$(id);if(box)box.disabled=disabled}
}
function scopedUnits(){return D.units.filter(u=>side==='All'||u.side===side)}
function sortedUnits(){return scopedUnits().filter(u=>category!=='ranged'||ammoValue(u,'primary_ammo_initial')>0||ammoValue(u,'secondary_ammo_initial')>0).slice().sort((a,b)=>{let av=isAmmoExpended(sort)?ammoPercent(a,sort):value(a,sort),bv=isAmmoExpended(sort)?ammoPercent(b,sort):value(b,sort);if(av==null&&bv==null)return unitName(a).localeCompare(unitName(b));if(av==null)return 1;if(bv==null)return -1;let delta=typeof av==='string'?av.localeCompare(String(bv)):av-bv;return (ascending?delta:-delta)||unitName(a).localeCompare(unitName(b))})}
function renderTable(){const c=CATEGORIES[category],cols=[['Unit','name',''],...c.columns],us=sortedUnits();
 $('head').innerHTML=cols.map(([label,k,ic])=>'<th scope="col" aria-sort="'+(sort===k?(ascending?'ascending':'descending'):'none')+'"><button data-key="'+k+'" title="'+esc(cellTip(k))+'">'+(ic?icon(ic)+' ':'')+esc(label)+(sort===k?(isAmmoExpended(k)?' · %':'')+(ascending?' ↑':' ↓'):'')+'</button></th>').join('');
 const maxima=Object.fromEntries(cols.map(([_,k])=>[k,Math.max(1,...us.map(u=>typeof value(u,k)==='number'?value(u,k):0))]));
 $('rows').innerHTML=us.map(u=>'<tr class="unit" data-id="'+esc(u.id)+'">'+cols.map(([_,k])=>k==='name'?'<td><div class="unit-cell">'+cardImage(u,true)+'<button class="unit-link" data-id="'+esc(u.id)+'"><b>'+esc(unitName(u))+'</b><small>'+esc(u.side)+(u.last.spawned?' · Summoned':'')+(!u.fresh?' · Last observed '+seconds(u.last_s)+'s':'')+'</small></button></div></td>':'<td class="'+(k==='damage'?'valuebar '+(u.side==='Enemy'?'damage-incoming':'damage-outgoing'):k==='gold_damage'||k==='trade'||isAmmoExpended(k)?'valuebar gold-bar':k===c.sort&&k!=='status'?'valuebar':'')+'" style="--bar:'+Math.max(0,Math.min(100,(isAmmoExpended(k)?ammoPercent(u,k)||0:(value(u,k)||0)/maxima[k]*100)))+'%">'+cellText(u,k)+'</td>').join('')+'</tr>').join('');
 $('category-note').textContent='';$('category-note').hidden=true;
 if(c.workInProgress){$('head').innerHTML='<th>Work in Progress</th>';$('rows').innerHTML=''}
 $('categories').innerHTML=Object.entries(CATEGORIES).map(([key,c])=>'<button data-category="'+key+'" aria-pressed="'+(key===category)+'">'+icon(c.icon)+esc(c.name)+'</button>').join('');
}
function selectCategory(key){if(!CATEGORIES[key])return;category=key;sort=CATEGORIES[key].sort;ascending=false;renderTable()}
$('categories').onclick=e=>{let b=e.target.closest('[data-category]');if(b)selectCategory(b.dataset.category)};
$('head').onclick=e=>{let b=e.target.closest('[data-key]');if(b){if(sort===b.dataset.key)ascending=!ascending;else{sort=b.dataset.key;ascending=sort==='name'||sort==='status'}renderTable()}};
// Opening a unit requires a short click, not a hold or a text-selection drag.
let rowPress=null;
$('rows').onpointerdown=e=>{let row=e.target.closest('tr[data-id]');rowPress=e.button===0&&row?{id:row.dataset.id,start:e.timeStamp,x:e.clientX,y:e.clientY,dragged:false}:null};
$('rows').onpointermove=e=>{if(rowPress&&Math.hypot(e.clientX-rowPress.x,e.clientY-rowPress.y)>5)rowPress.dragged=true};
$('rows').onpointercancel=()=>{rowPress=null};
$('rows').onclick=e=>{let row=e.target.closest('tr[data-id]'),press=rowPress;rowPress=null;if(!row||window.getSelection?.()?.isCollapsed===false)return;if(e.detail!==0&&(!press||press.id!==row.dataset.id||press.dragged||e.timeStamp-press.start>=400))return;selectUnit(row.dataset.id,true)};
$('side').onchange=()=>{side=$('side').value;renderTable();renderUnitPicker();if(!scopedUnits().some(u=>u.id===selected))selectUnit(scopedUnits()[0]?.id)};
function showView(next){view=next;$('main-view').hidden=next!=='main';$('unit-view').hidden=next!=='unit';syncUnitHeader();$('main-tab').setAttribute('aria-pressed',String(next==='main'));$('unit-tab').setAttribute('aria-pressed',String(next==='unit'));document.querySelector('h1').textContent=next==='main'?battleOverviewTitle():'Unit workspace';renderPanels();refreshMinis()}
function syncUnitHeader(){
 if($('report-header'))$('report-header').hidden=view==='unit'&&unitHeaderMinimized;
 $('unit-header').hidden=view!=='unit'||unitHeaderMinimized;
 if($('unit-header-restore'))$('unit-header-restore').hidden=view!=='unit'||!unitHeaderMinimized;
}
function minimizeUnitHeader(minimized){unitHeaderMinimized=minimized;syncUnitHeader();syncHeader();$(minimized?'unit-header-restore':'unit-header-minimize')?.focus?.()}
if($('unit-header-minimize'))$('unit-header-minimize').onclick=()=>minimizeUnitHeader(true);
if($('unit-header-restore'))$('unit-header-restore').onclick=()=>minimizeUnitHeader(false);
$('main-tab').onclick=()=>showView('main');$('unit-tab').onclick=()=>showView('unit');
function renderUnitPicker(){if($('unit-picker-label'))$('unit-picker-label').textContent='Choose unit from '+({All:'all',Allied:'ally',Enemy:'enemy'}[side]||'all');$('unit-select').innerHTML=scopedUnits().map(u=>'<option value="'+esc(u.id)+'">'+esc(unitName(u))+'</option>').join('');$('unit-select').value=selected||''}
$('unit-select').onchange=()=>selectUnit($('unit-select').value);
function metricCard(label,v,key){let tip=key==='healing'?HEALING_CAP_TIP:cellTip(({gold:'gold_damage',hp:'hp_cached'})[key]||key);return '<div class="card"><span class="card-label" title="'+esc(tip)+'">'+icon(key)+esc(label)+'</span><b>'+esc(v)+'</b></div>'}
function selectUnit(id,open=false){selected=id;const u=D.units.find(u=>u.id===selected);renderUnitPicker();if(!u){$('unit-title').textContent='No units in this view';$('unit-portrait').innerHTML='';$('unit-summary').innerHTML='';$('detail').innerHTML='';$('unit-panels').innerHTML='';$('unit-side').textContent='';$('unit-status').textContent='';if(open)showView('unit');return}
 $('unit-title').textContent=unitName(u);$('unit-side').textContent=u.side.toUpperCase()+(u.last.spawned?' · SUMMONED UNIT':'');$('unit-status').textContent=statusName(u)+' · last observed '+seconds(u.last_s)+'s'+(!unitCard(u)?' · unit card not mapped':cardNote(u)?' · provisional unit card':'');$('unit-portrait').innerHTML=cardImage(u);
 $('unit-summary').innerHTML=metricCard('Damage dealt',fmt(known(u,'damage')),'damage')+metricCard('Gold damage dealt',fmt(known(u,'gold_damage')),'gold')+metricCard('HP remaining',hpText(u),'hp')+metricCard('Models remaining',modelsText(u),'models')+metricCard('Healing budget left',u.last.healing_budget_unlimited===true?'Unlimited':fmt(known(u,'healing_budget_remaining_hp')),'healing');
 let changed=A.unit_info?.[u.id]?.artillery&&u.damage_taken_calculation?.reason?.includes('Maximum HP changed');$('unit-data-note').hidden=!changed;$('unit-data-note').textContent=changed?'Artillery HP and model counts changed between equipment and crew. Current values follow the game’s display. Damage taken and healing are unavailable across this change; a higher model count can mean crew are now shown.':'';
 showUnitValue(u);renderPanels();renderRecorded(u);refreshMinis();if(open)showView('unit');else if(view==='unit')drawCharts();
}
const STATE_NAMES={retreating_combined:'Retreating (combined)',firing:'Firing',melee:'Melee combat',idle:'Idle',walking:'Walking',running:'Running',flying:'Airborne',grounded:'Grounded',routing:'Routing',shattered:'Shattered',withdrawing:'Retreating',under_missile:'Under missile fire',out_of_opponents_vision:'Hidden from opponents',idle_after_rally:'Idling time after unit rallies'};
const ACTIVITY_ORDER=['idle','walking','running','melee','firing','retreating_combined','routing','withdrawing','shattered','flying','grounded','under_missile','out_of_opponents_vision','idle_after_rally'];
let showAllActiveFlags=true,showAllActivityFlags=true,simplifiedEffectTooltip=false;
const expandedRetreatUnits=new Set();
function orderedActivityKeys(keys){return [...new Set(keys)].sort((a,b)=>(ACTIVITY_ORDER.indexOf(a)<0?999:ACTIVITY_ORDER.indexOf(a))-(ACTIVITY_ORDER.indexOf(b)<0?999:ACTIVITY_ORDER.indexOf(b)))}
function stateList(u){if(!u)return '';const sub=['routing','withdrawing','shattered'];
 const duration=k=>u.state_observed_seconds?.[k]>0?seconds(u.state_seconds?.[k])+'s <small> / '+seconds(u.state_observed_seconds[k])+'s observed</small>':'Not recorded';
 const row=k=>'<dt>'+esc(STATE_NAMES[k]||k.replaceAll('_',' '))+'</dt><dd>'+duration(k)+'</dd>';
 const main=orderedActivityKeys(Object.keys(u.state_seconds||{})).filter(k=>![...sub,'retreating_combined','idle_after_rally'].includes(k)&&visibleActivity(u,k));
 return '<section class="panel state-panel"><div class="panel-heading effects-heading-row"><h3 id="activity-heading" title="Sampled battle time. Activities can overlap; brief rallies may be missed.">Time spent doing each activity</h3><label class="active-flags-option"><input type="checkbox" id="show-activity-flags" aria-label="Show all active activity flags" '+(showAllActivityFlags?'checked':'')+'>Show all active flags</label></div><button id="activity-retreat-toggle" class="retreat-toggle" aria-expanded="false">Expand retreating states</button><div class="activity-scroll">'+chartMarkup('activities','Recorded activities by battle time')+'</div><details class="activity-totals"><summary>Activity totals</summary><dl>'+main.map(row).join('')+'</dl><details class="activity-group"><summary title="Time in any retreat, routing or shattered state. Overlapping states count only once.">Retreating time <span>'+duration('retreating_combined')+'</span></summary><dl>'+sub.map(row).join('')+'</dl></details><dl class="activity-counts">'+row('idle_after_rally')+'<dt>Number of rallies</dt><dd>'+fmt(u.rallies_observed)+'</dd></dl></details></section>'
}

function renderPanels(){clearGraphHover();const u=D.units.find(u=>u.id===selected),visible=layout;
 $('unit-panels').innerHTML=visible.map(p=>{if(GRAPH_IDS.includes(p.id)){let i=GRAPH_IDS.indexOf(p.id),metric=graphMetrics[i];return '<section class="panel graph-panel"><div class="panel-heading" id="graph-heading-'+i+'"><h3>'+panelTitle(p)+'</h3><button class="graph-plus" data-popout="'+i+'" '+(minis.length>=4||miniForSlot(i)?'disabled':'')+' title="Open this graph in a mini window (maximum four)" aria-label="Pop out '+panelTitle(p)+'">+</button><select aria-label="Metric for '+panelTitle(p)+'" data-graph="'+i+'">'+metricOptions(metric,selected,'main-'+i)+'</select></div>'+chartMarkup('graph-'+i,panelTitle(p))+'<p id="graph-note-'+i+'" class="graph-note muted"></p></section>'}return p.id==='view-3'?movementMarkup():p.id==='view-6'?'<section class="panel winds-panel"><h3 id="winds-heading">Winds vs reserves over time</h3><select id="army"></select><p id="winds-rate" class="muted"></p>'+chartMarkup('winds','Army Winds timeline')+'<p class="legend muted">Gold: usable winds · Blue: winds reserves</p></section>':p.id==='view-8'?effectsMarkup():stateList(u)}).join('');
 if($('army')){$('army').innerHTML=D.armies.map((a,i)=>'<option value="'+i+'">'+esc(armyLabel(a,i))+'</option>').join('');$('army').onchange=drawCharts;let ai=D.armies.findIndex(a=>a.last.side===u?.side&&String(a.last.id)===String(u?.army));if(ai>=0)$('army').value=String(ai)}if(u&&view==='unit')drawCharts();syncExplanationVisibility();syncTooltipOptions();
}
function sameSegment(a,b,position=false){return !!a&&!!b&&a.segment===b.segment&&(!position||a.position_segment===b.position_segment)}
function chartMarkup(id,label,extra=''){return '<div class="chart-with-rails"><div class="interactive-chart"><canvas id="'+id+'" aria-label="'+esc(label)+'"></canvas>'+extra+'<div id="'+id+'-cursor" class="chart-cursor" hidden></div><span id="'+id+'-sample" class="chart-sample" hidden></span><div id="'+id+'-tooltip" class="chart-tooltip" role="tooltip" hidden></div></div></div>'}
function nearestSample(points,time){return points.reduce((nearest,p)=>Number.isFinite(p.t)&&(!nearest||Math.abs(p.t-time)<Math.abs(nearest.t-time))?p:nearest,null)}
function lineAt(points,time,field,u,get=(a,f)=>metricValue(a,f,u)){
 let point=nearestSample(points,time),value=point?get(point,field):null;
 return Number.isFinite(value)?{value,t:point.t}:null;
}
const graphNumber=(v,field)=>fmt(v,field==='elevation'?2:0);
function setup(id,height=210,doc=document){let c=doc.getElementById(id);if(!c)return null;let r=c.getBoundingClientRect(),d=doc.defaultView?.devicePixelRatio||window.devicePixelRatio||1,w=Math.max(260,r.width||600);c.width=w*d;c.height=height*d;let x=c.getContext('2d');x.scale(d,d);return[x,w,height]}
let ELEVATION_MIN=Number.isFinite(D.elevation_min)?D.elevation_min:null;
if(ELEVATION_MIN===null)for(let u of D.units)for(let p of u.history||[]){let y=p.xyz?.[1];if(Number.isFinite(y))ELEVATION_MIN=ELEVATION_MIN===null?y:Math.min(ELEVATION_MIN,y)}
function metricValue(a,f,u){if(f==='hp_cached'&&Number.isFinite(a.resolved_hp))return a.resolved_hp;if(f==='models'&&Number.isFinite(a.resolved_models))return a.resolved_models;if(f==='fatigue_state')return displayFatigueState(a);if(f.startsWith('native:'))return a.damage_by_source?.[f.slice(7)]?.enemy??null;if(f==='elevation')return a.xyz?.[1]??null;if(f==='healing_cap_remaining'){if(Number.isFinite(a.healing_budget_ceiling_hp))return a.healing_budget_ceiling_hp;if(Number.isFinite(a.hp_cached)&&Number.isFinite(a.healing_budget_remaining_hp))return a.hp_cached+a.healing_budget_remaining_hp;let models=u?.last_observed?.models_initial?.value??u?.last.models_initial??u?.first?.models_initial;if(models===1&&Number.isFinite(a.healing_ceiling_fraction_raw)&&a.hp_max_cached>0)return a.healing_ceiling_fraction_raw*a.hp_max_cached;return null}return a[f]??null}
function plotRange(values,field){if(field==='fatigue_state')return [0,6];if(field==='fatigue_points')return [0,D.fatigue_rules?.maximum||Math.max(1,...values)];if(field==='leadership'){let extent=Math.max(1,...values.map(Math.abs));return [-extent,extent]}if(field==='elevation'){let floor=ELEVATION_MIN??Math.min(...values);return [floor,Math.max(floor+1,...values)]}return [Math.min(0,...values),Math.max(1,...values)]}
function plot(id,points,fields,colors,u,doc=document){let s=setup(id,210,doc);if(!s)return;let[c,w,h]=s,p=fields[0]==='fatigue_state'?88:52,ts=points.map(a=>a.t).filter(Number.isFinite),get=(a,f)=>id==='winds'&&a.maximum===0?null:metricValue(a,f,u);
 const empty=message=>{c.fillStyle='#a4b0bf';c.fillText(message,p,35);const canvas=doc.getElementById(id);canvas.onmousemove=canvas.onmouseleave=null;registerTimeGraph(id,doc,time=>{canvas._sharedTime=time;for(let suffix of ['-cursor','-sample','-tooltip']){let el=doc.getElementById(id+suffix);if(el)el.hidden=true}})};
 let vs=fields.flatMap(f=>points.map(a=>get(a,f))).filter(Number.isFinite);if(!ts.length||!vs.length){empty('Not recorded / no valid samples');return}
 if(fields[0]==='fatigue_points'&&!D.fatigue_rules?.maximum){empty('Fatigue maximum / thresholds not recorded');return}
 let t0=Number.isFinite(D.timeline_start_s)?Math.min(D.timeline_start_s,...ts):Math.min(...ts),t1=Math.max(t0+1e-6,D.end_s??0,...ts),[v0,v1]=plotRange(vs,fields[0]);c.strokeStyle='#354456';c.strokeRect(p,14,w-p-12,h-56);c.font='11px Segoe UI';c.fillStyle='#a4b0bf';
 const yOf=v=>h-42-(v-v0)/Math.max(1,v1-v0)*(h-56);
 if(fields[0]==='fatigue_state'){FATIGUE_NAMES.forEach((name,i)=>{let y=yOf(i);c.strokeStyle='#51616e';c.setLineDash([3,4]);c.beginPath();c.moveTo(p,y);c.lineTo(w-12,y);c.stroke();c.setLineDash([]);c.fillText(name,2,y+4)})}else{c.fillText(graphNumber(v1,fields[0]),2,20);c.fillText(graphNumber(v0,fields[0]),2,h-42)}
 c.fillText(seconds(t0)+'s',p,h-8);c.fillText(seconds(t1)+'s',w-65,h-8);
 if(!['fatigue_state','fatigue_points','leadership'].includes(fields[0]))for(let q of [.25,.5,.75]){let v=v0+(v1-v0)*q,y=yOf(v);c.strokeStyle='#435763';c.setLineDash([3,4]);c.beginPath();c.moveTo(p,y);c.lineTo(w-12,y);c.stroke();c.setLineDash([]);c.fillStyle='#a4b0bf';}
 if(fields[0]==='fatigue_points'){let peak=Math.max(u?.fatigue_points_peak||0,...vs);(D.fatigue_rules.thresholds||[]).forEach((threshold,i)=>{if(threshold<=0||threshold>peak)return;let y=yOf(threshold);c.strokeStyle='#658080';c.setLineDash([3,4]);c.beginPath();c.moveTo(p,y);c.lineTo(w-12,y);c.stroke();c.setLineDash([]);c.fillStyle='#b1c3ca';c.fillText(FATIGUE_NAMES[i],p+5,y-3)})}
 if(fields[0]==='leadership'){let zero=yOf(0);c.strokeStyle='#69889a';c.setLineDash([4,4]);c.beginPath();c.moveTo(p,zero);c.lineTo(w-12,zero);c.stroke();c.setLineDash([]);}
 c.save();c.beginPath();c.rect(p,14,w-p-12,h-56);c.clip();
 fields.forEach((f,j)=>{c.strokeStyle=colors[j];c.lineWidth=2;c.beginPath();let previous=null,previousY=null;for(let a of points){let v=get(a,f);if(!Number.isFinite(v)){previous=null;continue}let x=p+(a.t-t0)/Math.max(1e-6,t1-t0)*(w-p-12),y=yOf(v);if(sameSegment(previous,a,f==='elevation')){if(f==='fatigue_state')c.lineTo(x,previousY);c.lineTo(x,y)}else c.moveTo(x,y);previous=a;previousY=y}c.stroke()})
 c.restore();
 const canvas=doc.getElementById(id),tooltip=doc.getElementById(id+'-tooltip'),cursor=doc.getElementById(id+'-cursor');
 const hide=()=>{if(tooltip)tooltip.hidden=true;if(cursor)cursor.hidden=true};hide();
 const point=e=>{let r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*w/r.width,y:(e.clientY-r.top)*h/(r.height||h)}};
 const dot=doc.getElementById(id+'-sample');
 const highlight=(time,origin)=>{
  let sample=nearestSample(points,time);if(!sample||!tooltip||!cursor)return;
  canvas._sharedTime=time;canvas._sharedSampleTime=sample.t;
  const x=p+(Math.max(t0,Math.min(t1,time))-t0)/Math.max(1e-6,t1-t0)*(w-p-12);
  cursor.hidden=false;cursor.style.left=x+'px';
  const values=fields.map(f=>({field:f,point:lineAt([sample],sample.t,f,u,get)}));
  if(dot){dot.hidden=!values[0].point;if(values[0].point){dot.style.left=(p+(sample.t-t0)/Math.max(1e-6,t1-t0)*(w-p-12))+'px';dot.style.top=yOf(values[0].point.value)+'px'}}
  tooltip.hidden=false;
  let rows=values.map(({field,point})=>{let name=METRICS.find(([key])=>key===field)?.[1]||(field==='current'?'Usable winds':field==='reserve'?'Winds reserves':field),value=point?(field==='fatigue_state'?FATIGUE_NAMES[Math.round(point.value)]:graphNumber(point.value,field)):'No recorded value';return '<div>'+esc(name)+': <b>'+esc(value)+'</b></div>'}).join('');
  showGraphTooltip(canvas,tooltip,'<b>Time: '+battleTime(time)+'s</b>'+rows);
 };
 registerTimeGraph(id,doc,highlight);
 canvas.onmousemove=e=>{beginGraphHover(canvas,e);let at=point(e);if(at.x<p||at.x>w-12||at.y<14||at.y>h-42){hide();clearGraphHover();return}
  let time=t0+(at.x-p)/(w-p-12)*(t1-t0),sample=nearestSample(points,time);if(!sample)return;
  publishTime(sample.t,canvas);
 };
 canvas.onmouseleave=()=>clearGraphHover();canvas.onclick=e=>rotateGraphTooltip(canvas,e);
 canvas.onwheel=canvas.onmousedown=canvas.onmouseup=canvas.ondblclick=null;

}
const timeColor=f=>{f=Math.max(0,Math.min(1,f));return f<.5?'rgb('+Math.round(56+300*f)+','+Math.round(202+12*f)+','+Math.round(114-80*f)+')':'rgb('+Math.round(206+64*(f-.5))+','+Math.round(208-252*(f-.5))+','+Math.round(74+16*(f-.5))+')'};
const statlineSelection=new WeakMap(),statlineCarryValues=new WeakMap(),statlineRecordings=new WeakMap();
function effectsMarkup(){return '<section class="panel effects-panel"><div class="panel-heading effects-heading-row"><h3 id="effects-heading">Statline & buffs/debuffs</h3><div class="effect-tooltip-options"><label class="active-flags-option" title="Show every active buff/debuff at the hovered sample."><input type="checkbox" id="show-active-flags" aria-label="Show all active buffs and debuffs" '+(showAllActiveFlags?'checked':'')+'>Show all active flags</label><label class="active-flags-option" title="Show recorded stat changes from the initial statline instead of effect names. Excludes HP, models and healing budget."><input type="checkbox" id="simplified-effects-tooltip" aria-label="Simplified buff/debuff tooltip" '+(simplifiedEffectTooltip?'checked':'')+'>Simplified tooltip</label></div></div><p id="effects-summary" class="muted"></p><div class="statline-workspace"><aside class="statline-card" id="statline-panel"><div class="statline-card-heading"><span id="statline-models" aria-label="Models"></span><output id="statline-time" aria-live="polite"></output></div><div id="statline-card"></div><p id="statline-note" class="muted"></p></aside><div class="statline-timeline"><div class="statline-controls"><button id="statline-prev" aria-label="Previous recorded statline">‹</button><input id="statline-scrubber" type="range" aria-label="Statline battle time"><button id="statline-next" aria-label="Next recorded statline">›</button></div><div class="effects-scroll">'+chartMarkup('effects','Statline and buff/debuff observations by battle time','<div id="statline-marker" class="chart-cursor statline-marker" hidden></div>')+'</div></div></div></section>'}
function statlinePoints(u){return (u.statline_timeline?.samples||[]).filter(p=>Number.isFinite(p.t))}
function nearestStatline(points,t){let lo=0,hi=points.length;while(lo<hi){let mid=(lo+hi)>>1;if(points[mid].t<t)lo=mid+1;else hi=mid}let a=points[lo-1],b=points[lo];return !a?b:!b?a:t-a.t<=b.t-t?a:b}
function statlineBaseline(u){
 const recorded=u.statline_timeline?.baseline;
 if(recorded?.values)return recorded;
 const point=statlinePoints(u).find(p=>p.values&&Object.values(p.values).some(Number.isFinite));
 return point?{...point,source:'first_sample'}:null;
}
function statlineChange(value,initial){
 if(!Number.isFinite(value)||!Number.isFinite(initial))return '';
 const displayed=v=>Math.sign(v)*Math.round(Math.abs(v)),delta=displayed(value)-displayed(initial);
 return delta>0?'statline-up':delta<0?'statline-down':'';
}
function statlineBarMarkup(value,initial,maximum){
 const percent=v=>Number.isFinite(v)&&maximum>0?Math.max(0,Math.min(100,v/maximum*100)):0;
 if(!Number.isFinite(initial))return '<span class="statline-bar" aria-hidden="true"><i style="width:'+percent(value)+'%"></i></span>';
 const base=percent(initial),current=percent(value),change=Number.isFinite(value)?current-base:0;
 return '<span class="statline-bar statline-baseline-bar" aria-hidden="true"><span class="statline-bar-track"><i class="statline-base" style="width:'+base+'%"></i>'+(change?'<i class="'+(change>0?'statline-gain':'statline-loss')+'" style="left:'+(change>0?base:current)+'%;width:'+Math.abs(change)+'%"></i>':'')+'</span></span>';
}
function statlineDisplayValues(values){
 const result={...(values||{})};
 result.fire_resistance=Number.isFinite(result.fire_resistance)&&Number.isFinite(result.fire_weakness)?result.fire_resistance-result.fire_weakness:null;
 return result;
}
function statlineHealthState(u,point,atEnd=false){
 const state=atEnd?{...(u.last||{}),...(point?.state||{})}:point?.state||{};
 const terminal=state.terminal_status?{status:state.terminal_status,hp:state.terminal_hp,models:state.terminal_models}:atEnd?u.terminal_result:null;
 const untracked=state.recorded===false||!point?.values||u.fresh===false||state.alive===false||state.left_battlefield===true;
 const summon=(u.first?.spawned===true||u.last?.spawned===true||state.spawned===true);
 if(terminal?.status==='Dead'||atEnd&&summon&&untracked)return {label:'Dead',icon:'kills',dead:true,terminal};
 if(terminal?.status==='Retreated')return {label:'Retreated',icon:'statline:retreat',terminal};
 if(state.shattered===true)return {label:'Shattered',icon:'statline:retreat'};
 if(state.withdrawing===true)return {label:'Retreating',icon:'statline:retreat'};
 if(state.routing===true)return {label:'Routed',icon:'statline:retreat'};
 if(atEnd&&(state.alive===false||state.left_battlefield===true))return {label:'Dead / retreated',icon:'other'};
 if(atEnd&&untracked)return {label:'No longer recorded',icon:'other'};
 return {label:null,icon:'hp'};
}
function statlineRecording(u,points){
 let cached=statlineRecordings.get(u);if(cached)return cached;
 const valid=points.filter(p=>p.values&&Object.values(p.values).some(Number.isFinite));
 cached={valid,last:valid.at(-1)};statlineRecordings.set(u,cached);return cached;
}
function previousStatline(points,t){
 let lo=0,hi=points.length;while(lo<hi){let mid=(lo+hi)>>1;if(points[mid].t<=t)lo=mid+1;else hi=mid}return lo-1;
}
function statlineSnapshot(u,t,points,range){
 const initial=statlineBaseline(u),left=t<=range.t0,right=!left&&t>=range.t1,recording=statlineRecording(u,points);
 let source=left&&initial?initial:right?points.at(-1):nearestStatline(points,t);
 if(!source)return null;
 let point={...source,cursor_t:left?range.t0:right?range.t1:source.t,initial:left&&!!initial,endpoint:right};
 const readable=source.values&&Object.values(source.values).some(Number.isFinite);
 point.stale=!left&&(!readable||source.state?.recorded===false||recording.last&&t>recording.last.t);
 if(point.stale){point.cursor_t=t;point.t=t}
 const index=previousStatline(recording.valid,source.t),previous=recording.valid[index];
 if((point.stale||right)&&previous){
  let cached=statlineCarryValues.get(u);
  if(!cached||cached.index!==index){let values={};
   for(let i=index;i>=0;i--)for(let [key,value] of Object.entries(recording.valid[i].values))if(Number.isFinite(value)&&!Number.isFinite(values[key]))values[key]=value;
   cached={index,values};statlineCarryValues.set(u,cached);
  }
  point.values={...cached.values};point.held=point.stale;point.last_recorded_s=previous.t;
 }
 if(right)point.t=range.t1;
 // Only the unrecorded tail may use the eventual confirmed result. A gap
 // before a later readable sample never inherits a future death or retreat.
 const tail=point.stale&&previous===recording.last;
 const context=point.stale?{...source,values:null,state:{...(previous?.state||{}),...(source.state||{})}}:source;
 point.health_state=statlineHealthState(u,context,right||tail);
 if(point.health_state.dead)point.values={...(point.values||{}),hp:0,models:0};
 return point;
}
function statlineTone(point){
 if(point?.stale||point?.health_state?.dead||point?.health_state?.label==='Retreated')return 'statline-tone-inactive';
 return ['Routed','Retreating','Shattered'].includes(point?.health_state?.label)?'statline-tone-routing':'';
}
function statlineLineColor(u,point){
 if(!point?.values||point.state?.recorded===false||point.state?.alive===false||point.state?.left_battlefield===true)return '#737b82';
 const status=statlineHealthState(u,point);
 if(status.dead||status.label==='Retreated')return '#737b82';
 return ['Routed','Retreating','Shattered'].includes(status.label)?'#e3e7ea':'#c9ae70';
}
function statlineModelsMarkup(u,point){
 const values=point?.values||{},initial=statlineBaseline(u)?.values||{},maximum=values.models_max??initial.models_max??u.initial_models_maximum;
 return icon('models')+'<b><span class="'+statlineChange(values.models,initial.models)+'">'+esc(fmt(values.models))+'</span><small>('+esc(fmt(maximum))+')</small></b>';
}
function statlineCardMarkup(u,point){
 const values=statlineDisplayValues(point?.values),baseline=statlineDisplayValues(statlineBaseline(u)?.values),caste=A.unit_info?.[u.id]?.caste;
 if(Number.isFinite(point?.state?.healing_budget_remaining_hp))values.healing_budget_remaining_hp=point.state.healing_budget_remaining_hp;
 const health=point?.health_state||statlineHealthState(u,point);
 const number=(key,suffix='')=>'<span class="'+statlineChange(values[key],baseline[key])+'">'+esc(fmt(values[key])+(Number.isFinite(values[key])?suffix:''))+'</span>';
 const budget='<div class="statline-row statline-budget" data-stat="healing_budget_remaining_hp">'+icon('healing')+'<span class="statline-label">Healing budget remaining</span><b>'+(point?.state?.healing_budget_unlimited===true?'Unlimited':number('healing_budget_remaining_hp'))+'</b></div>';
 return budget+(A.statline?.rows||[]).filter(row=>row.key!=='models').map(row=>{
  const key=row.key,value=health.dead&&key==='hp'?0:values[key],known=Number.isFinite(value),maximum=key==='hp'?values.hp_max:row.caste_max?.[caste]??row.max;
  let percent=known&&maximum>0?Math.max(0,Math.min(100,value/maximum*100)):0;
  if(key==='hp'){
   let text=(health.label?health.label+' · ':'')+fmt(value)+' / '+fmt(values.hp_max);
   return '<div class="statline-row statline-health '+(!known?'statline-unknown':'')+'" data-stat="hp" aria-label="Health: '+esc(text)+'"><span class="statline-bar" aria-hidden="true"><i style="width:'+percent+'%"></i></span><b>'+icon(health.icon)+'<span>'+esc(text)+'</span></b></div>';
  }
  return '<div class="statline-row '+(!known?'statline-unknown':'')+'" data-stat="'+key+'">'+icon('statline:'+key)+'<span class="statline-label">'+esc(row.label)+'</span><b>'+number(key,row.percent?'%':'')+'</b>'+statlineBarMarkup(value,baseline[key],maximum)+'</div>';
 }).join('');
}
function showStatline(u,t,points,range={t0:points[0]?.t??0,t1:points.at(-1)?.t??1}){
 let point=statlineSnapshot(u,t,points,range),card=$('statline-card');if(!card)return point;
 if(card._statlineCursor===point?.cursor_t&&card._statlineUnit===u)return point;
 card._statlineCursor=point?.cursor_t;card._statlineUnit=u;card.innerHTML=statlineCardMarkup(u,point);
 $('statline-panel').className='statline-card '+statlineTone(point);
 $('statline-models').innerHTML=statlineModelsMarkup(u,point);
 $('statline-time').textContent=point?battleTime(point.t)+'s':'Not recorded';
 $('statline-note').textContent=!points.length?'Statline was not recorded in this capture.':!point?.values?'Stats unavailable on this tick.':point.initial?'Initial stat line · '+(point.source==='deployment'?'recorded during deployment':'first available sample'):point.stale&&point.held?'Last recorded values'+(point.last_recorded_s!=null?' · '+battleTime(point.last_recorded_s)+'s':''):'';
 if(point?.health_state?.dead&&point.state?.terminal_status!=='Dead'&&u.terminal_result?.status!=='Dead')$('statline-note').textContent+=' · Summon no longer tracked';
 if(u.statline_timeline?.truncated_from_s!=null)$('statline-note').textContent+=' Recording display limit reached.';
 if(point){statlineSelection.set(u,point.cursor_t);$('statline-scrubber').value=point.cursor_t;$('statline-scrubber').setAttribute('aria-valuetext',battleTime(point.cursor_t)+' battle seconds')}
 $('statline-prev').disabled=!point||point.cursor_t<=range.t0;$('statline-next').disabled=!point||point.cursor_t>=range.t1;
 return point;
}
function effectPlotData(u){
 const timeline=u.effect_timeline, readings=(timeline?.samples||[]).map((p,i)=>({point:p,segment:timeline?.segments?.[i]??0,values:timeline?.values?.[i]||{}})).filter(r=>Number.isFinite(r.point[0])),samples=readings.map(r=>r.point);
 const rows=(timeline?.effects||[]).map(effect=>({...effect,...A.effect_texts?.[effect.key],ticks:[],runs:[],observations:[]}));
 const names=new Map(),labels=new Map(),ordinals=new Map();
 for(let row of rows)names.set(row.name,(names.get(row.name)||0)+1);
 for(let row of rows){row.label=row.name+(names.get(row.name)>1&&row.source_label?' ('+row.source_label+')':'');labels.set(row.label,(labels.get(row.label)||0)+1)}
 for(let row of rows)if(labels.get(row.label)>1){let label=row.label,n=(ordinals.get(label)||0)+1;ordinals.set(label,n);row.label=label+' #'+n}
 let previous=null;
 for(let reading of readings){let[t,active]=reading.point;for(let i of active||[]){let row=rows[i];if(!row)continue;row.ticks.push(t);row.observations.push([t,reading.values[i]||{}]);let last=row.runs.at(-1);if(previous&&previous.segment===reading.segment&&previous.point[1]?.includes(i)&&last&&t>previous.point[0])last[1]=t;else row.runs.push([t,t])}previous=reading}
 return {rows,samples,t0:Number.isFinite(D.timeline_start_s)?D.timeline_start_s:Number.isFinite(D.start_s)?D.start_s:(samples[0]?.[0]??0),t1:Number.isFinite(D.end_s)?D.end_s:(samples.at(-1)?.[0]??1)};
}
function effectTimeX(t,t0,t1,left,width){return left+(t-t0)/Math.max(1e-6,t1-t0)*(width-left-16)}
function nearestEffectSample(samples,t){let lo=0,hi=samples.length;while(lo<hi){let mid=(lo+hi)>>1;if(samples[mid][0]<t)lo=mid+1;else hi=mid}let a=samples[lo-1],b=samples[lo];return !a?b:!b?a:t-a[0]<=b[0]-t?a:b}
function effectRateLines(row,reading={}){
 const health=row.health||{},knownIntensity=Number.isFinite(reading.intensity)&&reading.intensity>=0,knownScale=Number.isFinite(reading.damage_scale)&&reading.damage_scale>=0,intensity=knownIntensity?reading.intensity:1,scale=knownScale?reading.damage_scale:1,lines=[],notes=[];
 if(health.damage>0){
  let base=health.damage*Math.max(1,health.max_entities||1);
  if(health.interval_s>0)base=Math.trunc(Math.fround(Math.fround(base)/Math.fround(health.interval_s)));
  base=Math.trunc(Math.fround(Math.fround(base)*Math.fround(scale)));
  let upper=Math.trunc(Math.fround(Math.fround(base)*Math.fround(intensity))),lower=Math.trunc(Math.fround(upper*.5));
  lines.push('Damage: '+fmt(lower)+'–'+fmt(upper)+' HP/s');
  if(!knownScale)notes.push('Base battle scale; scale was not recorded.');
 }
 for(let[field,label,pool]of [['heal_fraction','Healing','maximum HP'],['barrier_heal_fraction','Barrier healing','maximum barrier']])if(health[field]>0){
  let amount=health[field],duration=health.duration_s,interval=health.interval_s,suffix=' per application';
  if(duration>0){if(interval>0)amount*=Math.floor(duration/interval);amount/=Math.max(duration,1);suffix='/s'}
  else if(duration<0&&interval>0)suffix=interval===1?'/s':' every '+fmt(interval,1)+'s';
  lines.push(label+': +'+fmt(amount*100*intensity,1)+'% '+pool+suffix);
 }
 if(health.resurrect)lines.push('Can resurrect fallen models');
 for(let modifier of row.modifiers||[]){let value=modifier.how==='mult'?(modifier.value-1)*intensity+1:modifier.value*intensity;lines.push(modifier.label+': '+(modifier.how==='mult'?'×':value>0?'+':'')+fmt(value,1)+(modifier.unit||''))}
 if(lines.length){if(!knownIntensity)notes.push('Base intensity; intensity was not recorded.');else if(Math.abs(intensity-1)>1e-6)notes.push('Effect intensity: '+fmt(intensity*100,1)+'%');}
 return {lines,notes};
}
function effectDescription(row,reading={}){
 const rates=effectRateLines(row,reading),lines=[...rates.lines,...(row.details||[]).map(text=>text.replace(/-?\d+\.\d+/g,value=>fmt(Number(value),1)))];
 return (lines.length?'<div class="effect-definitions">'+lines.map(text=>'<div>'+esc(text)+'</div>').join('')+'</div>':'')+rates.notes.map(text=>'<small>'+esc(text)+'</small>').join('');
}
function activeEffectCounts(rows,active){
 const selected=active.map(i=>rows[i]).filter(Boolean),buffs=selected.filter(r=>r.polarity==='positive').length,debuffs=selected.filter(r=>r.polarity==='negative').length,other=selected.length-buffs-debuffs;
 return buffs+' buffs · '+debuffs+' debuffs'+(other?' · '+other+' other':'');
}
function simplifiedEffectContent(u,time){
 const points=statlinePoints(u),range={t0:D.timeline_start_s??D.start_s??points[0]?.t??0,t1:D.end_s??points.at(-1)?.t??1},point=statlineSnapshot(u,time,points,range),values=statlineDisplayValues(point?.values),baseline=statlineDisplayValues(statlineBaseline(u)?.values);
 let comparable=0,unavailable=0,changes=[];
 for(let row of A.statline?.rows||[]){
  const key=row.key;if(['hp','models','healing_budget_remaining_hp'].includes(key))continue;
  if(!Number.isFinite(values[key])||!Number.isFinite(baseline[key])){unavailable++;continue}
  comparable++;const raw=values[key]-baseline[key],delta=Math.sign(raw)*Math.round(Math.abs(raw)*10)/10;
  if(delta)changes.push('<div class="stat-change"><span>'+esc(row.label)+'</span><b class="'+(delta>0?'statline-up':'statline-down')+'">'+(delta>0?'+':'')+esc(fmt(delta,1))+(row.percent?'%':'')+'</b></div>');
 }
 return '<b>Time: '+battleTime(time)+'s</b><small>Changes from initial statline</small>'+(changes.length?changes.join(''):'<div>'+(comparable?'No recorded stat changes.':'Stat changes unavailable.')+'</div>')+(comparable&&unavailable?'<small>Some stats were not recorded.</small>':'')+(point?.held?'<small>Last recorded stats</small>':'');
}
function effectTooltipContent(rows,sample,hovered,all=showAllActiveFlags,u=null){
 const [time,active]=sample,known=Array.isArray(active),on=hovered?known?active.includes(rows.indexOf(hovered)):null:null;
 if(simplifiedEffectTooltip&&u)return simplifiedEffectContent(u,time);
 const status=on===true?'Active':on===false?'Inactive':'Not recorded';
 if(!all&&hovered){let reading=on?nearestEffectSample(hovered.observations,time)?.[1]:{};return '<b>'+esc(hovered.label)+' · '+status+'</b><small>Observed at '+battleTime(time)+'s</small>'+effectDescription(hovered,reading)}
 if(!known)return '<b>Active effects not recorded</b><small>'+battleTime(time)+'s · Unknown / unreadable</small>';
 const selected=active.map(i=>rows[i]).filter(Boolean);
 return '<b>Time: '+battleTime(time)+'s · '+activeEffectCounts(rows,active)+'</b><div class="effect-tooltip-columns">'+(selected.length?selected.map(row=>'<div class="active-effect"><strong>'+esc(row.label)+'</strong>'+effectDescription(row,nearestEffectSample(row.observations,time)?.[1]||{})+'</div>').join(''):'<div>No active buffs or debuffs detected.</div>')+'</div>';
}
function drawEffects(u){
 const {rows,samples,t0,t1}=effectPlotData(u),points=statlinePoints(u),height=Math.max(175,rows.length*30+130),canvas=$('effects');
 if(!canvas)return;const flagBox=$('show-active-flags');if(flagBox){flagBox.checked=showAllActiveFlags;flagBox.onchange=()=>{showAllActiveFlags=flagBox.checked;clearGraphHover()}}canvas.style.height=height+'px';
 syncTooltipOptions();const simplifiedBox=$('simplified-effects-tooltip');if(simplifiedBox){simplifiedBox.checked=simplifiedEffectTooltip;simplifiedBox.onchange=()=>{simplifiedEffectTooltip=simplifiedBox.checked;syncTooltipOptions();clearGraphHover()}}
 let s=setup('effects',height);if(!s)return;let[c,w,h]=s,left=Math.min(240,w*.4),x=t=>effectTimeX(t,t0,t1,left,w);
 let tooltip=$('effects-tooltip'),cursor=$('effects-cursor'),hide=()=>{if(tooltip)tooltip.hidden=true;if(cursor)cursor.hidden=true};hide();canvas.onmousemove=null;canvas.onmouseleave=hide;
 const selectTime=t=>{let point=showStatline(u,t,points,{t0,t1}),marker=$('statline-marker');if(marker){marker.hidden=!point;if(point)marker.style.left=x(Math.max(t0,Math.min(t1,t)))+'px'}return point};
 const pickTime=t=>{let point=selectTime(t);publishTime(point?.cursor_t??t,canvas);return point};
 const move=direction=>{let t=statlineSelection.get(u)??t0,times=[...new Set([t0,...points.map(p=>p.t),t1])].sort((a,b)=>a-b),next=direction<0?times.findLast(v=>v<t):times.find(v=>v>t);if(next!=null)pickTime(next)};
 let scrubber=$('statline-scrubber');if(scrubber){scrubber.min=t0;scrubber.max=Math.max(t0+1e-6,t1);scrubber.step='any';scrubber.disabled=!points.length;scrubber.oninput=e=>pickTime(Number(e.target.value));scrubber.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault?.();if(e.key==='Home')pickTime(t0);else if(e.key==='End')pickTime(t1);else move(e.key==='ArrowLeft'?-1:1)}}
 registerTimeGraph('effects',document,(time,origin)=>{selectTime(time);canvas._sharedTime=time;if(origin!==canvas&&tooltip){let sample=nearestEffectSample(samples,time);if(sample)showGraphTooltip(canvas,tooltip,'<b>Time: '+battleTime(sample[0])+'s</b><span> · '+(Array.isArray(sample[1])?activeEffectCounts(rows,sample[1]):'Effects not recorded')+'</span>')}});
 for(let[id,direction]of [['statline-prev',-1],['statline-next',1]])if($(id))$(id).onclick=()=>move(direction);
 selectTime(sharedTime??statlineSelection.get(u)??points.find(p=>p.t>(statlineBaseline(u)?.t??-Infinity))?.t??points[0]?.t??t0);
 const readable=samples.filter(p=>Array.isArray(p[1])).length;
 $('effects-summary').textContent=!samples.length?'Effects were not recorded in this capture.':!readable?'No readable effect observations.':rows.length?rows.length+' effects · '+readable.toLocaleString()+' recorded ticks':'No buffs or debuffs detected on the readable ticks.';
 if(u.effect_timeline?.truncated_from_s!=null)$('effects-summary').textContent+=' Timeline limit reached at '+seconds(u.effect_timeline.truncated_from_s)+'s; later ticks remain in the capture.';
 c.font='12px Segoe UI';
 for(let q=0;q<=4;q++){let t=t0+(t1-t0)*q/4,px=x(t);c.strokeStyle='#354456';c.lineWidth=1;c.beginPath();c.moveTo(px,16);c.lineTo(px,h-45);c.stroke();c.fillStyle='#a4b0bf';c.fillText(battleTime(t)+'s',Math.min(px,w-55),h-18)}
 c.fillStyle='#e4cd94';c.fillText('Statline',0,36);let previousStat=null;
 for(let point of points){let px=x(point.t);if(previousStat&&point.segment===previousStat.segment){c.strokeStyle=statlineLineColor(u,previousStat);c.lineWidth=2;c.beginPath();c.moveTo(x(previousStat.t),32);c.lineTo(px,32);c.stroke()}c.fillStyle=statlineLineColor(u,point);c.fillRect(px-1,29,2,6);previousStat=point}
 rows.forEach((row,i)=>{let y=62+i*30,color=row.polarity==='positive'?'#78d698':row.polarity==='negative'?'#f08080':'#d9bd78';c.fillStyle='#dce5ec';let label=(row.key==='retreating_combined'?'▸ ':['routing','withdrawing','shattered'].includes(row.key)?'  ':'')+row.label;while(label.length>3&&c.measureText(label).width>left-15)label=label.slice(0,-2)+'…';c.fillText(label,0,y+4);c.strokeStyle='#293642';c.lineWidth=1;c.beginPath();c.moveTo(left,y);c.lineTo(w-16,y);c.stroke();c.fillStyle=color;for(let[start,end]of row.runs)c.fillRect(x(start)-1.5,y-5,Math.max(3,x(end)-x(start)+3),10)});
 let readY=h-55;c.fillStyle='#a4b0bf';c.fillText('Readings',0,readY+4);for(let[t,active]of samples){c.fillStyle=active===null?'#7b6c69':'#6d8190';c.fillRect(x(t)-.5,readY-2,1,4)}
 canvas.onmousemove=e=>{
  beginGraphHover(canvas,e);let r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*w/r.width,py=(e.clientY-r.top)*h/(r.height||h);
  if(px<0||px>w||py<16||py>h-40){hide();return}
  let i=Math.round((py-62)/30),row=rows[i],time=t0+(px-left)/(w-left-16)*Math.max(1e-6,t1-t0),sample=nearestEffectSample(samples,time);
  if(px>=left)pickTime(px>=w-18?t1:px<=left+2?t0:time);else if(py<47)pickTime(t0);
  if(py<47&&!showAllActiveFlags&&!simplifiedEffectTooltip){hide();return}
  if(!sample||!tooltip||!cursor||(!row&&px<left)){hide();return}
  if(px<left&&sharedTime!==null)sample=nearestEffectSample(samples,sharedTime)||sample;
  let interval=row?.runs.find(([start,end])=>start<time&&time<end),labelHover=px<left;
  tooltip.hidden=false;cursor.hidden=labelHover;cursor.style.left=x(sample[0])+'px';
  showGraphTooltip(canvas,tooltip,effectTooltipContent(rows,sample,row,showAllActiveFlags,u));
 };
 canvas.onmouseleave=()=>{hide();clearGraphHover()};canvas.onclick=e=>rotateGraphTooltip(canvas,e);
 canvas.onwheel=e=>{if(!tooltip?.hidden&&tooltip?.className?.includes('effects-all-tooltip')&&tooltip.scrollHeight>tooltip.clientHeight){e.preventDefault?.();tooltip.scrollTop+=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?tooltip.clientHeight:1)}};
}
// Keep occupancy time and visit intervals for shading and hover details.
function occupancy(history,xy,cellSize=28){let cells=new Map();history.forEach((a,i)=>{let b=history[i+1];if(!a.xyz?.every(Number.isFinite)||!b?.xyz?.every(Number.isFinite)||!sameSegment(a,b,true)||b.t<=a.t)return;let[x,y]=xy(a),cx=Math.floor(x/cellSize),cy=Math.floor(y/cellSize),key=cx+','+cy;if(!cells.has(key))cells.set(key,{x:(cx+.5)*cellSize,y:(cy+.5)*cellSize,seconds:0,visits:[]});let cell=cells.get(key);cell.seconds+=b.t-a.t;cell.visits.push({start:a.t,end:b.t})});return cells}
function battleMovementBounds(){
 let b=D.movement_bounds;if(b&&['xmin','xmax','zmin','zmax'].every(k=>Number.isFinite(b[k]))&&b.xmin<=b.xmax&&b.zmin<=b.zmax)return {...b};
 b=null;for(let u of D.units)for(let p of u.history||[]){if(p.xyz?.length!==3||!p.xyz.every(Number.isFinite))continue;let[x,,z]=p.xyz;if(!b)b={xmin:x,xmax:x,zmin:z,zmax:z};else{b.xmin=Math.min(b.xmin,x);b.xmax=Math.max(b.xmax,x);b.zmin=Math.min(b.zmin,z);b.zmax=Math.max(b.zmax,z)}}return b;
}
const MOVEMENT_BOUNDS=battleMovementBounds();
const MOVEMENT_MEASURES=[['occupancy','Occupancy',null,'seconds'],['damage','Damage dealt','damage','HP'],['gold_damage','Gold damage dealt','gold_damage','gold'],['kills','Kills','kills','kills'],['damage_taken_estimate','Damage taken','damage_taken_estimate','HP'],['healing_received_estimate','Healing received','healing_received_estimate','HP']];
const movementSettings=new Map();
let movementResize=null;
const MOVEMENT_CELL_SIZES=[50,100,200];
function movementState(u){if(!movementSettings.has('all'))movementSettings.set('all',{metric:'occupancy',track:'All',cellSize:100,locked:false,time:null,zoom:1,panX:0,panY:0});return movementSettings.get('all')}
function movementHistory(u){return u.spatial_timeline?.samples||u.history||[]}
const INITIAL_SKIP=new Set(['the','a','an','of','and','or','in','on','at','to','for','from','with','by']);
function movementInitials(name){let text='',depth=0;for(const character of String(name)){if(character==='(')depth++;else if(character===')')depth=Math.max(0,depth-1);else if(!depth)text+=character}return (text.match(/[\p{L}\p{N}]+/gu)||[]).filter(word=>!INITIAL_SKIP.has(word.toLowerCase())&&!/^\d+$/.test(word)).map(word=>Array.from(word)[0].toUpperCase()).join('')}
function movementDotSize(zoom){return 14+4*Math.log2(Math.max(1,Math.min(8,zoom||1)))}
function movementDotAppearance(unit,time){
 const activity=nearestStatline(unit.activity_timeline?.samples||[],time),statline=nearestStatline(unit.statline_timeline?.samples||[],time);
 const flags=activity&&time>=unit.activity_timeline.samples[0].t?(activity.values||{}):statline&&time>=unit.statline_timeline.samples[0].t?(statline.state||{}):(time>=unit.last_s?unit.last:{}),shattered=flags?.shattered===true,routing=flags?.routing===true;
 const color=shattered?(unit.side==='Allied'?'#91b8a0':unit.side==='Enemy'?'#bb8c91':'#aaaaaa'):routing?(unit.side==='Allied'?'#d9f6e3':unit.side==='Enemy'?'#ffe1df':'#eeeeee'):(unit.side==='Allied'?'#78d698':unit.side==='Enemy'?'#f08080':'#ffffff');
 return {color,status:shattered?'shattered':routing?'routing':'normal'};
}
function movementLabelVisible(dot,dots,diameter,width,height,textWidth){return !!dot.initials}
function selectMovementUnit(id){
 const unit=D.units.find(u=>u.id===id);if(!unit)return false;
 if(side!=='All'&&side!==unit.side){side=unit.side;$('side').value=side;renderTable()}
 selectUnit(id);return true;
}
function movementUnits(u){return D.units}
function movementSquareUnits(units,track,unitId=selected){return track==='Selected'?units.filter(unit=>unit.id===unitId):track==='Allied'||track==='Enemy'?units.filter(unit=>unit.side===track):units}
function movementSquareText(metric,amount){
 const suffix={damage:'damage dealt',gold_damage:'gold damage dealt',kills:'models killed',damage_taken_estimate:'damage taken',healing_received_estimate:'HP healed'};
 return metric==='occupancy'?fmt(amount,1)+' seconds occupied in this square':fmt(amount)+' '+(suffix[metric]||metric)+' in this square';
}
function movementMarkup(){return '<section class="panel movement-panel"><div class="panel-heading"><h3 id="movement-heading">'+icon('movement')+' Movement and <select id="movement-measure" aria-label="Movement map measure">'+MOVEMENT_MEASURES.map(([key,label])=>'<option value="'+key+'">'+label+'</option>').join('')+'</select></h3><div class="movement-grid-size"><label for="movement-cell-size">Square size <output id="movement-cell-label"></output></label><input id="movement-cell-size" type="range" min="0" max="2" step="1" value="1" aria-label="Heatmap square size"><div class="movement-grid-ticks"><span>50 units</span><span>100 units</span><span>200 units</span></div></div><div class="movement-zoom"><button id="movement-zoom-out" aria-label="Zoom out map">−</button><output id="movement-zoom-level" aria-live="polite">100%</output><button id="movement-zoom-in" aria-label="Zoom in map">+</button><button id="movement-zoom-reset" aria-label="Fit entire movement map">Fit</button></div></div><p id="movement-units" class="muted"></p><div class="movement-time">'+chartMarkup('movement-time','All-unit map sample selector; click to lock or unlock')+'</div><p id="movement-lock" role="status" class="muted"></p><div class="movement-map-shell"><div id="movement-map-frame" class="interactive-chart movement-map" aria-label="Resizable movement map"><canvas id="movement" aria-label="All units and combined spatial gains"></canvas><div id="movement-positions" class="movement-positions"></div></div></div><div id="movement-resize-handle" class="movement-resize-handle" role="separator" tabindex="0" aria-orientation="horizontal" aria-label="Movement map height" aria-valuemin="240" aria-valuenow="360" title="Drag to adjust map height"></div><p class="muted movement-resize-hint">Drag the bottom edge to adjust the map height.</p><div class="movement-square-controls"><p id="movement-scale" class="muted"></p><label>Squares tracks stats of: <select id="movement-square-track" aria-label="Squares tracks stats of"><option value="All">all</option><option value="Allied">ally</option><option value="Enemy">enemy</option><option value="Selected">selected unit</option></select></label></div><p id="movement-note" class="muted"></p><p id="movement-tooltip" class="muted movement-tooltip" hidden></p></section>'}
function movementControls(u){
 const state=movementState(u),units=movementUnits(u);
 $('movement-square-track').value=state.track||'All';
 $('movement-square-track').onchange=e=>{if(['All','Allied','Enemy','Selected'].includes(e.target.value)){state.track=e.target.value;drawMovement(u)}};
 if(!MOVEMENT_CELL_SIZES.includes(state.cellSize))state.cellSize=100;
 $('movement-cell-size').value=MOVEMENT_CELL_SIZES.indexOf(state.cellSize);
 $('movement-cell-label').textContent=state.cellSize+' × '+state.cellSize+' units';
 $('movement-cell-size').setAttribute('aria-valuetext',state.cellSize+' game units');
 $('movement-cell-size').oninput=e=>{const size=MOVEMENT_CELL_SIZES[Number(e.target.value)];if(size){state.cellSize=size;drawMovement(u)}};
 $('movement-measure').value=state.metric;
 $('movement-measure').onchange=e=>{if(MOVEMENT_MEASURES.some(m=>m[0]===e.target.value)){state.metric=e.target.value;drawMovement(u)}};
 $('movement-units').textContent=units.length+' unit dots · green: Allied · red: Enemy · pale side-colour fill: routing · grey side-colour fill: shattered · click a dot to select';
 return {state,units};
}
function spatialGain(a,b,metric){
 if(metric==='occupancy')return b.t-a.t;
 const av=a[metric],bv=b[metric];return Number.isFinite(av)&&Number.isFinite(bv)&&bv>=av?bv-av:null;
}
const hasPosition=p=>p?.xyz?.length===3&&p.xyz.every(Number.isFinite);
function spatialCells(units,xy,metric='occupancy',cellSize=28){
 const cells=new Map();let comparable=0;
 for(let u of units){let history=movementHistory(u);
  for(let i=1;i<history.length;i++){let a=history[i-1],b=history[i];
   if(!hasPosition(a)||!hasPosition(b)||!sameSegment(a,b,true)||!(b.t>a.t))continue;
   let amount=spatialGain(a,b,metric);if(amount===null)continue;comparable++;
   const at=metric==='occupancy'?a:b,[x,y]=xy(at),cx=Math.floor(x/cellSize),cy=Math.floor(y/cellSize),key=cx+','+cy;
   if(!cells.has(key))cells.set(key,{x:(cx+.5)*cellSize,y:(cy+.5)*cellSize,amount:0,bySide:{},visits:[]});
   const cell=cells.get(key);cell.amount+=amount;cell.bySide[u.side]=(cell.bySide[u.side]||0)+amount;
   cell.visits.push({start:a.t,end:b.t,t:at.t,amount,unitId:u.id});
  }
 }
 return {cells,comparable};
}
function movementViewPoint(point,state,w,h){return [(point[0]-w/2)*(state.zoom||1)+w/2+(state.panX||0),(point[1]-h/2)*(state.zoom||1)+h/2+(state.panY||0)]}
function zoomMovement(state,factor,w,h,x=w/2,y=h/2){
 const old=state.zoom||1,next=Math.max(1,Math.min(8,old*factor));
 state.panX=x-w/2-(x-w/2-(state.panX||0))*next/old;
 state.panY=y-h/2-(y-h/2-(state.panY||0))*next/old;state.zoom=next;
}
function bindMovementHeightResize(u,frame){
 const handle=$('movement-resize-handle');if(!handle||handle._movementFrame===frame)return;
 handle._movementFrame=frame;let drag=null;
 const resize=height=>{movementState(u).frameHeight=Math.max(240,Math.round(height));clearGraphHover();drawMovement(u)};
 handle.onpointerdown=e=>{
  if(e.button!==0||drag)return;e.preventDefault?.();
  drag={id:e.pointerId,y:e.clientY,height:movementState(u).frameHeight||360};
  handle.setPointerCapture?.(e.pointerId);
 };
 handle.onpointermove=e=>{if(drag&&e.pointerId===drag.id){e.preventDefault?.();resize(drag.height+e.clientY-drag.y)}};
 const finish=e=>{if(!drag||e.pointerId!==drag.id)return;drag=null;if(handle.hasPointerCapture?.(e.pointerId))handle.releasePointerCapture(e.pointerId)};
 handle.onpointerup=finish;handle.onpointercancel=finish;handle.onlostpointercapture=finish;
 handle.onkeydown=e=>{if(!['ArrowUp','ArrowDown','Home'].includes(e.key))return;e.preventDefault?.();resize(e.key==='Home'?240:(movementState(u).frameHeight||360)+(e.key==='ArrowDown'?40:-40))};
}
function drawMovement(u){
 const frame=$('movement-map-frame'),sizeState=movementState(u),canvasSize=$('movement');
 const mapHeight=Math.max(240,sizeState.frameHeight||360);
 if(frame){frame.style.height=mapHeight+'px';frame.style.width='100%';bindMovementHeightResize(u,frame)}
 if($('movement-resize-handle'))$('movement-resize-handle').setAttribute('aria-valuenow',String(mapHeight));
 if(canvasSize)canvasSize.style.height=mapHeight+'px';
 if(frame&&typeof ResizeObserver==='function'&&movementResize?.frame!==frame){
  movementResize?.observer.disconnect();let last=frame.getBoundingClientRect();
  const observer=new ResizeObserver(()=>{
   if(!frame.isConnected)return;
   const current=frame.getBoundingClientRect();if(current.width<=0||current.height<=0)return;if(Math.abs(current.width-last.width)<.5&&Math.abs(current.height-last.height)<.5)return;
   last=current;sizeState.frameHeight=Math.max(240,current.height);
   drawMovement(u);
  });movementResize={frame,observer};observer.observe(frame);
 }
 let s=setup('movement',mapHeight);if(!s)return;
 const [c,w,h]=s,{state,units}=movementControls(u),measure=MOVEMENT_MEASURES.find(m=>m[0]===state.metric),bounds=MOVEMENT_BOUNDS;
 const histories=units.map(v=>({unit:v,history:movementHistory(v)})),projected=[];
 const start=D.timeline_start_s??D.start_s??0,end=Math.max(start+1e-6,D.end_s??1);
 if(!bounds){c.fillStyle='#a3afb7';c.fillText('No valid position samples',20,35);$('movement-note').textContent='Position samples were not recorded.';return}
 const {xmin,xmax,zmin,zmax}=bounds,scale=Math.min((w-90)/Math.max(1,xmax-xmin),(h-90)/Math.max(1,zmax-zmin)),ox=(w-(xmax-xmin)*scale)/2,oy=(h-(zmax-zmin)*scale)/2,baseXY=a=>[ox+(a.xyz[0]-xmin)*scale,oy+(a.xyz[2]-zmin)*scale];
 state.zoom=Math.max(1,Math.min(8,state.zoom||1));
 const maxX=Math.max(0,((xmax-xmin)*scale*state.zoom-w)/2+45),maxY=Math.max(0,((zmax-zmin)*scale*state.zoom-h)/2+45);
 state.panX=Math.max(-maxX,Math.min(maxX,state.panX||0));state.panY=Math.max(-maxY,Math.min(maxY,state.panY||0));
 const xy=a=>movementViewPoint(baseXY(a),state,w,h),zoom=state.zoom;
 $('movement-zoom-level').textContent=Math.round(zoom*100)+'%';$('movement-zoom-out').disabled=zoom<=1;$('movement-zoom-in').disabled=zoom>=8;
 $('movement-zoom-out').onclick=()=>{clearGraphHover();zoomMovement(state,1/1.4,w,h);drawMovement(u)};
 $('movement-zoom-in').onclick=()=>{clearGraphHover();zoomMovement(state,1.4,w,h);drawMovement(u)};
 $('movement-zoom-reset').onclick=()=>{clearGraphHover();Object.assign(state,{zoom:1,panX:0,panY:0});drawMovement(u)};
 const cellSize=state.cellSize,{cells,comparable}=spatialCells(movementSquareUnits(units,state.track,u.id),a=>[a.xyz[0],a.xyz[2]],state.metric,cellSize),max=Array.from(cells.values()).reduce((peak,v)=>Math.max(peak,v.amount),1);
 for(let cell of cells.values()){
  if(cell.amount<=0)continue;
  c.fillStyle='rgba(255,255,255,'+(.06+.88*Math.pow(cell.amount/max,.65))+')';
  let[px,py]=xy({xyz:[cell.x-cellSize/2,0,cell.y-cellSize/2]});const edge=cellSize*scale*zoom;c.fillRect(px+.5,py+.5,Math.max(.5,edge-1),Math.max(.5,edge-1));
 }
 const overlay=$('movement-positions'),canvas=$('movement');
 overlay.innerHTML=units.map((v,i)=>'<div id="movement-position-'+i+'" class="movement-position" hidden role="button" tabindex="0" data-movement-unit="'+esc(v.id)+'" aria-label="Select '+esc(unitName(v))+'" title="'+esc(unitName(v))+'"><i><span class="movement-initials"></span></i></div>').join('');
 $('movement-scale').textContent='Brighter white = more of the chosen stat generated in that square';
 const note=$('movement-note');note.textContent=(state.metric==='damage_taken_estimate'||state.metric==='healing_received_estimate'?'Uses the calculated estimate.':'')+(!comparable?' No comparable samples for this measure.':'')+(histories.some(({unit})=>unit.spatial_timeline?.truncated_from_s!=null)?' Spatial display limit reached.':'');note.hidden=!note.textContent;
 let dots=[];
 const times=[...new Set(histories.flatMap(v=>v.history.map(p=>p.t)))].sort((a,b)=>a-b);
 const sampleTime=time=>nearestStatline(times.map(t=>({t})),time)?.t??start;
 const updatePositions=time=>{
  time=sampleTime(time);state.time=time;canvas._sharedTime=time;$('movement-time')._sharedTime=time;dots=[];
  histories.forEach(({unit,history},i)=>{let point=nearestStatline(history,time),marker=$('movement-position-'+i),known=hasPosition(point)&&time>=history[0]?.t&&time<=history.at(-1)?.t;
   if(marker){marker.hidden=!known;if(known){let[x,y]=xy(point);marker.style.left=x+'px';marker.style.top=y+'px';dots.push({x,y,unit,marker,initials:movementInitials(unitName(unit))})}}
  });
  const diameter=movementDotSize(zoom),font=8;
  c.font='700 '+font+'px Segoe UI';
  for(const dot of dots){
   const look=movementDotAppearance(dot.unit,time),marker=dot.marker,label=marker.querySelector?.('.movement-initials');
   marker.style.width=marker.style.height=diameter+'px';marker.style.color=look.color;
   marker.className='movement-position movement-'+look.status;marker.title=unitName(dot.unit)+' · '+dot.unit.side+(look.status==='normal'?'':' · '+look.status);
   if(label){label.textContent=dot.initials;label.hidden=!movementLabelVisible(dot,dots,diameter,w,h,c.measureText(dot.initials).width)}
  }
  $('movement-lock').textContent=(state.locked?'Locked at ':'Previewing ')+battleTime(time)+'s · Click the time strip or map to '+(state.locked?'unlock.':'lock this sample.');
  let cursor=$('movement-time-cursor');if(cursor){cursor.hidden=false;cursor.style.left=effectTimeX(time,start,end,30,$('movement-time').getBoundingClientRect().width)+'px'}
 };
 updatePositions(state.locked?state.time:sharedTime??times[0]??start);
 registerTimeGraph('movement',document,time=>{if(!state.locked)updatePositions(time)});
 const timeline=$('movement-time'),tc=setup('movement-time',56);
 if(tc){let[ctx,tw,th]=tc,left=30,x=t=>effectTimeX(t,start,end,left,tw);timeline.style.height='56px';ctx.font='11px Segoe UI';
  for(let q=0;q<=4;q++){let t=start+(end-start)*q/4,px=x(t);ctx.fillStyle='#a4b0bf';ctx.fillText(battleTime(t)+'s',Math.min(px,tw-45),th-2)}
  ctx.strokeStyle='#657581';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,19);ctx.lineTo(tw-16,19);ctx.stroke();
  ctx.fillStyle='#d8dfe8';for(let time of times)ctx.fillRect(x(time)-.5,10,1,18);
  registerTimeGraph('movement-time',document,time=>{if(!state.locked){timeline._sharedTime=time;updatePositions(time)}});
  timeline.onmousemove=e=>{if(state.locked)return;let r=timeline.getBoundingClientRect(),px=(e.clientX-r.left)*tw/r.width;if(px<left||px>tw-16)return;publishTime(sampleTime(start+(px-left)/(tw-left-16)*(end-start)),timeline)};
  timeline.onclick=()=>{state.locked=!state.locked;updatePositions(state.time)};
  timeline.onmouseleave=()=>{};timeline.tabIndex=0;
  timeline.onkeydown=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault?.();timeline.onclick();return}if(state.locked||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault?.();let at=state.time??start,next=e.key==='Home'?times[0]:e.key==='End'?times.at(-1):e.key==='ArrowLeft'?times.findLast(t=>t<at):times.find(t=>t>at);if(next!=null)publishTime(next,timeline)};
 }
 canvas.onmousemove=e=>{if(state.drag?.moved)return;let r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*w/r.width,y=(e.clientY-r.top)*h/r.height,bx=(x-w/2-state.panX)/zoom+w/2,by=(y-h/2-state.panY)/zoom+h/2,worldX=xmin+(bx-ox)/scale,worldZ=zmin+(by-oy)/scale,cell=cells.get(Math.floor(worldX/cellSize)+','+Math.floor(worldZ/cellSize));
  const names=dots.filter(p=>(p.x-x)**2+(p.y-y)**2<=(movementDotSize(zoom)/2+4)**2).map(p=>unitName(p.unit));
  $('movement-tooltip').hidden=false;$('movement-tooltip').textContent=(names.length?names.join(' · ')+' — ':'')+(comparable?movementSquareText(state.metric,cell?.amount||0):'No recorded '+measure[1].toLowerCase()+' in this square');
 };
 canvas.onmouseleave=()=>{$('movement-tooltip').hidden=true};canvas.onclick=()=>{if(state.suppressClick){state.suppressClick=false;return}state.locked=!state.locked;updatePositions(state.time)};
 overlay.onmousemove=canvas.onmousemove;overlay.onclick=e=>{const dot=e.target?.closest?.('[data-movement-unit]');if(dot){e.stopPropagation?.();selectMovementUnit(dot.getAttribute('data-movement-unit'));return}canvas.onclick(e)};
 overlay.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){const dot=e.target?.closest?.('[data-movement-unit]');if(dot){e.preventDefault?.();selectMovementUnit(dot.getAttribute('data-movement-unit'))}}};
 canvas.onwheel=e=>{e.preventDefault?.();clearGraphHover();const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*w/r.width,y=(e.clientY-r.top)*h/(r.height||h);zoomMovement(state,Math.exp(-e.deltaY*.002),w,h,x,y);drawMovement(u)};
 overlay.onwheel=canvas.onwheel;
 canvas.onpointerdown=e=>{if(e.button!==0||state.zoom<=1)return;state.suppressClick=false;state.drag={x:e.clientX,y:e.clientY,panX:state.panX,panY:state.panY,moved:false};canvas.setPointerCapture?.(e.pointerId)};
 canvas.onpointermove=e=>{let drag=state.drag;if(!drag)return;const r=canvas.getBoundingClientRect(),dx=(e.clientX-drag.x)*w/r.width,dy=(e.clientY-drag.y)*h/(r.height||h);if(!drag.moved&&Math.hypot(dx,dy)<4)return;drag.moved=true;state.panX=drag.panX+dx;state.panY=drag.panY+dy;clearGraphHover();drawMovement(u)};
 const finishDrag=e=>{if(state.drag){state.suppressClick=state.drag.moved;state.drag=null}canvas.releasePointerCapture?.(e.pointerId)};
 canvas.onpointerup=finishDrag;canvas.onpointercancel=finishDrag;canvas.style.cursor=state.zoom>1?'grab':'crosshair';
}
function sourcePanel(u){let sources=known(u,'damage_by_source');if(!sources)return '<section class="panel"><h3>Damage breakdown</h3><p class="muted">Not recorded in this capture.</p></section>';
 const names={ability:'Direct damage',melee_combined:'Melee',missile:'Missiles',other:'Other'};
 let firstAlly=(u.history||[]).find(p=>Object.values(p.damage_by_source||{}).some(r=>r.ally>0)),summons=D.units.filter(s=>s.side===u.side&&s.first.spawned===true),firstSummon=summons.length?Math.min(...summons.map(s=>s.first_s)):null;
 let timing=firstAlly?'<p class="muted">First positive friendly-fire total observed: '+seconds(firstAlly.t)+'s.'+(firstSummon!==null?' Earliest allied summon observed: '+seconds(firstSummon)+'s.':'')+' Timing alone does not establish the victim or cause.</p>':'';
 return '<section class="panel"><h3>'+icon('damage')+' Damage breakdown</h3><div class="table-shell"><table><thead><tr><th title="'+esc(Object.keys(names).map(k=>names[k]+': '+cellTip('source:'+k)).join(' '))+'">Source</th><th title="'+esc(SHARE_TIP)+'">Damage dealt</th><th title="'+esc(cellTip('friendly'))+'">Friendly fire</th><th title="'+esc(SELF_TIP)+'">Self damage</th></tr></thead><tbody>'+Object.entries(names).map(([key,name])=>'<tr><td>'+icon(key==='melee_combined'?'melee':key)+' '+name+'</td>'+['enemy','ally','self'].map(r=>'<td>'+(r==='enemy'?percentDamage(sourceValue(u,key,r),known(u,'damage')):fmt(sourceValue(u,key,r)))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'+timing+'</section>'
}
function activityValue(sample,key){
 if(key!=='retreating_combined'||typeof sample?.values?.[key]==='boolean')return sample?.values?.[key];
 const states=['routing','withdrawing','shattered'].map(k=>sample?.values?.[k]);
 return states.some(v=>v===true)?true:states.every(v=>v===false)?false:null;
}
function activityTooltipContent(sample,row,all=showAllActivityFlags,u=null){
 if(!all){let value=activityValue(sample,row.key);return '<b>'+esc(row.label)+'</b><div>'+battleTime(sample.t)+'s · '+(value===true?'Active':value===false?'Inactive':'Not recorded')+'</div>'}
 if(!sample.values)return '<b>Active flags not recorded</b><div>'+battleTime(sample.t)+'s · Unknown / unreadable</div>';
 const keys=orderedActivityKeys(Object.keys(sample.values)).filter(k=>!['retreating_combined','idle_after_rally'].includes(k)&&(k!=='grounded'||!u||everFlew(u))),active=keys.filter(k=>sample.values[k]===true);
 return '<b>Time: '+battleTime(sample.t)+'s</b>'+(active.length?active.map(k=>'<div>'+esc(STATE_NAMES[k]||k.replaceAll('_',' '))+'</div>').join(''):'<div>No active flags detected.</div>')+(keys.some(k=>typeof sample.values[k]!=='boolean')?'<small>Some flags were not recorded.</small>':'');
}
function activityPlotData(u){
 const samples=(u.activity_timeline?.samples||[]).filter(p=>Number.isFinite(p.t));
 const available=new Set(Object.keys(u.state_seconds||STATE_NAMES));
 if(['routing','withdrawing','shattered'].some(k=>available.has(k)))available.add('retreating_combined');
 const expanded=expandedRetreatUnits.has(u.id),keys=orderedActivityKeys([...available]).filter(k=>visibleActivity(u,k)&&(expanded?k!=='retreating_combined':!['routing','withdrawing','shattered'].includes(k)));
 const rows=keys.map(key=>{let runs=[],previous=null;for(let p of samples){
  if(activityValue(p,key)===true){let last=runs.at(-1);if(activityValue(previous,key)===true&&previous.segment===p.segment&&last&&p.t>previous.t)last[1]=p.t;else runs.push([p.t,p.t])}previous=p;
 }return {key,label:STATE_NAMES[key]||key.replaceAll('_',' '),runs}});
 return {samples,rows};
}
function drawActivities(u){
 const canvas=$('activities');if(!canvas)return;const flagBox=$('show-activity-flags');if(flagBox){flagBox.checked=showAllActivityFlags;flagBox.onchange=()=>{showAllActivityFlags=flagBox.checked;clearGraphHover()}}
 syncTooltipOptions();const {samples,rows}=activityPlotData(u),height=Math.max(175,rows.length*28+90);
 const toggle=$('activity-retreat-toggle'),expanded=expandedRetreatUnits.has(u.id);
 const toggleRetreat=()=>{if(expandedRetreatUnits.has(u.id))expandedRetreatUnits.delete(u.id);else expandedRetreatUnits.add(u.id);drawActivities(u)};
 if(toggle){toggle.textContent=expanded?'Collapse retreating states':'Expand retreating states';toggle.setAttribute('aria-expanded',String(expanded));toggle.onclick=toggleRetreat;toggle.hidden=!rows.some(row=>['retreating_combined','routing','withdrawing','shattered'].includes(row.key))}
 canvas.style.height=height+'px';let s=setup('activities',height);if(!s)return;
 const [c,w,h]=s,left=Math.min(240,w*.4),t0=Number.isFinite(D.timeline_start_s)?D.timeline_start_s:D.start_s??0,t1=D.end_s??samples.at(-1)?.t??1,x=t=>effectTimeX(t,t0,t1,left,w);
 for(let q=0;q<=4;q++){let t=t0+(t1-t0)*q/4,px=x(t);c.strokeStyle='#354456';c.lineWidth=1;c.beginPath();c.moveTo(px,16);c.lineTo(px,h-45);c.stroke();c.fillStyle='#a4b0bf';c.fillText(battleTime(t)+'s',Math.min(px,w-55),h-18)}
 c.font='12px Segoe UI';
 rows.forEach((row,i)=>{let y=32+i*28;c.fillStyle='#dce5ec';let label=row.label;while(label.length>3&&c.measureText(label).width>left-15)label=label.slice(0,-2)+'…';c.fillText(label,0,y+4);c.strokeStyle='#293642';c.lineWidth=1;c.beginPath();c.moveTo(left,y);c.lineTo(w-16,y);c.stroke();c.fillStyle='#78d698';for(let [start,end] of row.runs)c.fillRect(x(start)-1.5,y-5,Math.max(3,x(end)-x(start)+3),10)});
 c.fillStyle='#a4b0bf';c.fillText('Readings',0,h-51);for(let p of samples){c.fillStyle=p.values?'#6d8190':'#7b6c69';c.fillRect(x(p.t)-.5,h-57,1,4)}
 if(!samples.length){c.fillStyle='#a4b0bf';c.fillText('Activity samples were not recorded.',left,32)}
 let tooltip=$('activities-tooltip'),cursor=$('activities-cursor');const hide=()=>{if(tooltip)tooltip.hidden=true;if(cursor)cursor.hidden=true};hide();
 registerTimeGraph('activities',document,(time,origin)=>{if(cursor){cursor.hidden=false;cursor.style.left=x(time)+'px'}canvas._sharedTime=time;if(origin!==canvas&&tooltip){let sample=nearestSample(samples,time);if(sample)showGraphTooltip(canvas,tooltip,activityTooltipContent(sample,{key:'',label:''},true,u))}});
 canvas.onmousemove=e=>{beginGraphHover(canvas,e);let r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*w/r.width,py=(e.clientY-r.top)*h/(r.height||h),row=rows[Math.round((py-32)/28)];
  if(!row||px<left||px>w-16||py<16||py>h-55||!samples.length){hide();return}
  let time=t0+(px-left)/(w-left-16)*Math.max(1e-6,t1-t0),sample=nearestSample(samples,time),value=activityValue(sample,row.key);if(!sample||!tooltip||!cursor)return;publishTime(sample.t,canvas);
  tooltip.hidden=false;cursor.hidden=false;cursor.style.left=x(sample.t)+'px';showGraphTooltip(canvas,tooltip,activityTooltipContent(sample,row,showAllActivityFlags,u));
 };canvas.onmouseleave=()=>{hide();clearGraphHover()};
 canvas.onclick=e=>{let r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*w/r.width,py=(e.clientY-r.top)*h/(r.height||h),row=rows[Math.round((py-32)/28)];if(px<left&&row&&['retreating_combined','routing','withdrawing','shattered'].includes(row.key))toggleRetreat();else rotateGraphTooltip(canvas,e)};
}
function renderRecorded(u){let rows=[['Calculated damage taken',cellText(u,'damage_taken'),'hp'],['Kills',fmt(known(u,'kills')),'kills'],['Initial primary ammo',fmt(ammoValue(u,'primary_ammo_initial')),'ammo'],['Primary ammo expended',fmt(ammoValue(u,'primary_ammo_expended')),'firing'],['Initial secondary ammo',fmt(ammoValue(u,'secondary_ammo_initial')),'ammo:2'],['Secondary ammo expended',fmt(ammoValue(u,'secondary_ammo_expended')),'firing:2'],['Leadership',fmt(known(u,'leadership')),'status'],['Fatigue state',displayFatigueName(u.last),'status'],['Fatigue points',fmt(u.last.fatigue_points),'status'],['Calculated healing received',fmt(u.healing_received_estimate),'healing'],['Last observed status',statusName(u),'status'],['Damage gained while firing*',fmt(u.damage_firing_estimate),'missile'],['Damage gained in other states*',fmt(u.damage_other_state_estimate),'melee'],['Ambiguous damage interval',fmt(u.damage_ambiguous),'damage'],['Observed net HP falls / rises*',fmt(u.observed_hp_drops)+' / '+fmt(u.observed_hp_rises),'hp'],['Healing budget remaining',u.last.healing_budget_unlimited===true?'Unlimited':fmt(known(u,'healing_budget_remaining_hp')),'healing'],['Healing budget / maximum HP',known(u,'healing_budget_remaining_fraction')==null?'Unknown':fmt(known(u,'healing_budget_remaining_fraction')*100,1)+'%','healing'],['HP + remaining healing budget',fmt(known(u,'healing_budget_ceiling_hp')),'hp'],['Displayed healing ceiling',known(u,'healing_ceiling_fraction_raw')==null?'Unknown':fmt(known(u,'healing_ceiling_fraction_raw')*100,1)+'%','healing'],['Observed rallies*',fmt(u.rallies_observed),'status'],...Object.entries(u.state_seconds).filter(([k])=>visibleActivity(u,k)).map(([k,v])=>[k.replaceAll('_',' ')+' time*',u.state_observed_seconds[k]?seconds(v)+'s / '+seconds(u.state_observed_seconds[k])+'s covered':'Unknown',k==='firing'?'missile':k==='melee'?'melee':'status'])];
 $('detail').innerHTML=sourcePanel(u)+'<section class="panel"><h3 title="Sampled estimates; activity times can overlap. Firing-state damage can include spells. Healing allowance is read directly from the game.">Recorded observations</h3><dl>'+rows.map(([a,b,key])=>'<dt>'+icon(key)+' '+esc(a)+'</dt><dd>'+esc(b)+'</dd>').join('')+'</dl></section>';
 let armies=D.armies.map((a,i)=>({a,i})).filter(({a})=>a.last.side===u.side&&String(a.last.id)===String(u.army));if(armies.length&&$('army'))$('army').value=String(armies[0].i);
}
function syncHeader(){let heading=document.querySelector('.report-heading'),height=heading?.hidden?0:heading?.getBoundingClientRect?.()?.height;if(height!=null)document.documentElement?.style?.setProperty?.('--report-header-height',Math.ceil(height)+'px')}
function metricNote(metric,u){
 const notes={
  hp_cached:'Remaining HP across the unit.',
  models:'Remaining models, including any resurrected models.',
  damage:'HP damage dealt to enemies. Excludes barrier absorption.',
  damage_taken_estimate:'Calculated from the change in healing ceiling.',
  healing_received_estimate:'Estimated healing from starting HP, damage taken and current HP.',
  primary_ammo_expended:'Net ammunition spent; replenishment can offset the total.',
  secondary_ammo_expended:'Net secondary ammunition spent; replenishment can offset the total.',
  fatigue_state:'The game’s average fatigue category. Maximum marks the fatigue-points limit.',
  fatigue_points:'Average fatigue points. Dotted lines mark thresholds for individual models.',
  leadership:'Leadership over time. Negative leadership alone does not confirm routing.',
  healing_cap_remaining:'Current HP plus unused healing allowance.',
  healing_budget_remaining_hp:HEALING_CAP_TIP,
  elevation:'Height above the lowest recorded point in this battle; includes terrain and flight.',
  'native:ability':DIRECT_TIP,
  'native:melee':'Ordinary melee damage. Charge and collision have separate graphs.',
  'native:missile':MISSILE_TIP,
  'native:charge':'The game’s charge-damage counter, included in Melee in the main table.',
  'native:melee_collision':'The game’s melee-collision counter, included in Melee in the main table.',
  'native:other':OTHER_TIP
 };
 return notes[metric]||'';
}
function windRechargeSummary(army){
 if(army.recharge_stats)return army.recharge_stats;
 const samples=[];for(let point of army.history||[]){if(samples.at(-1)?.t===point.t)samples[samples.length-1]=point;else samples.push(point)}
 let highest=null,lowest=null,total=0,count=0,weighted=0,covered=0,previous=null;
 for(let point of samples){let rate=point.maximum===0?null:Number.isFinite(point.recharge_per_second)&&point.recharge_per_second>=0?point.recharge_per_second:point.recharge>0?1/point.recharge:null;
  if(rate!==null){highest=highest===null?rate:Math.max(highest,rate);lowest=lowest===null?rate:Math.min(lowest,rate);total+=rate;count++}
  if(rate!==null&&previous?.rate!=null&&sameSegment(previous,point)&&point.t>previous.t){let dt=point.t-previous.t;weighted+=previous.rate*dt;covered+=dt}
  previous={...point,rate};
 }
 return {highest,lowest,average:covered?weighted/covered:count?total/count:null};
}
function windsRechargeText(army){const s=windRechargeSummary(army);return 'Highest recharge: '+fmt(s.highest,3)+' Winds/s · Lowest recharge: '+fmt(s.lowest,3)+' Winds/s · Average recharge: '+fmt(s.average,3)+' Winds/s'}
function drawCharts(){syncHeader();const u=D.units.find(u=>u.id===selected);if(view!=='unit')return;if(u){drawMovement(u);drawEffects(u);drawActivities(u);for(let i=0;i<4;i++){if(!$('graph-'+i))continue;let metric=graphMetrics[i];plot('graph-'+i,u.history,[metric],['#d9bd78'],u);let heading=$('graph-heading-'+i);if(heading)heading.title=hideGraphExplanations?'':metricNote(metric,u)}}if(!$('army'))return;const a=D.armies[Number($('army').value)||0];if(a){plot('winds',a.history,['current','reserve'],['#d9bd78','#76bbdc']);$('winds-rate').textContent=windsRechargeText(a)}}
$('recorded-details').ontoggle=drawCharts;
function battleOverviewTitle(pathname=window.location?.pathname){
 if(window.__WH3_EMBEDDED__)return 'Battle overview: '+(D.report_filename||'Recorded battle');
 let name=pathname?.split('/').pop()||'';try{name=decodeURIComponent(name)}catch(_){}
 name=name.replace(/\.html?$/i,'')||D.report_filename||'Recorded battle';
 return 'Battle overview: '+name;
}
function renderBattleResult(){let outcome=D.battle_result?.outcome,visible=['Victory','Defeat','Draw'].includes(outcome),node=$('battle-result');node.hidden=false;let qualified=D.battle_result?.result_type_confirmed===true&&D.battle_result?.result_type_label?.endsWith(outcome);node.textContent=visible?(qualified?D.battle_result.result_type_label:outcome):'Battle result: unknown';node.className='battle-result'+(outcome==='Victory'?' victory':outcome==='Defeat'?' defeat':!visible?' unknown':'');}
$('subtitle').textContent=seconds(D.time_reference?.battle_origin_known?(D.end_s||0):(D.end_s||0)-(D.start_s||0))+(D.time_reference?.battle_origin_known?' battle seconds · ':' simulation seconds · ')+D.samples+' samples';$('subtitle').title=D.time_reference?.precision||'';
document.title=battleOverviewTitle();
renderBattleResult();
function applyReportAssets(assets){Object.assign(A,assets);D.assets=A;renderTable();selectUnit(selected);syncHeader();refreshMinis()}
renderTable();selectUnit(scopedUnits()[0]?.id);showView('main');window.addEventListener('resize',()=>{syncHeader();drawCharts()});
