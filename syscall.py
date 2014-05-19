from traceline import TraceLine
import re
import subprocess

sys_enter_re = re.compile("sys_.*\(.*\)")
raw_sys_enter_re = re.compile("sys_enter: .*")
sys_exit_re = re.compile("sys_.* -> 0x\d+")
raw_sys_exit_re = re.compile("sys_exit: .*")

match_raw_sys_enter_re = re.compile("sys_enter: NR (\d+) \((.*)\)")
match_sys_enter_re = re.compile("(sys_.*)\((.*)\)")

match_raw_sys_exit_re = re.compile("sys_exit: NR (-*\d+) = (-*\d+)")
match_sys_exit_re = re.compile("(sys_.*) -> 0x(\d+)")
syscall_dict = {}

def isSyscall(trace):
    return trace.find("sys_") != -1

def isSyscallEnter(trace):
    m = sys_enter_re.search(trace)
    if m:
        return True
    m = raw_sys_enter_re.search(trace)
    if m:
        return True
    return False

def isSyscallExit(trace):
    m = sys_exit_re.search(trace)
    if m:
        return True
    m = raw_sys_exit_re.search(trace)
    if m:
        return True
    return False

def getSyscallName(sysnr):
    if sysnr not in syscall_dict:
        output = subprocess.Popen(['ausyscall', sysnr], stdout=subprocess.PIPE).communicate()[0]
        syscall_dict[sysnr] = output.rstrip()
    return syscall_dict[sysnr]

class Syscall(TraceLine):
    def __init__(self, trace):
        TraceLine.__init__(self, trace)
        m = match_raw_sys_enter_re.match(trace["data"])
        if m:
            self.sysnr = m.group(1)
            self.raw_format = True
        else:
            m = match_sys_enter_re.match(trace["data"])
            if m is None:
                raise ValueError
            self.raw_format = False
        if self.raw_format:
            self.syscall = getSyscallName(self.sysnr)
        else:
            self.syscall = m.group(1)
        self.args = m.group(2)
        self.runtime = 0

    def syscallExit(self, trace, timestamp):
        if not isSyscallExit(trace):
            raise TypeError
        if self.raw_format:
            m = match_raw_sys_exit_re.match(trace)
            if m is None:
                raise TypeError
            if m.group(1) != self.sysnr:
                # rt_sigreturn will show -1 for the syscall nr on return
                if m.group(1) != "-1" or self.sysnr != "15":
                    raise ValueError
        else:
            m = match_sys_exit_re.match(trace)
            if m is None:
                raise TypeError
            if m.group(1) != self.syscall:
                raise ValueError
        self.runtime = float(timestamp) - self.trace["timestamp"]
        if self.raw_format:
            self.retval = int(m.group(2))
        else:
            self.retval = int(m.group(2), 16)
