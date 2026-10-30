"""Small, validated overlay layout; recordings and collected values are separate."""


def clean_layout(value):
    if not isinstance(value,dict):return {}
    result={}
    for name,low,high in [('x',-131072,131072),('y',-131072,131072),('width',340,8192),('height',220,8192)]:
        if type(value.get(name)) is int and low<=value[name]<=high:result[name]=value[name]
    if value.get('scope') in ('all','ally','enemy'):result['scope']=value['scope']
    if value.get('metric') in ('damage','healing_budget_remaining_hp'):result['metric']=value['metric']
    return result
