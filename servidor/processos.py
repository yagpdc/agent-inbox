"""Os processos dos agentes morrem junto com o servidor.

No Windows, matar o servidor NÃO mata os filhos: um claude.exe de execução podia ficar
rodando pra sempre (o cronômetro que o mataria vive no processo pai). Aqui os filhos entram
num job object com KILL_ON_JOB_CLOSE: quando o servidor acaba, de qualquer jeito — Ctrl+C,
Stop-Process, reinício da tarefa agendada — o Windows fecha o job e derruba todos.

Fica de fora, de propósito, o terminal que você abre pelo painel: aquela janela é sua.
"""

import ctypes
import subprocess
from ctypes import wintypes

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class _LIMITES(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _CONTADORES(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_ulonglong), ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong), ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong), ("OtherTransferCount", ctypes.c_ulonglong)]


class _INFO(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _LIMITES), ("IoInfo", _CONTADORES),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _criar_job():
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _INFO()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            return None
        return job
    except Exception:  # noqa: BLE001  (não é Windows, ou a API não deixou: segue sem job)
        return None


_JOB = _criar_job() if hasattr(ctypes, "WinDLL") else None


def adotar(proc: subprocess.Popen) -> bool:
    """Amarra o processo ao servidor. Devolve False se não deu (aí ele só segue solto)."""
    if not _JOB or proc.poll() is not None:
        return False
    try:
        return bool(ctypes.WinDLL("kernel32", use_last_error=True)
                    .AssignProcessToJobObject(_JOB, int(proc._handle)))  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False
