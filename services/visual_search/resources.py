"""Process-local Windows job limits; never changes another process or system policy."""
import os


def restrict_compute(memory_mb=1536, cpu_percent=10):
    if not 512 <= memory_mb <= 4096 or cpu_percent is not None and not 1 <= cpu_percent <= 25:
        raise ValueError('invalid_compute_budget')
    if os.name != 'nt':
        # A Linux deployment must additionally set cgroup CPU/memory limits.
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
                  ('min_ws',c.c_size_t),('max_ws',c.c_size_t),('processes',w.DWORD),
                  ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(c.Structure):
        _fields_=[(name,c.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(c.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),('job_memory',c.c_size_t),
                  ('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
    class CPU(c.Structure):
        _fields_=[('flags',w.DWORD),('rate',w.DWORD)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.SetErrorMode(0x8003)
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise OSError('compute_job_create_failed')
    try:
        limit=Extended();limit.basic.flags=0x200|0x2000;limit.job_memory=memory_mb*1024*1024
        if not kernel.SetInformationJobObject(handle,9,c.byref(limit),c.sizeof(limit)):
            raise OSError('compute_memory_limit_failed')
        if cpu_percent is not None:
            cpu=CPU(0x1|0x4,cpu_percent*100)
            if not kernel.SetInformationJobObject(handle,15,c.byref(cpu),c.sizeof(cpu)):
                raise OSError('compute_cpu_limit_failed')
        if not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
            raise OSError('compute_job_assignment_failed')
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    # Retain this handle for the process lifetime; closing it terminates the job.
    return handle
