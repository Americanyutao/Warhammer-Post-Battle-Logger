"""Provider-neutral deployment baseline and combat recording boundary."""
import copy
from aggregate import number, STATES


class CombatWindow:
    def __init__(self):
        self.baseline = None
        self.started = False

    def accept(self, frame):
        phase = frame.get('battle_phase')
        if phase in (0, 4):
            # Keep only the latest deployment snapshot. Positions and activities
            # belong to combat, never to a deployment-to-combat path segment.
            self.started = False
            excluded = {'xyz','alive','left_battlefield','awaiting_order_after_rally_raw',*STATES}
            self.baseline = dict(sim_s=frame.get('sim_s'), source='native_deployment',
                units=[{k:copy.deepcopy(v) for k,v in u.items() if k not in excluded} for u in frame['units']],
                armies=copy.deepcopy(frame.get('armies', [])))
            return None
        if not self.started:
            if phase not in (5, 6, 7) or not number(frame.get('sim_s')):
                return None
            self.started = True
            if self.baseline is not None:
                frame = dict(frame, deployment_baseline=self.baseline)
                self.baseline = None
        # Retain results (and temporary unknown phases) once combat has started.
        return frame
