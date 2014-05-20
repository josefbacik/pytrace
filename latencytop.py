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
        self.sleeptime = event.sleeptime
        self.cpuChanges = 0

    def addEvent(self, event):
        if event.stacktrace in self.events:
            self.events[event.stacktrace].sleeptime += event.sleeptime
        else:
            self.events[event.stacktrace] = event
        if event.changeCpu:
            self.cpuChanges += 1
        self.sleeptime += event.sleeptime

def toggleEvents(toggle):
    if toggle:
        ftrace.enableEvent("sched/sched_switch")
        ftrace.enableStackTrace()
    else:
        ftrace.disableEvent("sched/sched_switch")
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

def printSummary(processes, totalSleep):
    print("Total slept for %f seconds" % totalSleep)
    while processes:
        p = findSleepiestProcess(processes)
        process = processes[p]
        print("\tProcess %s-%d spent %f asleep %d cpu changes, %f percentage of total" %
                (process.comm, process.pid, process.sleeptime, process.cpuChanges, ((process.sleeptime / totalSleep)) * 100))
        while process.events:
            e = findSleepiestEvent(process.events)
            event = process.events[e]
            print("\t\tSpent %f seconds in here, %f percentage of sleep time" %
                    (event.sleeptime, ((event.sleeptime / process.sleeptime) * 100)))
            printStackTrace(event.stacktrace)
            del process.events[e]
        del processes[p]

parser = argparse.ArgumentParser(description="Track top latency reason")
parser.add_argument('infile', nargs='?', help='Process a tracefile')

args = parser.parse_args()
infile = None
continual = False

if not args.infile:
    traceDir = ftrace.getTraceDir()
    if traceDir == "":
        print("Please mount debugfs to use this feature")
        sys.exit(1)
    infile = open(traceDir+"trace_pipe", 'r')
    continual = True
    toggleEvents(True)
    signal.signal(signal.SIGINT, signalHandler)
else:
    infile = open(args.infile, 'r')

processes = {}
sleeping = {}
stacktrace = False
start = time.time()
curEvent = None
totalSleep = 0.0

for line in infile:
    trace = traceline.traceParseLine(line)
    if not trace:
        if stacktrace:
            func = traceline.parseStacktraceLine(line)
            if not func:
                continue
            if not curEvent:
                continue
            if curEvent.stacktrace == "":
                curEvent.stacktrace = func
            else:
                curEvent.stacktrace += ":" + func
        continue
    stacktrace = False
    curEvent = None

    # We can get a couple of sched events before we start to spit out the stack
    # trace so we need to pay attention to the pid in the stack trace line and
    # pick out the right event
    if traceline.isStackTrace(trace["data"]):
        if trace["pid"] in sleeping:
            stacktrace = True
            curEvent = sleeping[trace["pid"]]
        continue

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

    # idle threads all have a pid of 0, just ignore them since they don't matter
    # anyway
    if eventDict["prev_pid"] == 0:
        continue

    e = sched.SchedSwitchEvent(trace, eventDict)
    sleeping[eventDict["prev_pid"]] = e
    if continual and (time.time() - start) >= 5:
        printSummary(processes, totalSleep)
        processes = {}
        start = time.time()

printSummary(processes, totalSleep)
