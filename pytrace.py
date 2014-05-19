#!/bin/python

import re
import argparse
import traceline
import syscall
import operator

def isLargest(key, haystack):
    oursum = sum(haystack[key])
    for item in haystack:
        if item == key:
            continue
        if sum(haystack[item]) > oursum:
            return False
    return True 

parser = argparse.ArgumentParser(description="Parse trace files")
parser.add_argument('infile', metavar='file', help='Trace file to process')

args = parser.parse_args()

infile = open(args.infile, "r")

calls = []
pending_calls = {}

for line in infile:
    trace = traceline.traceParseLine(line)
    if not trace:
        print("no match for '%s'" % line.rstrip())
        continue
    if syscall.isSyscall(trace["data"]):
        if syscall.isSyscallEnter(trace["data"]):
            call = syscall.Syscall(trace)
            pending_calls[trace["pid"]] = call
        elif syscall.isSyscallExit(trace["data"]):
            if trace["pid"] in pending_calls:
                call = pending_calls[trace["pid"]]
                try:
                    call.syscallExit(trace["data"], trace["timestamp"])
                    calls.append(call)
                except ValueError:
                    # do nothing, we just didn't have a match
                    pass
                del pending_calls[trace["pid"]]

call_times = {}
for call in calls:
    if call.syscall in call_times:
        call_times[call.syscall].append(call.runtime)
    else:
        call_times[call.syscall] = [ call.runtime ]

output = [["Call", "Average lat", "Min lat", "Max lat", "Total Lat", "Num of calls"]]
while call_times:
    for k in call_times.keys():
        if not isLargest(k, call_times):
            continue
        row = []
        row.append(k)
        row.append("%f" % (sum(call_times[k]) / len(call_times[k])))
        row.append("%f" % min(call_times[k]))
        row.append("%f" % max(call_times[k]))
        row.append("%f" % sum(call_times[k]))
        row.append("%d" % len(call_times[k]))
        output.append(row)
        del call_times[k]
    
col_width = max(len(word) for row in output for word in row) + 2
for row in output:
    print "".join(word.ljust(col_width)  for word in row)
