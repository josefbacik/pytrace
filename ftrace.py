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

def getTraceDir():
    if __m.traceDir != "":
        return __m.traceDir
    f = open("/proc/mounts", "r")
    mounts_re = re.compile("([a-zA-Z0-9_/\-,]+) ([a-zA-Z0-9_/\-,]+) (\w+) .*")
    for line in f:
        m = mounts_re.match(line)
        if not m:
            print("didn't find what we wanted '%s'" % line)
            continue
        if m.group(1) == "debugfs":
            __m.traceDir = m.group(2) + "/tracing/"
            print("found debugfs")
            break
        else:
            print("found '%s'" % m.group(1))
    f.close()
    return __m.traceDir
