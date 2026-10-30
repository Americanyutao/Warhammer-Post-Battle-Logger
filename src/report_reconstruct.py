"""Rebuild chart samples from matching primary observations, with exact fallbacks."""
import copy
import json


def signature(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def at(value,path):
    for key in path:
        if not isinstance(value,dict) or key not in value:return False,None
        value=value[key]
    return True,value


def put(row,path,value):
    for key in path[:-1]:row=row.setdefault(key,{})
    row[path[-1]]=copy.deepcopy(value)


def prepare_report(summary):
    report=copy.deepcopy(summary);recipes=[];formulas=[]
    for ui,unit in enumerate(report.get('units',[])):
        # Formulas use the existing collector's three-valued activity rules.
        activity=unit.get('activity_timeline') or {};samples=activity.get('samples',[])
        for kind,key in [('retreat','retreating_combined'),('grounded','grounded')]:
            indices=[]
            for i,row in enumerate(samples):
                values=row.get('values')
                if isinstance(values,dict) and key in values and signature(values[key])==signature(activity_value(values,kind)):
                    indices.append(i);del values[key]
            if indices:formulas.append([ui,kind,indices])
        cases=[(['history'],['spatial_timeline','samples'],[( [k],[k]) for k in ('segment','position_segment','xyz','damage','gold_damage','damage_taken_estimate','healing_received_estimate')]),
               (['history'],['statline_timeline','samples'],[([a],['values',b]) for a,b in [('hp_cached','hp'),('hp_max_cached','hp_max'),('models','models'),('healing_budget_remaining_hp','healing_budget_remaining_hp')]]),
               (['activity_timeline','samples'],['statline_timeline','samples'],[(['values',k],['state',k]) for k in ('routing','shattered','withdrawing')]+[(['segment'],['segment'])])]
        for target_path,source_path,fields in cases:
            target=get_path(unit,target_path);source=get_path(unit,source_path)
            if not isinstance(target,list) or not isinstance(source,list):continue
            original_target=get_path(summary['units'][ui],target_path)
            by_time={};duplicates=set()
            for i,row in enumerate(source):
                t=row.get('t')
                if t in by_time:duplicates.add(t)
                by_time[t]=i
            groups={}
            for target_field,source_field in fields:
                links=[]
                for ti,row in enumerate(original_target):
                    t=row.get('t')
                    if t in duplicates or t not in by_time:continue
                    si=by_time[t];other=source[si]
                    if row.get('segment')!=other.get('segment'):continue
                    present,value=at(row,target_field);found,source_value=at(other,source_field)
                    if present and found and signature(value)==signature(source_value):
                        links.append([ti,si]);parent=get_path(target[ti],target_field[:-1]);del parent[target_field[-1]]
                if links:
                    key=signature(links)
                    groups.setdefault(key,[[],links])[0].append([target_field,source_field])
            for fields,links in groups.values():recipes.append([ui,target_path,source_path,fields,links])
    return report,dict(copies=recipes,activities=formulas)


def get_path(value,path):
    for key in path:
        if not isinstance(value,dict):return None
        value=value.get(key)
    return value


def activity_value(values,kind):
    if kind=='grounded':return not values['flying'] if type(values.get('flying')) is bool else None
    flags=[values.get(k) for k in ('routing','shattered','withdrawing')]
    return True if any(v is True for v in flags) else False if all(v is False for v in flags) else None


def restore_report(report,recipes):
    for ui,target_path,source_path,fields,links in recipes['copies']:
        unit=report['units'][ui];target=get_path(unit,target_path);source=get_path(unit,source_path)
        for ti,si in links:
            for target_field,source_field in fields:put(target[ti],target_field,get_path(source[si],source_field))
    for ui,kind,indices in recipes['activities']:
        samples=report['units'][ui]['activity_timeline']['samples']
        for i in indices:
            values=samples[i]['values'];values['grounded' if kind=='grounded' else 'retreating_combined']=activity_value(values,kind)
    return report


JS_RESTORE="""function restoreReport(report,recipes){const get=(v,path)=>path.reduce((x,k)=>x[k],v);function set(v,path,x){for(const k of path.slice(0,-1)){if(!Object.hasOwn(v,k))Object.defineProperty(v,k,{value:{},enumerable:true,writable:true,configurable:true});v=v[k];}Object.defineProperty(v,path.at(-1),{value:structuredClone(x),enumerable:true,writable:true,configurable:true});}for(const [ui,tp,sp,fields,links] of recipes.copies){const u=report.units[ui],target=get(u,tp),source=get(u,sp);for(const [ti,si] of links)for(const [tf,sf] of fields)set(target[ti],tf,get(source[si],sf));}for(const [ui,kind,indices] of recipes.activities){const samples=report.units[ui].activity_timeline.samples;for(const i of indices){const v=samples[i].values;if(kind==='grounded')v.grounded=typeof v.flying==='boolean'?!v.flying:null;else{const flags=[v.routing,v.shattered,v.withdrawing];v.retreating_combined=flags.some(x=>x===true)?true:flags.every(x=>x===false)?false:null;}}}return report;} """
