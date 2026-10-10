"""C1 probe (Fable v3.2 build, synthetic, only its own child processes): what killpg / kill answer for a process group
whose only member is a zombie, after it is reaped, and with a live member left in the group.

    python3 -I -S -B c1_killpg_zombie_probe.py"""
import json, os, signal, sys, time

def attempt(fn):
    try:
        fn()
        return "OK"
    except Exception as error:
        return type(error).__name__

out = {"schema": "L12HOST_V32_C1_KILLPG_ZOMBIE_PROBE", "platform": sys.platform,
       "python": "%d.%d.%d" % sys.version_info[:3]}
pid = os.fork()
if pid == 0:
    os.setsid()
    os._exit(0)
time.sleep(0.2)                                         # the session leader exited: a zombie-only group
out["killpg_group_of_one_zombie"] = attempt(lambda: os.killpg(pid, signal.SIGKILL))
out["kill_the_zombie_itself"] = attempt(lambda: os.kill(pid, signal.SIGKILL))
os.waitpid(pid, 0)
out["killpg_after_reaping"] = attempt(lambda: os.killpg(pid, signal.SIGKILL))
pid = os.fork()
if pid == 0:
    os.setsid()
    if os.fork() == 0:
        time.sleep(2)
        os._exit(0)
    os._exit(0)
time.sleep(0.2)                                         # zombie leader + one live member
out["killpg_zombie_leader_with_a_live_member"] = attempt(lambda: os.killpg(pid, signal.SIGKILL))
os.waitpid(pid, 0)
print(json.dumps(out, indent=1, sort_keys=True))
