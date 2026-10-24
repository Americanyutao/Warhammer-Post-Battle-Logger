"""First observed firing/melee window, with a simulation-time idle grace."""


class FirstEngagement:
    def __init__(self, idle_grace_s=3.):
        self.grace = idle_grace_s
        self.start = self.end = self.through = self.idle_since = None
        self.status = 'not_observed'

    def observe(self, t, unit):
        if self.status in ('completed', 'interrupted', 'inactive_observed'):
            return
        if unit.get('alive') is False and self.start is not None:
            self.end = self.through = t
            self.status = 'inactive_observed'
            return
        # Charging can join this classifier when a collector supplies it.
        states = [unit.get('firing'), unit.get('melee')]
        if isinstance(unit.get('charging'), bool):
            states.append(unit['charging'])
        active = True if any(s is True for s in states) else False if all(s is False for s in states) else None
        if active is None:
            self.interrupt()
            return
        if self.start is not None and self.idle_since is not None and t - self.idle_since >= self.grace:
            self.end, self.status = self.idle_since, 'completed'
            return
        self.through = t
        if active:
            if self.start is None:
                self.start, self.status = t, 'ongoing'
            self.idle_since = None
        elif self.start is not None and self.idle_since is None:
            self.idle_since = t

    def interrupt(self):
        if self.start is not None and self.status == 'ongoing':
            self.end, self.status = self.through, 'interrupted'

    def summary(self):
        stop = self.end if self.end is not None else self.through
        return dict(start_s=self.start, end_s=self.end, observed_through_s=self.through,
                    duration_estimate_s=stop-self.start if self.start is not None else None,
                    status=self.status, idle_grace_s=self.grace)
