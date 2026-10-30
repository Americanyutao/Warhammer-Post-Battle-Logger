"""Visibility-gated live display only; full recording samples stay untouched."""

FIELDS=('id','name','side','damage','healing_budget_remaining_hp','healing_budget_unlimited')


class LiveRoster:
    def __init__(self):self.rows={};self.ended=False
    def end(self):
        if not self.ended:
            for row in self.rows.values():row['final_detectable']=row['fresh'] and row['present'] and not row['departed']
        self.ended=True
    def missing(self):
        for row in self.rows.values():row['fresh']=False;row['present']=False
    def observe(self,units,results=False,visibility=None):
        self.missing()
        for unit in units:
            uid=str(unit['id']);previous=self.rows.get(uid)
            visible=unit.get('side')!='Enemy' or (visibility.get(uid) is True if visibility is not None else unit.get('out_of_opponents_vision') is False)
            if previous is None and not visible:continue
            # Native presence and explicit departure remain separate from LOS.
            departed=unit.get('left_battlefield') is True or (unit.get('alive') is False and not results)
            if previous and previous['departed'] and not (unit.get('alive') is True and unit.get('left_battlefield') is False):departed=True
            if previous and not visible:
                previous['present']=True
                if departed:previous['departed']=True;previous['final_detectable']=False
                continue
            row={field:unit.get(field) for field in FIELDS}
            # Keep last readable counters rather than replacing them with zero.
            if previous:
                for field in ('name','side','damage','healing_budget_remaining_hp','healing_budget_unlimited'):
                    if row[field] is None:row[field]=previous[field]
            row.update(id=uid,fresh=True,present=True,departed=departed,
                final_detectable=(not departed and (unit.get('alive') is not False or bool(previous and previous.get('final_detectable')))) if self.ended else None)
            self.rows[uid]=row
