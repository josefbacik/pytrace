import re

class Ftrace:
    pass

__m = Ftrace()
__m.traceDir = ""

def enableEvent(event):
    traceDir = getTraceDir()
    eventFile = open(traceDir+"events/"+event+"/enable", 'w')
    eventFile.write("1")
    eventFile.close()

def disableEvent(event):
    traceDir = getTraceDir()
    eventFile = open(traceDir+"events/"+event+"/enable", 'w')
    eventFile.write("0")
    eventFile.close()

def enableStackTrace():
    traceDir = getTraceDir()
    eventFile = open(traceDir+"options/stacktrace", 'w')
    eventFile.write("1")
    eventFile.close()

def disableStackTrace():
    traceDir = getTraceDir()
    eventFile = open(traceDir+"options/stacktrace", 'w')
    eventFile.write("0")
    eventFile.close()

def clearTraceBuffer():
    traceDir = getTraceDir()
    traceFile = open(traceDir+"trace", 'w')
    traceFile.write("")
    traceFile.close()

def filterPid(pid):
    traceDir = getTraceDir()
    try:
        traceFile = open(traceDir+"set_ftrace_pid", 'w')
    except:
        # Older kernels don't have set_ftrace_pid, losers
        return
    traceFile.write(str(pid))
    traceFile.close()

def clearFilterPid():
    traceDir = getTraceDir()
    try:
        traceFile = open(traceDir+"set_ftrace_pid", 'w')
    except:
        # Older kernels don't have set_ftrace_pid
        return
    traceFile.write("")
    traceFile.close()

def enableFtrace():
    traceDir = getTraceDir()
    traceFile = open(traceDir+"tracing_on", 'w')
    traceFile.write("1")
    traceFile.close()

def disableFtrace():
    traceDir = getTraceDir()
    traceFile = open(traceDir+"tracing_on", 'w')
    traceFile.write("0")
    traceFile.close()

def getTraceDir():
    if __m.traceDir != "":
        return __m.traceDir
    f = open("/proc/mounts", "r")
    mounts_re = re.compile("([a-zA-Z0-9_/\-,\.:]+) ([a-zA-Z0-9_/\-,\.:]+) (\w+) .*")
    for line in f:
        m = mounts_re.match(line)
        if not m:
            continue
        if m.group(3) == "debugfs":
            __m.traceDir = m.group(2) + "/tracing/"
            break
    f.close()
    return __m.traceDir

class TimeRange():
    def __init__(self, start, end):
        self._range = { start : end }
        self.total = end - start

    def __inRange(self, w, x, y, z):
        if z < w:
            return False
        if y > x:
            return False
        return True

    def addRange(self, newstart, newend):
        key = None
        for start,end in self._range.iteritems():
            if self.__inRange(start, end, newstart, newend):
                key = start
                break
        if not key:
            self._range[newstart] = newend
            self.total += newend - newstart
            return
        start = key
        end = self._range[key]
        if start <= newstart and end >= newend:
            return
        del self._range[start]
        self.total -= end - start
        if start > newstart:
            start = newstart
        if newend > end:
            end = newend
        self.addRange(start, end)
