#!/bin/python

import argparse
import traceline
import operator
import ftrace
import signal
import sys
import sched
import time
from subprocess import Popen
import os
import shlex
import select

# We want to keep track of total sleep time per stacktrace per process, so heres
# a basic class to aggregate all of this stuff in one place
class Process:
    def __init__(self, event, collapsed):
        if collapsed:
            self.pid = 0
        else:
            self.pid = event.trace["pid"]
        self.comm = event.trace["comm"]
        self.events = { event.stacktrace : event }
        self.wakeups = { event.wakeupStacktrace : 1 }
        self.numEvents = 1
        if event.hadWakeEvent:
            self.waketime = { "avg" : event.timeToWake, "min" : event.timeToWake, "max" : event.timeToWake }
        else:
            self.waketime = { "avg" : 0.0, "min" : 1000000000.0, "max" : 0.0 }
        self.cpuChanges = 0
        self.collapsed = collapsed
        self.sleepRanges = ftrace.TimeRange(event.trace["timestamp"], event.woken)

    def addEvent(self, event):
        if event.stacktrace in self.events:
            self.events[event.stacktrace].sleepRanges.addRange(event.trace["timestamp"], event.woken)
        else:
            self.events[event.stacktrace] = event
        if event.wakeupStacktrace in self.wakeups:
            self.wakeups[event.wakeupStacktrace] += 1
        else:
            self.wakeups[event.wakeupStacktrace] = 1
        self.sleepRanges.addRange(event.trace["timestamp"], event.woken)
        if event.changeCpu:
            self.cpuChanges += 1
        if event.hadWakeEvent:
            if self.waketime["avg"] > 0.0:
                self.waketime["avg"] += event.timeToWake
                self.waketime["avg"] /= 2
            else:
                self.waketime["avg"] = event.timeToWake
            if event.timeToWake > self.waketime["max"]:
                self.waketime["max"] = event.timeToWake
            if event.timeToWake < self.waketime["min"]:
                self.waketime["min"] = event.timeToWake
        self.numEvents += 1

def toggleEvents(toggle, wakeups=False, command=None):
    if toggle:
        ftrace.enableEvent("sched/sched_switch")
        if wakeups:
            ftrace.enableEvent("sched/sched_wakeup")
        if command:
            ftrace.filterPid(os.getpid())
        ftrace.enableStackTrace()
        ftrace.clearTraceBuffer()
        ftrace.enableFtrace()
    else:
        ftrace.disableFtrace()
        ftrace.disableEvent("sched/sched_switch")
        ftrace.disableEvent("sched/sched_wakeup")
        ftrace.disableStackTrace()
        ftrace.clearFilterPid()

def signalHandler(signal, frame):
    toggleEvents(False)
    sys.exit(0)

def findSleepiestProcess(processes):
    maxSleep = 0.0
    key = 0
    for process in processes.keys():
        if processes[process].sleepRanges.total > maxSleep:
            maxSleep = processes[process].sleepRanges.total
            key = process
    return key

def findSleepiestEvent(events):
    maxSleep = 0.0
    key = ""
    for e in events.keys():
        if events[e].sleepRanges.total > maxSleep:
            maxSleep = events[e].sleepRanges.total
            key = e
    return key

def printStackTrace(stacktrace):
    tracelist = stacktrace.split(':')
    for v in tracelist:
        print("\t\t" + v)

def printSummary(processes, totalTime):
    print("Total time run %f seconds" % totalTime)
    while processes:
        p = findSleepiestProcess(processes)
        process = processes[p]
        print("Process %s-%d" % (process.comm, process.pid))
        print("=> Time asleep:\t\t\t%f" % process.sleepRanges.total)
        print("=> Cpu changes:\t\t\t%d" % process.cpuChanges)
        print("=> Num sleep/wake cycles:\t%d" % process.numEvents)
        if process.waketime["avg"] > 0.0:
            print("=> Wake latency min,avg,max:\t%f, %f, %f" %
                  (process.waketime["min"], process.waketime["avg"], process.waketime["max"]))
        print("=> Percentage of total:\t\t%f" % ((process.sleepRanges.total / totalTime) * 100))
        while process.events:
            e = findSleepiestEvent(process.events)
            event = process.events[e]
            print("\tSpent %f seconds in here, %f percentage of sleep time" %
                    (event.sleepRanges.total, ((event.sleepRanges.total / process.sleepRanges.total) * 100)))
            printStackTrace(event.stacktrace)
            del process.events[e]
        for trace in sorted(process.wakeups, key=process.wakeups.get, reverse=True):
            if trace == "":
                continue
            print("\tWoken up %d times like this" % process.wakeups[trace])
            printStackTrace(trace)
        del processes[p]

parser = argparse.ArgumentParser(description="Track top latency reason")
parser.add_argument('infile', nargs='?', help='Process a tracefile')
parser.add_argument('-w', action='store_true')
parser.add_argument('-t', '--time', type=float, help="Only run for the given amount of seconds")
parser.add_argument('-n', '--name', type=str, help="Only pay attention to processes with this name")
parser.add_argument('-o', '--output', type=str, help="Write all trace data to this file")
parser.add_argument('-c', '--collapse', action='store_true', help="Collapse all comms into one big event")
parser.add_argument('-r', '--run', type=str, help="Run and profile this command")

args = parser.parse_args()
infile = None
continual = False
runTime = 5
liveSystem = False
traceFile = None
poll = select.poll()

if not args.infile:
    traceDir = ftrace.getTraceDir()
    if traceDir == "":
        print("Please mount debugfs to use this feature")
        sys.exit(1)
    infd = os.open(traceDir+"trace_pipe", os.O_RDONLY|os.O_NONBLOCK)
    poll.register(infd, select.POLLIN)
    infile = os.fdopen(infd)
    if args.output:
        traceFile = open(args.output, "w+")
    toggleEvents(True, args.w, args.run)
    signal.signal(signal.SIGINT, signalHandler)
    liveSystem = True
    if args.time:
        runTime = args.time
    else:
        continual = True
else:
    infile = open(args.infile, 'r')

processes = {}
sleeping = {}
waking = {}
stacktrace = 0
start = time.time()
curEvent = None
firstTime = 0.0
lastTime = 0.0
commandP = None
exited = False
devNull = None

if args.run:
    devNull = open("/dev/null", 'w')
    commandP = Popen(shlex.split(args.run), stdout=devNull, stderr=devNull)

while 1:
    results = poll.poll(100)
    if not results:
        if exited:
            break
        continue
    while 1:
        try:
            line = infile.readline()
        except:
            break
        if traceFile:
            traceFile.write(line)
        trace = traceline.traceParseLine(line)
        if not trace:
            if stacktrace > 0:
                func = traceline.parseStacktraceLine(line)
                if not func:
                    stacktrace = 0
                    curEvent = None
                    continue
                if not curEvent:
                    continue
                if stacktrace == 1:
                    if curEvent.stacktrace == "":
                        curEvent.stacktrace = func
                    else:
                        curEvent.stacktrace += ":" + func
                else:
                    if curEvent.wakeupStacktrace == "":
                        curEvent.wakeupStacktrace = func
                    else:
                        curEvent.wakeupStacktrace += ":" + func
            continue
        if firstTime == 0.0:
            firstTime = trace["timestamp"]
        else:
            lastTime = trace["timestamp"]
        stacktrace = 0
        curEvent = None

        # We can get a couple of sched events before we start to spit out the
        # stack trace so we need to pay attention to the pid in the stack trace
        # line and pick out the right event
        if traceline.isStackTrace(trace["data"]):
            if trace["pid"] in sleeping:
                # Sometimes we can miss wakeup messages, and we've already
                # gotten a stacktrace for this event, if this is the case just
                # skip this stacktrace and delete this event
                curEvent = sleeping[trace["pid"]]
                if curEvent.stacktrace == "":
                    stacktrace = 1
                else:
                    curEvent = None
                    del sleeping[trace["pid"]]
            elif trace["pid"] in waking:
                stacktrace = 2
                curEvent = waking[trace["pid"]]
                del waking[trace["pid"]]
            continue

        # Wakeup actions are going to happen from a different PID for a given
        # PID so we just want to find the sleeper and start the wakeup timer and
        # then setup a pending waker so we can scrape it's stacktrace
        eventDict = sched.schedWakeupParse(trace["data"])
        if eventDict:
            if eventDict["pid"] in sleeping:
                e = sleeping[eventDict["pid"]]
                e.wakeEvent(trace)
                waking[trace["pid"]] = e
            continue

        # Still need to track the sched_switch wakeup part since that is when we
        # actually load the process onto the CPU and make it do shit.  Only then
        # we can remove it from our sleeping dict and add it to the process
        eventDict = sched.schedSwitchParse(trace["data"])
        if eventDict["next_pid"] in sleeping:
            e = sleeping[eventDict["next_pid"]]
            e.wakeup(trace)
            key = e.trace["pid"]
            if args.collapse:
                key = e.trace["comm"]
            if key in processes:
                processes[key].addEvent(e)
            else:
                processes[key] = Process(e, args.collapse)
            del sleeping[eventDict["next_pid"]]

        # Nobody cares about you idle processes
        if eventDict["prev_pid"] == 0:
            continue

        if commandP and eventDict["prev_pid"] != commandP.pid:
            continue

        # Don't record events about processes we don't care about
        if args.name and eventDict["prev_comm"].find(args.name) == -1:
            continue

        e = sched.SchedSwitchEvent(trace, eventDict)
        sleeping[eventDict["prev_pid"]] = e
        if not commandP and liveSystem and (time.time() - start) >= runTime:
            if not continual:
                toggleEvents(False, args.w)
                exited = True
                break
            printSummary(processes, lastTime - firstTime)
            firstTime = 0.0
            processes = {}
            sleeping = {}
            waking = {}
            start = time.time()

        # Check to see if our command exited, if it did disable polling and
        # trace_pipe will return EOF once we've gotten the rest of the stuff in
        # the buffer.
        if commandP and not exited:
            retval = commandP.poll()
            if retval is not None:
                exited = True
                ftrace.disableFtrace()

printSummary(processes, lastTime - firstTime)
if traceFile:
    traceFile.close()
if args.run:
    devNull.close()
