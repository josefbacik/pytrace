import re
from traceline import TraceLine

# 3.14
# sched_switch: prev_comm=umount prev_pid=7868 prev_prio=120 prev_state=D ==> next_comm=swapper/0 next_pid=0 next_prio=120

sched_switch_re = re.compile("sched_switch: prev_comm=(.+) prev_pid=(\d+) .* ==> next_comm=(.+) next_pid=(\d+) .*")

def isSchedSwitch(trace):
    m = sched_switch_re.search(trace)
    if not m:
        return False
    return True

def schedSwitchParse(trace):
    m = sched_switch_re.match(trace)
    if not m:
        return None
    event = {}
    event["prev_comm"] = m.group(1)
    event["prev_pid"] = int(m.group(2))
    event["next_comm"] = m.group(3)
    event["next_pid"] = int(m.group(4))
    return event

class SchedSwitchEvent(TraceLine):
    def __init__(self, trace, event=None):
        TraceLine.__init__(self, trace)
        if not event:
            self.event = schedSwitchParse(trace["data"])
        else:
            self.event = event
        self.trace["comm"] = self.event["prev_comm"]
        if not self.event:
            raise ValueError
        self.sleeptime = 0.0
        self.stacktrace = ""

    def wakeup(self, trace):
        self.sleeptime = trace["timestamp"] - self.trace["timestamp"]
