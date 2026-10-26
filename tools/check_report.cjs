// Offline interactions and graph math; does not assess browser layout.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(process.argv[2]||path.join(__dirname,'../build/demo-report.html'),'utf8');
const markup=html.split('<script id="data"')[0],payload=html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1],data=JSON.parse(payload),script=html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);const storage=new Map(),operations=[],styles=new Map();
function run(block=false){const nodes={},ids=new Set(['data',...[...markup.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1])]),canvas=new Proxy({},{get:(o,k)=>k in o?o[k]:(...args)=>operations.push({method:k,args})});
 function node(id){if(!ids.has(id)&&!nodes['unit-panels']?.innerHTML.includes('id="'+id+'"'))return null;if(nodes[id])return nodes[id];let value='';return nodes[id]={style:{},textContent:id==='data'?payload:'',innerHTML:'',get value(){return value},set value(v){value=String(v??'')},open:false,hidden:false,children:[],setAttribute(k,v){this[k]=v},getBoundingClientRect:()=>({width:800,height:360,left:0,top:0}),getContext:()=>canvas,appendChild(c){this.children.push(c)}}}
 const windows=[];
 function makeWindow(){const events={},els={},doc={head:{appendChild(){}},body:{innerHTML:''},open(){},write(){},close(){},createElement:()=>({}),getElementById(id){if(!doc.body.innerHTML.includes('id="'+id+'"'))return null;return els[id]??={style:{},value:'',textContent:'',getBoundingClientRect:()=>({width:700}),getContext:()=>canvas}}};let win={document:doc,closed:false,devicePixelRatio:1,addEventListener(k,v){events[k]=v},close(){this.closed=true;events.pagehide?.()},focus(){this.focused=true}};doc.defaultView=win;windows.push(win);return win}
 const fakeWindow={devicePixelRatio:1,addEventListener(){},open:makeWindow};
 const c=vm.createContext({document:{getElementById:node,querySelector:s=>s==='.report-heading'?{getBoundingClientRect:()=>({height:100})}:s==='style'?{textContent:html.match(/<style>([\s\S]*?)<\/style>/)[1]}:nodes.heading??={},createElement:()=>({}),documentElement:{style:{setProperty:(k,v)=>styles.set(k,v)}}},localStorage:{getItem:k=>{if(block)throw Error();return storage.get(k)||null},setItem:(k,v)=>{if(block)throw Error();storage.set(k,v)}},window:fakeWindow,console});vm.runInContext(script,c);return{node,windows,e:s=>vm.runInContext(s,c)}}
const r=run(),n=r.node,e=r.e;

// Main table percentages floor to integers; unit-detail formatting retains precision.
assert.equal(e('cellText({last:{hp_cached:999,hp_max_cached:1000}},"hp_cached")'),'(99%) 999/1,000');
assert.equal(e('hpText({last:{hp_cached:999,hp_max_cached:1000}})'),'(99.9%) 999/1,000');
assert.equal(e('cellText({last:{damage:1000,damage_by_source:{ability:{enemy:129}}}},"source:ability")'),'(12%) 129');
assert.equal(e('cellText({damage_taken_estimate:1999,damage_taken_calculation:{baseline:{maximum_hp:1000}},last:{}},"damage_taken")'),'(199%) 1,999');
assert.equal(e('cellText({id:"floor-test",last:{gold_damage:999,unit_gold_value:1000}},"trade")'),'99%');
assert.equal(e('cellText({last:{}},"hp_cached")'),'(—%) —/—');
assert.equal(e('CATEGORIES.simple.columns.filter(c=>c[1]==="hp_cached").length'),1);
assert.equal(e('CATEGORIES.simple.columns.filter(c=>c[1]==="models").length'),1);
assert.equal(e('CATEGORIES.simple.columns.some(c=>c[1]==="hp_and_models")'),false);
// Releasing on the original row after a hold or selection must not open Unit view.
const rowTarget={closest:()=>({dataset:{id:e('scopedUnits()[0].id')}})};
function rowGesture(duration,{drag=false,selected=false,cancel=false}={}){
 e('showView("main")');
 e('window.getSelection=()=>({isCollapsed:'+!selected+'})');
 n('rows').onpointerdown({target:rowTarget,button:0,timeStamp:100,clientX:10,clientY:10});
 if(drag){n('rows').onpointermove({clientX:40,clientY:10});n('rows').onpointermove({clientX:10,clientY:10})}
 if(cancel)n('rows').onpointercancel();
 n('rows').onclick({target:rowTarget,detail:1,timeStamp:100+duration});
 return e('view');
}
assert.equal(rowGesture(80),'unit');
assert.equal(rowGesture(700),'main');
assert.equal(rowGesture(80,{drag:true}),'main');
assert.equal(rowGesture(80,{selected:true}),'main');
assert.equal(rowGesture(80,{cancel:true}),'main');
e('window.getSelection=()=>({isCollapsed:true})');
n('rows').onclick({target:rowTarget,detail:0});assert.equal(e('view'),'unit');
e('showView("main")');

assert.ok(!markup.includes('id="cards"'));for(const label of ['Collection quality & performance','Unmeasured fields & interpretation','Game icon sources'])assert.ok(!markup.includes(label));assert.ok(!n('subtitle').textContent.includes('PDT'));
assert.equal(e('battleOverviewTitle("/reports/fun%20battle.html")'),'Battle overview: fun battle');
assert.equal(e('battleOverviewTitle("/reports/fun.battle.HTML")'),'Battle overview: fun.battle');
assert.equal(e('battleOverviewTitle("/reports/100%25%20fun.html")'),'Battle overview: 100% fun');
e('window.location={pathname:"/reports/fun%20battle.html"};showView("main")');assert.equal(e('document.querySelector("h1").textContent'),'Battle overview: fun battle');e('delete window.location');
e('globalThis.savedResult=D.battle_result;D.battle_result={outcome:"Victory"};renderBattleResult()');assert.equal(n('battle-result').textContent,'Victory');assert.match(n('battle-result').className,/victory/);
e('D.battle_result={outcome:"Defeat"};renderBattleResult()');assert.equal(n('battle-result').textContent,'Defeat');assert.match(n('battle-result').className,/defeat/);
e('D.battle_result={outcome:"Victory",result_type_label:"Pyrrhic Victory",result_type_confirmed:true};renderBattleResult()');assert.equal(n('battle-result').textContent,'Pyrrhic Victory');assert.match(n('battle-result').className,/victory/);
e('D.battle_result={outcome:"Defeat",result_type_label:"Valiant Defeat",result_type_confirmed:true};renderBattleResult()');assert.equal(n('battle-result').textContent,'Valiant Defeat');assert.match(n('battle-result').className,/defeat/);
e('D.battle_result={outcome:"Defeat",result_type_label:"Decisive Victory",result_type_confirmed:true};renderBattleResult()');assert.equal(n('battle-result').textContent,'Defeat');
e('D.battle_result={outcome:"Victory",result_type_label:"Decisive Victory",result_type_confirmed:false};renderBattleResult()');assert.equal(n('battle-result').textContent,'Victory');
e('D.battle_result=null;renderBattleResult()');assert.equal(n('battle-result').hidden,false);assert.equal(n('battle-result').textContent,'Battle result: unknown');assert.match(n('battle-result').className,/unknown/);assert.match(html,/\.battle-result\.unknown\{color:#fff\}/);e('D.battle_result=savedResult;renderBattleResult()');

assert.equal(e('fmt(null).charCodeAt(0)'),0x2014);
assert.ok(markup.indexOf('id="side"')<markup.indexOf('id="main-view"'));assert.equal((markup.match(/id="side"/g)||[]).length,1);
assert.equal(e('category'),'simple');assert.equal(e('view'),'main');assert.equal(n('unit-view').hidden,true);assert.equal(e('layout.length'),7);
assert.equal((n('unit-panels').innerHTML.match(/class="panel /g)||[]).length,7);assert.ok(!n('unit-panels').innerHTML.includes('placeholder'));
for(let i=0;i<4;i++)assert.ok(n('graph-'+i));assert.equal(e('METRICS.length'),19);assert.match(n('unit-panels').innerHTML,/Idling time after unit rallies/);
assert.ok(!e('METRICS.some(m=>m[0]==="barrier_hp")'));e("selectCategory('barrier')");assert.equal(n('rows').innerHTML,'');assert.match(n('head').innerHTML,/Work in Progress/);e("selectCategory('simple')");
assert.ok(e('!METRICS.some(m=>m[0]==="morale_state"||m[0].includes("ammo_fraction"))'));
assert.ok(e('METRICS.filter(m=>m[0].startsWith("native:")).length===6'));assert.ok(e('METRICS.filter(m=>m[0].startsWith("native:")).every(m=>m[1].startsWith("Damage: "))'));
assert.match(n('rows').innerHTML,/gold-bar/);assert.match(n('rows').innerHTML,/damage-outgoing/);assert.ok(!e('CATEGORIES.status'));
assert.equal(e('sortedUnits()[0].last.damage'),Math.max(...data.units.filter(u=>u.side==='Allied').map(u=>u.last.damage??0)));
n('head').onclick({target:{closest:()=>({dataset:{key:'status'}})}});assert.ok(e('ascending && sortedUnits().every((u,i,a)=>!i||statusRank(a[i-1])<=statusRank(u))'));
e("selectCategory('damage')");assert.match(n('head').innerHTML,/Mortis Engines/);assert.match(n('head').innerHTML,/charge and collision/);assert.match(n('head').innerHTML,/miscast damage/);assert.match(n('head').innerHTML,/Missiles and spells/);assert.match(n('head').innerHTML,/Friendly fire/);
assert.equal(e('CATEGORIES.damage.columns[1][1]'),'gold_damage');assert.equal(e('CATEGORIES.damage.columns[4][1]'),'source:melee_combined');
assert.equal(e('CATEGORIES.damage.columns[2][1]'),'kills');
assert.equal(e('metricValue({primary_ammo_expended:386},"primary_ammo_expended",{})'),386);
assert.equal(e('ammoValue({ammo:{primary:{initial:1080,expended:386}}},"primary_ammo_expended")'),386);
assert.equal(e('ammoValue({ammo:{}},"secondary_ammo_initial")'),null);
assert.match(e('cellTip("primary_ammo_expended")'),/Beginning ammo minus ending ammo only/);
assert.match(e('icon("ammo:2")'),/<sub>2<\/sub>/);
e("selectCategory('ranged')");assert.ok(e('sortedUnits().every(u=>ammoValue(u,"primary_ammo_initial")>0||ammoValue(u,"secondary_ammo_initial")>0)'));assert.equal(e('sortedUnits().length'),e('scopedUnits().filter(u=>ammoValue(u,"primary_ammo_initial")>0||ammoValue(u,"secondary_ammo_initial")>0).length'));
assert.match(n('head').innerHTML,/Initial ammo/);assert.match(n('head').innerHTML,/Secondary ammo expended/);
e("selectCategory('damage')");
assert.match(n('unit-panels').innerHTML,/Retreating time/);assert.match(n('unit-panels').innerHTML,/Number of rallies/);assert.match(n('unit-panels').innerHTML,/Number of landings/);
assert.ok(!n('detail').innerHTML.includes('Sampled travel distance'));
assert.equal(e('statusName({first:{spawned:true},last:{alive:false},terminal_result:{status:"Dead"}})'),"Summon");
assert.equal(e('sourceValue({last:{damage_by_source:{melee:{enemy:10},charge:{enemy:20},melee_collision:{enemy:30}}}},"melee_combined")'),60);
assert.equal(e('cellText({last:{damage:100,damage_by_source:{melee:{ally:25,self:12}}}},"friendly")'),'25');assert.equal(e('cellText({last:{damage:100,damage_by_source:{melee:{ally:25,self:12}}}},"self")'),'12');
assert.equal(e('percentDamage(45000,50000)'),'(90%) 45,000');assert.equal(e('hpText({last:{hp_cached:6000,hp_max_cached:8000}})'),'(75%) 6,000/8,000');
assert.ok(e('CATEGORIES.gold.columns.length===2&&CATEGORIES.gold.columns[1][1]==="trade"'));
assert.equal(e('tradePercent({id:"test",name:"test",last:{gold_damage:3000,unit_gold_value:1000}})'),300);
assert.equal(e('cellText({id:"test",name:"test",last:{gold_damage:3000,unit_gold_value:1000}},"trade")'),'300%');assert.equal(e('tradePercent({id:"test",name:"test",last:{gold_damage:3000,unit_gold_value:0}})'),null);
e('selectUnit(scopedUnits()[0].id,true)');assert.equal(e('view'),'unit');assert.equal(n('unit-title').textContent,e('unitName(scopedUnits()[0])'));assert.equal(styles.get('--report-header-height'),'100px');
n('unit-value').value='1000';n('unit-value').onchange();assert.equal(e('unitWorth(scopedUnits()[0]).value'),1000);
assert.equal(e('cellText({ammo:{primary:{initial:1080,expended:390}}},"primary_ammo_expended")'),'(36%) 390');
assert.equal(e('ammoPercent({ammo:{primary:{initial:0,expended:0}}},"primary_ammo_expended")'),null);
e('globalThis.savedUnits=D.units;D.units=[{id:"sort-A",name:"A",side:"Allied",last:{},ammo:{primary:{initial:20,expended:10}}},{id:"sort-B",name:"B",side:"Allied",last:{},ammo:{primary:{initial:1000,expended:100}}},{id:"sort-C",name:"C",side:"Allied",last:{},ammo:{primary:{initial:50,expended:40}}}];selectCategory("ranged")');
for(const order of ['C,A,B','B,A,C','C,A,B']){
 assert.equal(e('sortedUnits().map(u=>u.name).join(",")'),order);
 assert.ok(n('rows').innerHTML.includes('style="--bar:80%"'));
 n('head').onclick({target:{closest:()=>({dataset:{key:'primary_ammo_expended'}})}});
}
e('D.units=savedUnits;selectCategory("simple")');
assert.equal(e('visibleActivity({last:{},ammo:{}},"firing")'),false);
assert.equal(e('visibleActivity({last:{},ammo:{secondary:{initial:3}}},"firing")'),true);
assert.equal(e('visibleActivity({last:{flying:false},ever_flying:false},"grounded")'),false);
assert.equal(e('visibleActivity({last:{flying:false},ever_flying:true},"grounded")'),true);
assert.equal(e('displayFatigueState({fatigue_state:0,fatigue_state_native:2,fatigue_points:7000})'),2);
e("selectCategory('gold')");assert.match(n('rows').innerHTML,/gold-bar/);
n('unit-panels').onchange({target:{dataset:{graph:'2'},value:'leadership'}});assert.equal(e('graphMetrics[2]'),'leadership');
assert.ok(!markup.includes('Arrange & hide views'));assert.ok(!script.includes('Hover to inspect the nearest recorded sample'));
assert.ok(e('METRICS.every(([key])=>metricNote(key,D.units[0]).length>40)'));
n('hide-graph-explanations').onchange({target:{checked:true}});assert.equal(n('graph-note-0').hidden,true);assert.equal(n('movement-note').hidden,true);assert.equal(n('winds-note').hidden,true);
e('selectUnit(scopedUnits()[1]?.id||scopedUnits()[0].id)');assert.equal(e('graphMetrics[2]'),'leadership');assert.equal(n('graph-note-2').hidden,true);
let reload=run();assert.equal(reload.e('graphMetrics[2]'),'leadership');assert.equal(reload.node('hide-graph-explanations').checked,true);assert.equal(reload.e('unitWorth(scopedUnits()[0]).value'),1000);
n('hide-graph-explanations').onchange({target:{checked:false}});assert.equal(n('graph-note-0').hidden,false);assert.equal(n('winds-note').hidden,false);assert.match(n('graph-note-2').textContent,/leadership/i);
assert.equal(e('sameSegment({segment:1},{segment:2})'),false);assert.equal(e('known({last:{hp_cached:null},last_observed:{hp_cached:{value:500}}},"hp_cached")'),null);
assert.equal(e('metricValue({hp_cached:1000,healing_budget_remaining_hp:6000},"healing_cap_remaining",{})'),7000);
assert.equal(e('metricValue({healing_ceiling_fraction_raw:1.5,hp_max_cached:8000},"healing_cap_remaining",{last:{models_initial:1}})'),12000);
assert.equal(e('metricValue({healing_ceiling_fraction_raw:1.5,hp_max_cached:8000},"healing_cap_remaining",{last:{models_initial:120}})'),null);
assert.equal(e('metricValue({primary_ammo_fraction:.5},"primary_ammo",{})'),null);
assert.equal(e('JSON.stringify(plotRange([-20,80],"leadership"))'),'[-80,80]');e('ELEVATION_MIN=-50');assert.equal(e('plotRange([100,120],"elevation")[0]'),-50);
operations.length=0;e("plot('graph-0',[{t:0,leadership:80,segment:1},{t:1,leadership:-20,segment:1}],['leadership'],['#fff'])");assert.ok(operations.some(o=>o.method==='setLineDash'&&o.args[0].length===2));
operations.length=0;e("plot('winds',[{t:0,maximum:0,current:0,segment:1},{t:1,maximum:100,current:12,segment:1}],['current'],['#fff'])");assert.equal(operations.filter(o=>o.method==='lineTo').length,3);
n('recorded-details').open=true;n('recorded-details').ontoggle();assert.match(n('detail').innerHTML,/Damage breakdown/);
n('side').value='Enemy';n('side').onchange();assert.match(n('unit-side').textContent,/ENEMY/);e("selectCategory('damage')");assert.match(n('rows').innerHTML,/damage-incoming/);
const occupied=JSON.parse(e('JSON.stringify([...occupancy([{t:0,xyz:[0,0,0],segment:1,position_segment:1},{t:10,xyz:[0,0,0],segment:1,position_segment:1},{t:30,xyz:[0,0,0],segment:2,position_segment:2},{t:35,xyz:[0,0,0],segment:2,position_segment:2}],()=>[20,20]).values()])'));
assert.equal(occupied[0].seconds,15);assert.equal(e('timeColor(0)'),'rgb(56,202,114)');assert.equal(e('timeColor(1)'),'rgb(238,82,82)');
storage.set('wh3-report-unit-layout-v1',JSON.stringify([{id:'view-2',visible:false}]));const legacyLayout=run();assert.equal(legacyLayout.e('layout.filter(p=>p.visible).length'),7);
const blocked=run(true);blocked.e('setExplanationsHidden(true)');assert.equal(blocked.node('hide-graph-explanations').checked,true);assert.equal(blocked.node('graph-note-0').hidden,true);

assert.ok(n("winds"));assert.equal(e('cellText({first:{models:80},last:{models_initial:120}},"models_initial")'),"80/120");

assert.equal(e("JSON.stringify(MOVEMENT_BOUNDS)"),JSON.stringify(data.movement_bounds));
assert.equal(e('seconds(12.6)'),'13');assert.equal(e('seconds(12.4)'),'12');
assert.match(e('HEALING_CAP_TIP'),/100%.*150%/);assert.match(e('cellTip("gold_damage")'),/500 gold per level/);assert.match(e('cellTip("trade")'),/500 gold per level/);
assert.equal(e('unitWorth({id:"level-test",name:"x",last:{has_character_rank:true,character_level:7}}).value'),3500);
assert.equal(e('unitWorth({id:"level-test",name:"x",last:{has_character_rank:true}}).value'),500);
assert.equal(e('statusName({fresh:false,last:{left_battlefield:true}})'),"Dead / retreated");
assert.equal(e('statusName({fresh:true,last:{alive:false,left_battlefield:false}})'),"Dead / retreated");
assert.equal(e('known({last:{alive:false,hp_cached:null},last_observed:{hp_cached:{value:231}}},"hp_cached")'),231);
assert.equal(e('known({last:{alive:false,models:null},last_observed:{models:{value:3}}},"models")'),3);
assert.equal(e('CATEGORIES.taken.note'),'');assert.ok(!e('HEALING_CAP_TIP.includes("175%")'));
assert.equal(e('fatigueName(4)'),"Very tired");assert.equal(e('fatigueName(6)'),"Unknown");
e('D.fatigue_rules={maximum:30000,thresholds:[0,2800,6600,12600,18000,27000,30000]}');
assert.equal(e('displayFatigueName({fatigue_state:5,fatigue_points:30000})'),'Maximum');assert.equal(e('metricValue({fatigue_state:6},"fatigue_state")'),null);
assert.equal(e('JSON.stringify(plotRange([100,14000],"fatigue_points"))'),'[0,30000]');
operations.length=0;e("plot('graph-0',[{t:0,fatigue_points:100,segment:1},{t:10,fatigue_points:13000,segment:1}],['fatigue_points'],['#fff'],{fatigue_points_peak:18001})");assert.ok(operations.some(o=>o.method==='fillText'&&o.args[0]==='Very tired'));assert.ok(!operations.some(o=>o.method==='fillText'&&o.args[0]==='Exhausted'));
operations.length=0;e("plot('graph-0',[{t:0,damage:0,segment:1},{t:10,damage:100,segment:1}],['damage'],['#fff'])");
for(const label of ['25','50','75'])assert.ok(!operations.some(o=>o.method==='fillText'&&o.args[0]===label));assert.equal(operations.filter(o=>o.method==='setLineDash'&&o.args[0]?.length===2).length,3);
assert.ok(!operations.some(o=>o.method==='fillText'&&String(o.args[0]).includes('%')));
operations.length=0;e("plot('graph-0',[{t:0,fatigue_state:0,segment:1},{t:10,fatigue_state:4,segment:1}],['fatigue_state'],['#fff'])");assert.ok(operations.some(o=>o.method==='fillText'&&o.args[0]==='Very tired'));assert.equal(operations.filter(o=>o.method==='setLineDash'&&o.args[0]?.length===2).length,7);
e("showView('unit');openMini(0)");assert.equal(e('minis.length'),1);assert.equal(e('chartOccupied(selected,graphMetrics[0],"main-0")'),false);assert.ok(!n('unit-panels').innerHTML.includes('chart-in-mini'));assert.equal(e('chartOccupied(selected,graphMetrics[0],minis[0].id)'),false);assert.ok(!r.windows[0].document.body.innerHTML.includes('already shown'));
assert.ok(r.windows[0].document.getElementById('mini-note').textContent.length>40);e('setExplanationsHidden(true)');assert.equal(r.windows[0].document.getElementById('mini-note').hidden,true);e('renderMini(minis[0])');assert.equal(r.windows[0].document.getElementById('mini-note').hidden,true);e('setExplanationsHidden(false)');assert.equal(r.windows[0].document.getElementById('mini-note').hidden,false);
let mainBefore=e('graphMetrics[0]');let popupBefore=e('minis[0].metric');
n('unit-panels').onchange({target:{dataset:{graph:'0'},value:'fatigue_points'}});assert.equal(e('minis[0].metric'),popupBefore);
n('unit-panels').onchange({target:{dataset:{graph:'0'},value:mainBefore}});assert.equal(e('graphMetrics[0]'),mainBefore);
assert.match(n('unit-panels').innerHTML,/data-popout="0" disabled/);assert.ok(!/data-popout="1" disabled/.test(n('unit-panels').innerHTML));e('openMini(0)');assert.equal(e('minis.length'),1);e('minis[0].win.close()');assert.equal(e('minis.length'),0);assert.ok(!/data-popout="0" disabled/.test(n('unit-panels').innerHTML));e('openMini(0)');assert.equal(e('minis.length'),1);
let mainMetric=e('graphMetrics[0]');e('minis[0].metric=graphMetrics[1];syncMiniViews()');assert.equal(e('graphMetrics[0]'),mainMetric);e('minis[0].metric=graphMetrics[0];syncMiniViews()');
e('openMini(1);openMini(2);openMini(3)');assert.equal(e('minis.length'),4);e('openMini(0)');assert.equal(e('minis.length'),4);assert.match(n('unit-panels').innerHTML,/data-popout="3" disabled/);
assert.ok(r.windows.every(w=>w.document.getElementById('mini-chart')));
let oldId=e('minis[0].unitId');e('changeMiniUnit(minis[0],D.units.find(u=>u.id!==selected).id)');assert.notEqual(e('minis[0].unitId'),oldId);assert.equal(e('minis[1].unitId'),oldId);
e('changeMiniUnit(minis[0],selected)');assert.equal(e('minis[0].metric'),e('graphMetrics[0]'));
e('minis[0].win.closed=true;reapClosedMinis()');assert.equal(e('minis.length'),3);assert.ok(!/data-popout="0" disabled/.test(n('unit-panels').innerHTML));e('minis.slice().forEach(m=>m.win.close())');assert.equal(e('minis.length'),0);assert.equal(e('chartOccupied(selected,graphMetrics[0],"main-0")'),false);
assert.ok(!script.includes('documentPictureInPicture'));assert.ok(!script.includes('mini-pin'));
e('openMini(0)');assert.ok(!r.windows.at(-1).document.body.innerHTML.includes('Always on top'));e('minis.slice().forEach(m=>m.win.close())');
assert.equal(e('lineAt([{t:0,damage:10,segment:1},{t:10,damage:30,segment:1}],4,"damage",{}).value'),10);
assert.equal(e('lineAt([{t:0,damage:10,segment:1},{t:10,damage:30,segment:2}],6,"damage",{}).t'),10);
assert.equal(e('lineAt([{t:0,damage:null,segment:1},{t:10,damage:30,segment:1}],4,"damage",{})'),null);
assert.equal(e('lineAt([{t:0,fatigue_state:0,segment:1},{t:10,fatigue_state:4,segment:1}],6,"fatigue_state",{}).value'),4);
assert.equal(e('lineAt([],5,"damage",{})'),null);
operations.length=0;e('drawMovement({history:[{t:0,segment:1,position_segment:1,xyz:[0,0,0]},{t:1,segment:1,position_segment:1,xyz:[1,0,1]}]})');assert.deepEqual(operations.filter(o=>o.method==='arc').map(o=>o.args[2]),[7,11]);assert.ok(operations.some(o=>o.method==='fillRect'));assert.ok(operations.some(o=>o.method==='lineTo'));

assert.equal(e('graphNumber(47.8,"damage")'),'48');assert.equal(e('graphNumber(47.28,"elevation")'),'47.28');
e("plot('graph-0',[{t:0,damage:0,segment:1},{t:10,damage:100.4,segment:1}],['damage'],['#fff'],{id:'hover-test'})");
n('graph-0').onmousemove({clientX:400,clientY:100});assert.equal(n('graph-0-tooltip').hidden,false);assert.match(n('graph-0-tooltip').innerHTML,/Time: 0s/);assert.match(n('graph-0-tooltip').innerHTML,/Damage dealt: <b>0/);assert.equal(n('graph-0-cursor').style.left,'52px');
n('graph-0').onmousemove({clientX:700,clientY:100});assert.match(n('graph-0-tooltip').innerHTML,/Time: 10s/);assert.match(n('graph-0-tooltip').innerHTML,/Damage dealt: <b>100/);assert.ok(!n('graph-0-tooltip').innerHTML.includes('100.4'));assert.ok(!n('graph-0-tooltip').innerHTML.includes('Between samples'));
assert.equal(n('graph-0').onwheel,null);assert.equal(n('graph-0').onmousedown,null);assert.equal(n('graph-0').ondblclick,null);assert.ok(!script.includes('Scroll to zoom'));assert.ok(!script.includes('moveChartRange'));
e("plot('graph-0',[{t:0,xyz:[0,47.28,0],segment:1}],['elevation'],['#fff'],{id:'hover-test'})");n('graph-0').onmousemove({clientX:400,clientY:100});assert.match(n('graph-0-tooltip').innerHTML,/Elevation: <b>47.28/);
e("plot('graph-0',[{t:0,damage:null,models:2,segment:1},{t:10,damage:30,models:2,segment:2}],['damage','models'],['#fff','#eee'],{id:'hover-test'})");n('graph-0').onmousemove({clientX:400,clientY:100});assert.match(n('graph-0-tooltip').innerHTML,/No recorded value/);
n('graph-0').onmouseleave();assert.equal(n('graph-0-tooltip').hidden,true);
console.log('Report checks pass: nearest recorded sample/time, missing values, whole-number graph values except elevation, removed zoom, unlabeled guides, independent popouts and existing report interactions. Browser visual layout not assessed.');
