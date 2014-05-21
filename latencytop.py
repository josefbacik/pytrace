#!/bin/python

import argparse
import traceline
import operator
import ftrace
import signal
import sys
import sched
import time

# We want to keep track of total sleep time per stacktrace per process, so heres
# a basic class to aggregate all of this stuff in one place
class Process:
    def __init__(self, event):
        self.pid = event.trace["pid"]
        self.comm = event.trace["comm"]
        self.events = { event.stacktrace : event }
        self.wakeups = { event.wakeupStacktrace : 1 }
        self.numEvents = 1
        self.sleeptime = event.sleeptime
        self.waketime = event.waketime
        self.cpuChanges = 0

    def addEvent(self, event):
        if event.stacktrace in self.events:
            self.events[event.stacktrace].sleeptime += event.sleeptime
        else:
            self.events[event.stacktrace] = event
        if event.wakeupStacktrace in self.wakeups:
            self.wakeups[event.wakeupStacktrace] += 1
        else:
            self.wakeups[event.wakeupStacktrace] = 1

        if event.changeCpu:
            self.cpuChanges += 1
        self.sleeptime += event.sleeptime
        self.waketime += event.waketime
        self.numEvents += 1

def toggleEvents(toggle, wakeups=False):
    if toggle:
        ftrace.enableEvent("sched/sched_switch")
        if wakeups:
            ftrace.enableEvent("sched/sched_wakeup")
        ftrace.enableStackTrace()
    else:
        ftrace.disableEvent("sched/sched_switch")
        ftrace.disableEvent("sched/sched_wakeup")
        ftrace.disableStackTrace()

def signalHandler(signal, frame):
    toggleEvents(False)
    sys.exit(0)

def findSleepiestProcess(processes):
    maxSleep = 0.0
    key = 0
    for process in processes.keys():
        if processes[process].sleeptime > maxSleep:
            maxSleep = processes[process].sleeptime
            key = process
    return key

def findSleepiestEvent(events):
    maxSleep = 0.0
    key = ""
    for e in events.keys():
        if events[e].sleeptime > maxSleep:
            maxSleep = events[e].sleeptime
            key = e
    return key

def printStackTrace(stacktrace):
    tracelist = stacktrace.split(':')
    for v in tracelist:
        print("\t\t\t" + v)

def printSummary(processes, totalTime, totalSleep):
    print("Total slept for %f seconds out of %f" % (totalSleep, totalTime))
    while processes:
        p = findSleepiestProcess(processes)
        process = processes[p]
        print("\tProcess %s-%d spent %f asleep %d cpu changes %d sleep/wake cycles, %f percentage of total" %
                (process.comm, process.pid, process.sleeptime, process.cpuChanges, process.numEvents, ((process.sleeptime / totalTime)) * 100))
        while process.events:
            e = findSleepiestEvent(process.events)
            event = process.events[e]
            print("\t\tSpent %f seconds in here, %f percentage of sleep time" %
                    (event.sleeptime, ((event.sleeptime / process.sleeptime) * 100)))
            printStackTrace(event.stacktrace)
            del process.events[e]
        for trace in sorted(process.wakeups, key=process.wakeups.get, reverse=True):
            if trace == "":
                continue
            print("\t\tWoken up %d times like this" % process.wakeups[trace])
            printStackTrace(trace)
        del processes[p]

parser = argparse.ArgumentParser(description="Track top latency reason")
parser.add_argument('infile', nargs='?', help='Process a tracefile')
parser.add_argument('-w', action='store_true')
parser.add_argument('-t', '--time', type=int, help="Only run for the given amount of seconds")
parser.add_argument('-n', '--name', type=str, help="Only pay attention to processes with this name")

args = parser.parse_args()
infile = None
continual = False
runTime = 5
liveSystem = False

if not args.infile:
    traceDir = ftrace.getTraceDir()
    if traceDir == "":
        print("Please mount debugfs to use this feature")
        sys.exit(1)
    infile = open(traceDir+"trace_pipe", 'r')
    toggleEvents(True, args.w)
    signal.signal(signal.SIGINT, signalHandler)
    liveSystem = True
    if args.time:
        runTime = args.Runtime
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
totalSleep = 0.0
firstTime = 0.0
lastTime = 0.0

for line in infile:
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

    # We can get a couple of sched events before we start to spit out the stack
    # trace so we need to pay attention to the pid in the stack trace line and
    # pick out the right event
    if traceline.isStackTrace(trace["data"]):
        if trace["pid"] in sleeping:
            # Sometimes we can miss wakeup messages, and we've already gotten a
            # stacktrace for this event, if this is the case just skip this
            # stacktrace and delete this event
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

    # Wakeup actions are going to happen from a different PID for a given PID
    # so we just want to find the sleeper and start the wakeup timer and then
    # setup a pending waker so we can scrape it's stacktrace
    eventDict = sched.schedWakeupParse(trace["data"])
    if eventDict:
        if eventDict["pid"] in sleeping:
            e = sleeping[eventDict["pid"]]
            e.wakeEvent(trace)
            waking[trace["pid"]] = e
        continue

    # Still need to track the sched_switch wakeup part since that is when we
    # actually load the process onto the CPU and make it do shit.  Only then we
    # can remove it from our sleeping dict and add it to the process
    eventDict = sched.schedSwitchParse(trace["data"])
    if eventDict["next_pid"] in sleeping:
        e = sleeping[eventDict["next_pid"]]
        e.wakeup(trace)
        totalSleep += e.sleeptime
        if e.trace["pid"] in processes:
            processes[e.trace["pid"]].addEvent(e)
        else:
            processes[e.trace["pid"]] = Process(e)
        del sleeping[eventDict["next_pid"]]

    # Nobody cares about you idle processes
    if eventDict["prev_pid"] == 0:
        continue

    # Don't record events about processes we don't care about
    if args.name and eventDict["prev_comm"].find(args.name) == -1:
        continue

    e = sched.SchedSwitchEvent(trace, eventDict)
    sleeping[eventDict["prev_pid"]] = e
    if liveSystem and (time.time() - start) >= runTime:
        if not continual:
            break
        printSummary(processes, lastTime - firstTime, totalSleep)
        firstTime = 0.0
        processes = {}
        sleeping = {}
        waking = {}
        start = time.time()

printSummary(processes, lastTime - firstTime, totalSleep)
