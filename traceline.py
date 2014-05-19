import re

# There are two formats I've seen so far
#       python2.7-4415  [011] .... 161710.648515: sys_exit: NR 13 = 0
#       python2.7-4415  [011] 161710.648515: sys_exit: NR 13 = 0
#
# Newer versions include things like need_resched and irqs disabled whereas
# older versions don't, so we account for both cases in our RE.
trace_re = re.compile("\s+(.*)-(\d+)\s+\[(\d+)\] (?:.... |)(\d+\.\d+): (.*)$")

def traceParseLine(traceStr):
    m = trace_re.match(traceStr)
    if not m:
        return None
    trace = {}
    trace["comm"] = m.group(1)
    trace["pid"] = int(m.group(2))
    trace["cpu"] = int(m.group(3))
    trace["timestamp"] = float(m.group(4))
    trace["data"] = m.group(5)
    return trace

class TraceLine:
	def __init__(self, trace):
		self.trace = trace
