import re
from traceline import TraceLine

# 3.14
# sched_switch: prev_comm=umount prev_pid=7868 prev_prio=120 prev_state=D ==> next_comm=swapper/0 next_pid=0 next_prio=120
sched_switch_re = re.compile("sched_switch: prev_comm=(.+) prev_pid=(\d+) .* ==> next_comm=(.+) next_pid=(\d+) .*")

# 3.14
# sched_wakeup: comm=fish pid=5361 prio=120 success=1 target_cpu=001
sched_wakeup_re = re.compile("sched_wakeup: comm=(.+) pid=(\d+) prio=\d+ success=.* target_cpu=(\d+)")

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

def schedWakeupParse(trace):
    m = sched_wakeup_re.match(trace)
    if not m:
        return None
    event = {}
    event["comm"] = m.group(1)
    event["pid"] = int(m.group(2))
    event["cpu"] = int(m.group(3))
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
        self.waketime = 0.0
        self.stacktrace = ""
        self.wakeupStacktrace = ""
        self.changeCpu = False

    # This is when we get the sched_wakeup event, which is different from
    # actually waking up, we are just telling the scheduler we are ready to
    # wakeup the given pid.
    def wakeEvent(self, trace):
        self.waketime = trace["timestamp"]

    # This is when we are actually placed onto the CPU to do our work
    def wakeup(self, trace):
        self.sleeptime = trace["timestamp"] - self.trace["timestamp"]
        self.waketime = trace["timestamp"] - self.waketime
        if self.trace["cpu"] != trace["cpu"]:
            self.changeCpu = True
