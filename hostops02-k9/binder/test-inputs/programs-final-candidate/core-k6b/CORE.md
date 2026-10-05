# HOSTOPS02 — the frozen core (K0-min), the token family's revision — generation core-k6b (2026-10-05 UTC)

**This directory is NOT the token family's core.** It is that core (generation `32c44cf8…c644`, seal `35475b2f…d375`:
everything of 2026-10-02 plus the non-dumpable process of section 14) with one change, by Codex decision 1 (#429
5985748037) and the owner's A2 amendment 1 rev 3 (#429 5986005646): `assemble.py` carries `IN_PLACE_EDIT_EXCEPTION`,
the exact and only exception to rule 4 ("nothing that exists is overwritten"), and a rule that every other attached run
is uid 0:0. Parts and reviewed base files are byte-identical (same `PINS`); the two demonstration builds were
reassembled. Rule 4 is NOT preserved for that one row: section 15 says exactly what is allowed. Sections 1 to 14 are the
token family's text, unchanged.


Offline work only. Nothing in this directory was run on the host, pushed, or bound. Every hash named here was taken by command.
Status: built and tested by its author, then verified once by an independent pass that changed it (section 13 says what and why). Nobody else has reviewed these bytes, and the Linux job has never run. No source assembled from it may be dispatched before both have happened.

**This directory is the token family's revision of the frozen core** (section 14, 2026-10-03): a copy of the core `73fb546b9758718924b73200b48b7c0582a156a60da200ff83f4ca66e9e5c9b1` (generation `4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6`) with one function that makes the process non-dumpable (`dumps_disabled()`, `NativeRead.not_dumpable()`), the rule of the assembler that lets the core, and never an operation part, load the C library for it, and their tests. It is used by ONE operation, the token placement (`token_from_env`, revision 3, beside it as `../token_from_env`); every other operation of the tier keeps the core `73fb546b…`, which was not edited. Sections 1 to 13 are the core's own text, amended where this revision changes what they say.

| What | Value |
|---|---|
| Core generation (`CORE_SHA256` in every source, scope and receipt) | `32c44cf80e6d53e860745e52792cc917c15ccaae448aee7ba68b6aca76d3c644` = sha256 of `assemble.py` (the token family's revision, section 14; the frozen core it was copied from is generation `4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6`, and before the verification of section 13 that core was `1b3a5020…a3b1`) |
| Seal | `CORE_SHA256SUMS` (every file of this directory); check with `shasum -a 256 -c CORE_SHA256SUMS` or `python3 -B seal.py check` |
| Derived from | the frozen core `73fb546b…c9b1` (section 14), itself derived from HOSTOPS01 revision 3, seal `5609b334…71c1` (read, never modified) |
| Tests | 573 tests (121 of them the conformance suite, applied to each of the two demonstration operations; 20 of them new in section 14): 572 passed, 1 skipped on Python 3.9.6 (`/usr/bin/python3`) and on 3.12.14, with `HOSTOPS02_TEST_RELEASE_REPOSITORY` set (the skip is the real kernel's `prctl`, `tests/test_dumpable.py`, which runs on Linux only; without the variable the README argv pin is skipped as well) |
| Mutation | 558 single and 11 combined mutants (the frozen core's 537 and 11, and 21 of section 14), zero survivors, zero errors on both interpreters; 2 redundant mutants recorded as such, each dead in its pair (`mutation/MUTATION_RUN.json`, `mutation/MUTATION_RUN.py312.json`) |

Contents of this document: 1 directory · 2 delta against HOSTOPS01 · 3 date sets · 4 timeout table and budget · 5 how an operation plugs in · 6 API of the parts · 7 test harness · 8 rules · 9 mutation · 10 proven and unproven · 11 notes for the four tier 0 builders · 12 reproduce · 13 what the independent verification changed · 14 the token family's revision: the process made non-dumpable.

---

## 1. The directory

```
core/
  CORE.md  CORE_SHA256SUMS
  assemble.py        builds ONE operation directory; pins every part and base file; its own hash is the generation
  seal.py            writes the pins into assemble.py and CORE_SHA256SUMS (author only)
  delta.py  DELTA/   the delta against HOSTOPS01 as files (core.diff, two function diffs, IDENTICAL.json)
  parts/             core.py runner.py docker.py parents.py files.py lock.py     <- the shared parts, frozen
  reviewed_base/     dispatch_once.py launcher_stdin.py transport_once.py         <- HOSTOPS01's reviewed base, byte-identical
  tests/             hostemu.py oslevel.py native_child.py family.py conformance.py demos.py conftest.py test_*.py
                     demo_read/ demo_write/   two complete demonstration operations (spec.py, op.py, build/)
  mutation/          mutate.py mutants.py mutants_ported.py MUTATION_RUN*.json
  linux_root/        run.sh shapes.py report.py WORKFLOW.yml.txt   the job for a throwaway Linux runner (NOT RUN by the author)
```

**Frozen means:** `assemble.py` carries the SHA-256 of every part and of the three base files (`PINS`) and refuses to build from a file that differs (`ASSEMBLY_REFUSED CORE_CHANGED <file>`). The SHA-256 of `assemble.py` itself is written into every assembled source as `CORE_SHA256`, enters each signed scope (`SCOPE['core_sha256']`) and each receipt (`core_sha256`). A change to a part, to a base file or to `assemble.py` is therefore a new generation with new payload hashes; a source assembled earlier keeps its bytes because nothing it was built from can change under it. A later tier that needs more gets a new core directory with its own seal; this one is not edited.

**Frozen means the names too.** The operation's own part is the last text of the one module, so a name it bound again would change what the carried parts do while their bytes stay the sealed ones. `assemble.py` therefore refuses an operation part that binds a top-level name of a carried part again (an assignment, a definition, a loop target, a second `import` of a module the parts already import), that stores into or deletes from an object of the core (`COMMAND_CLASSES['RUN']['seconds']=…`, `Gate.__call__=…`), or after whose loading a data constant of the core no longer has the value the parts alone give it (`COMMAND_ENVIRONMENT.update(…)`). What a function of the operation part does to such an object at run time is not seen by the assembler: that stays with the author and the reviewer.

An operation lives OUTSIDE this directory, in its own directory with its own seal. Nothing an operation's author writes changes any byte here.

---

## 2. Delta against HOSTOPS01, file by file

Read `DELTA/` for the bytes; `python3 -B delta.py check <hostops01 candidate>` regenerates and compares them, and `tests/test_assembly.py` runs it.

| File here | Relation to HOSTOPS01 |
|---|---|
| `reviewed_base/dispatch_once.py`, `launcher_stdin.py`, `transport_once.py` | **Byte-identical** (8415e357…, 2842444e…, 5900efbf…). |
| generated `launcher_stdin.py` | **Byte-identical to the launcher HOSTOPS01 shipped** (ac4085e4…): the same five substituted lines. |
| generated `transport_once.py` | Byte-identical (5900efbf…). |
| generated `dispatch_once.py` | The same substitution table as HOSTOPS01: 18 lines for a writing source, 17 for a reading one, no line added or removed. Only the literals differ (names, date set). It does not look at `activation_allowed`; the source's own `authenticate()`, which the dispatcher runs before any claim, does. |
| `parts/core.py` | HOSTOPS01's `parts/core.py` with **18 lines removed and 60 added** (`DELTA/core.diff`; 36 in the frozen core, 24 more in the token family's revision: `import ctypes`, `PR_GET_DUMPABLE`, `PR_SET_DUMPABLE`, `dumps_disabled()`, `NativeRead.not_dumpable()`, section 14). Everything else is byte-identical: documents, pins, canonical bytes, `authenticate()` order and codes, `Gate`, pinned parents (`walk_pinned`, `Pinned`, `probe`, `descend`, `count_entries`, `read_regular`, `boot_id_sha256`), `Effects`, `mutate`, `seal`, `run`. The changes: (1) `READ_DATES`/`WRITE_DATES` replaced by `EPOCH_DAYS` and `DATE_SETS` (section 3); (2) the three `activation_allowed` comparisons are with the source's `ACTIVATION_ALLOWED` instead of the literal `False`; (3) the refusal code `EVIDENCE_PRECHECK_MISSING` is `EVIDENCE_OPERATION_MISSING` (the required operations are the source's own `EVIDENCE_OPERATIONS`); (4) `strict(raw,limit=65536)` takes a limit (compose renders are larger than a document); (5) `envelope()` adds `core_sha256`; the minimum receipt of `seal()` keeps `core_sha256`, `activation_performed`, `daemon_reload_performed` as they were instead of forcing them to False; (6) the last-resort handler of `run()` says `None` for those two members when a source that may switch a unit escaped after it started; (7) new `timing()`; (8) two docstrings. |
| `parts/runner.py` | **New runner** (section 4, 6.2). Byte-identical to HOSTOPS01's `parts/runner.py`: `trusted_executable()`, `binary()`, `COMMAND_ENVIRONMENT`, `MAX_TOOL_TIMEOUTS`. Rewritten: `NativeRunner.run()` (standard input, per-call time and output limit, two variables, working directory `/`, `NotStarted`, a session and process group of its own for the command and a kill of that group when the call does not end by the command's return), `Commands` (dict rows with prefix, middle, tail, class, kind, stdin; the budget rule; `STARTED_THROUGH`), new `effect()`, `effects_budget()`, `command_row()`. The image helper moved to `docker.py`. |
| `parts/docker.py` | New file. Byte-identical to HOSTOPS01's `parts/runner.py`: `IMAGE_FORMAT`, `image_facts()`, `REVISION_LABEL`, `REFERENCE`, `MAX_TAGS`. Byte-identical to the read-only post-deploy family (rev 4, rev 5): `CONTAINER_FORMAT`, `PS_FORMAT`. New: container helpers, the attached run, compose. |
| `parts/files.py` | New file. `remove_own_temporary()`, `number()`, `TEMPORARY` are byte-identical to `op_install_units.py`. `create_file()` is `install_unit()` with the mode, the path and the key as arguments and a request check before anything (`DELTA/files.create_file.diff`). `create_directory()` is `op_provision.py`'s with the mode, key and path as arguments (`DELTA/files.create_directory.diff`). New: `readback_file()`, `readback_directory()` (the bodies of the two in-run readbacks), `file_request()`, `named_in()`, `objects_left()`, `NativeFiles`. |
| `parts/parents.py` | New file. `world_writable_without_sticky()` is byte-identical to `layout.py`; `row_accepted()` and `validate_chain()` are `layout.py`'s rule with the data volume generalised to an "open root" named by the request. New: `chain_effects()`, `stat_signature()`, `free_bytes()`. |
| `parts/lock.py` | New file (the deployment lock). |
| NOT carried | `layout.py`, `listing.py`, `scan.py`, `render.py` and the four operation parts. Tier 0 needs none of them. |
| `tests/hostemu.py` | HOSTOPS01's emulation with: template functions `eq ne or and not split lower len`, assignment with `=`, else-if; `container inspect`, `ps -a`, an attached `run`, `compose config` and `compose up`; standard input, variables and limits in `FakeHost.run`; `flock`, `pause`; `absent`, `hang`, `hang_after`. `world()` is the host of this epoch (section 7.2). |
| `tests/oslevel.py` | HOSTOPS01's file plus the recording of `fcntl.flock`. |
| `tests/family.py`, `tests/conformance.py` | HOSTOPS01's `tests/family.py` and `tests/test_family.py` made independent of the operation. |
| `mutation/mutants_ported.py` | The 269 rows of HOSTOPS01's mutant list whose anchor still occurs exactly once (128 core, 119 files, 12 dispatcher, 5 runner, 4 launcher, 1 docker); 268 are used (one runner row no longer fits the new call and is rewritten as `R43`). |

---

## 3. Date sets

`request.date` is signed and must be one of the source's code set; all six instants of the three documents must lie on that UTC day; the dispatcher carries the same literal and requires `request.date` to be the day of its window (both layers, tested). An instant is written as `datetime.isoformat()` writes it in UTC (`2026-10-05T08:26:00+00:00`): other spellings (`+00`, the basic format) are accepted by Python 3.12 and refused by 3.9, and the dispatcher and the host need not run the same interpreter (attacked on both; unchanged from HOSTOPS01). **A window lies wholly on one UTC day.** A UTC day runs from 21:00 BRT of the previous day to 20:59:59 BRT: no gate crosses 21:00 BRT.

A source does not write its own dates. It names one class of the core's table:

```python
DATE_CLASS='WRITE_FIRST_SESSION'
DATES=DATE_SETS[DATE_CLASS]
```

| Class | UTC days | For |
|---|---|---|
| `READ` | 2026-10-02 … 2026-10-10 (nine days) | every source whose `WRITES_ALLOWED` is False (a read source that runs a read-only container is still `READ`) |
| `WRITE_WEEKEND` | 10-02, 10-03, 10-04 | what must be over before the first-session day begins (Sunday 21:00 BRT): catalog initialisation |
| `WRITE_FIRST_SESSION` | 10-05 only | install_release and activate |
| `WRITE_SESSIONS` | 10-05 … 10-10 | daily writes and the end of the epoch (Friday after 21:00 BRT is 10-10 UTC) |
| `WRITE_EPOCH` | 10-03 … 10-10 | a write that may fall on the weekend or on a session day |

`assemble.py` refuses a source whose `DATES` is not `DATE_SETS[DATE_CLASS]`, a reading source with another class than `READ`, and a writing source with `READ`. The gate may not be longer than `MAX_GATE_SPAN_SECONDS`, which the source sets: at most 900 for a writing source, at most 3600 for a reading one (refused above that).

---

## 4. Timeout table and budget

Limits that do not move: payload 60 s (`MAX_SECONDS`, a monotonic deadline from authenticated entry), dispatcher watchdog 80 s, transport 270 s. Nothing may park or wait long.

Every row of a source's `COMMANDS` table names one class. The table is part of every signed scope (`SCOPE['command_classes']`).

| Class | Seconds | Captured bytes | For |
|---|---|---|---|
| `QUICK` | 8 | 65,536 | inspect, ps, info, version, `systemctl show` (HOSTOPS01's single limit) |
| `RENDER` | 15 | 1,048,576 | `docker compose config` (it prints every service) |
| `RUN_SHORT` | 20 | 65,536 | an attached container that runs a short pinned snippet |
| `RUN` | 40 | 65,536 | an attached container that imports the application (the catalog initialisation's 40 s) |
| `RECREATE` | 30 | 65,536 | `docker compose up` of one service (the whole activation of 28/09 took 23 s) |
| `SWITCH` | 30 | 65,536 | a systemctl verb that changes a unit or reloads the manager |

A command never runs longer than its class and never past the budget (`min(class seconds, gate())`). The command leads a session and a process group of its own. When a call does not end by the command's return (the time limit, the output limit, an expiry), the runner kills that whole group with SIGKILL: the docker CLI **and** what it started as a process, so a compose plugin does not go on recreating a service after the run has sealed its receipt and released the deployment lock. It reaches nothing else: not the container an attached `docker run` created (the engine keeps it until its own process ends, and `--rm` removes it then), not a process that left the group, nothing the engine does on its own. A command that returned is reaped and nothing is killed.

Every row also has a **kind**:

| Kind | Meaning | Started through |
|---|---|---|
| `READ` | changes nothing | `commands.call()` / `commands.output()`; the one row whose template comes at call time (`container_environment`) only through `container_environment()` |
| `CONTAINER` | an attached `docker run` that creates and removes one container with read-only binds only | `container_run()` only |
| `EFFECT` | changes the host or the engine; exists only where `WRITES_ALLOWED` is True | `effect()`, `container_effect()`, `compose_up()` only |

A row started any other way is refused before a process exists (`NotStarted('COMMAND_KIND')`, tested), and the operation part cannot pose as a helper (`through=` is refused by `assemble.py`). So a `CONTAINER` run always has its image by ID and no bind it can write through, every `EFFECT` is counted, and no template but the boolean one reaches `docker inspect`. (An `EFFECT` run has its image by ID when it goes through `container_effect()`, the helper that builds its arguments; use no other way.)

**The budget rules** (all tested):

1. A `CONTAINER` or `EFFECT` command is not started unless `gate() >= class seconds + AFTER_EFFECT_RESERVE_SECONDS` (4 s). Otherwise `NotStarted('COMMAND_NOT_STARTED_BUDGET')`: nothing ran. A command killed by the budget would leave its effect unknown.
2. `effects_budget(*row_names)` = sum of the classes of the named rows + one reserve. **Before its first effect a run checks `gate() >= effects_budget(every CONTAINER/EFFECT row still to run) + its own allowance for files and reads`, and refuses otherwise.** This is the last refusal that costs nothing on the host. The allowance must cover every `READ` command that runs between the first creation and the last effect: rule 1 is applied again when each later effect starts, and a refusal there (`COMMAND_NOT_STARTED_BUDGET`) comes after something was created, so the run is PARTIAL (`tests/test_demo_write.py`, "an effect that does not fit any more"). Section 11 has the figures for K6a.
3. `acquire_lock(host,fd,gate,wait_seconds,keep_seconds)` waits at most `wait_seconds` (≤ 20) and never past the point where less than `keep_seconds` would be left. Pass the figure of rule 2 as `keep_seconds` and take the lock **before** the first creation: a busy lock is then a refusal with nothing changed.
4. A `READ` command has no such rule: it runs with whatever is left.

---

## 5. How an operation plugs in

### 5.1 The operation directory

```
hostops02/<key>/            (anywhere; conventionally a sibling of core/)
  spec.py                   assembly specification
  op.py                     the operation's own part
  build/                    written by assemble.py, never edited
  tests/                    conftest.py puts <core>/tests on sys.path
  mutation/                 a copy of core/mutation/mutate.py with three tables changed, and its own mutants.py
```

```
python3 -B <core>/assemble.py <operation directory>            # (re)writes build/, prints ASSEMBLY.json
python3 -B <core>/assemble.py --check <operation directory>    # BUILD_EQUAL, exit 0; BUILD_DIFFERS ..., exit 1
python3 -B <core>/assemble.py --core                           # verifies the frozen core, prints the generation
```

`build/` holds: `<MODULE>.py` (**the ONE payload source**: header, a generated seal block, the shared parts in the fixed order between marker lines, the operation's part, the footer), `dispatch_once.py`, `launcher_stdin.py`, `transport_once.py`, `REQUEST|AUTHORITY|GO|DISPATCH|PUBLICATION_PROOF.UNBOUND.json`, `FINAL_PAYLOAD.UNBOUND.py`, `DISPATCH_SCOPE_DELTA.diff`, `LAUNCHER_DELTA.diff`, `ASSEMBLY.json`. It is the same set of files a HOSTOPS01 operation directory holds (for the binder), with the same key sets in every document. Differences a binder must know: `activation_allowed` is the source's constant (not always false); `evidence` must name each of the source's `EVIDENCE_OPERATIONS`; the date set is the source's class. No output depends on where either directory lies (tested: a copy elsewhere yields the same bytes).

### 5.2 `spec.py`

```python
NAME='install_release'                 # [a-z][a-z0-9_]{1,30}; the block label is OP_<NAME>
MODULE='install_release'               # build/<MODULE>.py; not dispatch_once, launcher_stdin, transport_once, spec, op
STEM='HOSTOPS02_INSTALL_RELEASE'       # HOSTOPS02_[A-Z][A-Z0-9_]{1,40}
PARTS=['core','runner','docker','parents','files']   # 'core' first, in the order core runner docker parents files lock; docker needs runner
HEADER='''"""OP_...: one paragraph that says what the source does and never does. ... No action on import.
"""
'''                                    # one docstring, ASCII, must contain the sentence "No action on import."
def unbound_plan(module):              # exactly module.PLAN_KEYS, every open value None
    return {...}
SUCCESS_IN_TEMPLATE=True               # optional; False when the success outcome follows a signed mode (GO template carries null)
```

### 5.3 `op.py` — what the part must define

ASCII only; Python 3.7 syntax (no `:=`, no positional-only parameters; checked best-effort); no marker line (`# ==== `). Names of the shared parts are simply in scope (one module), and they stay the core's:

- it may `import base64` and nothing else: a module the parts already import (`json`, `re`, `stat`, `errno`, `hashlib`, …) is used, not imported again; and it never imports `subprocess`, `selectors`, `signal`, `fcntl`, `time` or `ctypes` in any form (`import x as y`, `from x import y`: section 14);
- it binds no top-level name of a carried part and stores into no object of the core (section 1); pick other names for its own constants (`IMAGE_ID`, `REFERENCE`, `CODE`, `FILE_NAME`, `TEMPORARY`, `MAX_SECONDS` and about 170 others are taken; the refusal lists the clash);
- it makes no system call and starts no process of its own: it never names `subprocess`, `selectors`, `signal`, `fcntl`, `time` or `ctypes`, and of `os` only the open flags (`os.O_…`). Everything goes through `host` (the `Native` mix-ins) and the functions of the parts; the clock is the `clock` and `monotonic` that `perform` receives;
- it never passes `through=` (that is how the helpers of the core identify themselves to `Commands`).

```python
OPERATION='GO_WRITE_HOSTOPS02_<NAME>_<NN>'        # GO_READONLY_HOSTOPS02_... for a reading source
PHASE='WRITE_...'                                 # READONLY_... for a reading source
REQUEST_SCHEMA='WRITE_<STEM>_REQUEST_V1'          # READONLY_<STEM>_... for a reading source; AUTHORITY, GO, RECEIPT likewise
AUTHORITY_SCHEMA=...; GO_SCHEMA=...; RECEIPT_SCHEMA=...
PLAN_SCHEMA='<STEM>_PLAN_V1'
SOURCE_NAME='<MODULE>.py'
WRITES_ALLOWED=True                               # one flag per source: no source mixes read and write modes
ACTIVATION_ALLOWED=False                          # True only where a systemd unit is switched (rule 8.2)
DATE_CLASS='WRITE_FIRST_SESSION'; DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_...',)          # operation names the request must cite at least once each; () is allowed
MAX_GATE_SPAN_SECONDS=900                         # <= 900 write, <= 3600 read
COMPLETE_OUTCOME='...'; PARTIAL_OUTCOME='...'; REFUSED_OUTCOME='...'; REDUCED_OUTCOME='...'; ESCAPED_OUTCOME='...'
PLAN_KEYS=frozenset((...))                        # the operation's own plan keys (not the seven common ones)
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}      # only with the runner; docker and systemctl are the only tools
COMMANDS={'image':command_row(...), ...}                              # only with the runner; section 6.2
SCOPE_STATEMENT='...'                             # the constant sentence the GO must carry
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,          # these five: the objects themselves,
       'command_environment':COMMAND_ENVIRONMENT,'command_variables':COMMAND_VARIABLES,    # only with the runner
       'never':[...],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT, ...},
       ...}                                       # plus whatever the signers must see: FILES_SCOPE, LOCK_SCOPE, side effects, paths
SCOPE_SHA256=sha(canonical(SCOPE))
class Native(NativeRead,NativeRunner,NativeFiles,NativeLock): ...    # exactly the mix-ins of the parts carried; a reading source: no NativeFiles
def validate_plan(plan): ...                      # raises Refused(code) for every member that is not as it must be; pure
def effects_of(plan): ...                         # the literal object the authority and the GO carry; recomputed and compared
def success_of(plan): ...                         # the one outcome that counts as success for that request
REDUCTIONS=[('NAME',function(receipt)), ...]      # flagged reductions when a receipt exceeds 60000 bytes; may be []
def perform(plan,gate,host,bound,clock,monotonic,state): ...   # returns seal(envelope(...)); never raises for a refusal
```

`run()`, `authenticate()`, `Pins`, `Gate`, `Effects` come from the core. The launcher calls `run()`; the dispatcher calls `authenticate()` locally before any claim, so a malformed plan cannot spend the GO.

### 5.4 The shape of `perform` (copy it from `tests/demo_write/op.py` or `tests/demo_read/op.py`)

```python
def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    ...pure work: decode the signed bytes, compute what will be compared...
    gate()                       # FIRST gate call, before anything is observed (a dry gate that raises must stop here)
    state.started=True
    commands=Commands(host,gate); go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            ...,**extra)))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')        # first, before anything is looked at
            host.umask(0o077)                                              # writing sources
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            ...EVERYTHING is looked at here: chains walked and held, destinations proved absent, images, containers,
               renders, the lock taken (rule 4.3), the budget (rule 4.2)...
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        ...effects, each read back inside the run; from here on nothing refuses unless nothing has changed...
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)     # nothing succeeded, nothing uncertain
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        ...release the lock, close every Pinned...
```

A reading source observes each item on its own (`observe()` in `demo_read/op.py`): a failed observation is `safe(error)` (`UNAVAILABLE` with a constant code), never an absence; a mismatch is a finding that leaves every other item in the receipt; `GO_EXPIRED` and `CLOCK_REVERSED` stop the run. Exit 0 exists for one outcome only.

### 5.5 Envelope (the transport fixes three status strings; the meaning is in `outcome`)

| Exit | status | Verdict | When |
|---|---|---|---|
| 0 | `METADATA_ONLY_REQUIRES_REVIEW` | KNOWN_COMPLETE | only the success outcome |
| 2 | `PARTIAL_METADATA_REQUIRES_REVIEW` | KNOWN_PARTIAL | a read that is incomplete or found a mismatch; a write that changed something and did not finish, or whose effect is uncertain |
| 1 | `REFUSED` | KNOWN_REFUSAL | nothing observed (read) / no mutating call succeeded and none is uncertain (write) |
| 3 | anything that escapes `run()` | UNCERTAIN | state unknown |

Receipt members every source gets from `envelope()`/`seal()`: `schema operation status outcome code scope_sha256 core_sha256 activation_performed daemon_reload_performed secret_bytes_in_receipt ready size_reductions metadata_sha256`, and from `bound`: `request_sha256 authority_sha256 go_sha256 payload_sha256 host_binding_sha256`. A receipt is at most 60,000 bytes (the dispatcher decodes 65,536); `seal()` applies `REDUCTIONS` in order, flags each, and a reduced receipt is never complete.

---

## 6. API of the parts

`host` is the source's `Native()` in production and `hostemu.FakeHost` in tests. `gate` is the `Gate` object: calling it checks the window and the 60 s deadline and returns the seconds left. Every function below raises `Refused(CODE)` (a `ValueError` whose text is a constant code) unless it says otherwise.

### 6.1 `core` (always carried)

Documents and values: `canonical(value)->bytes`, `sha(bytes)->hex`, `strict(raw,limit=65536)` (JSON, duplicate keys and non-finite numbers refused), `decode(raw)` (an object), `document(raw)` (an object in its canonical bytes), `exact(value,keys,code)`, `instant(text)` (UTC only), `text(value,pattern)` (fullmatch on a `str`), `integer(value,low=0,high=None)` (never a bool), `hexpin(value)` (64 hex, not zero), `clean_path(value)`, `inside(path,root)`, `prefixes(path)`, `kind(mode)`, `shape(stat)`, `code_of(error,fallback)`, `safe(error)`, `attempt(action)`, `combined(items)`, `timing(begun,mark,clock,monotonic)`.

Pinned parents — an existing directory is never assumed; every component from `/` is a signed row `{path,device,inode,uid,gid,mode}` copied from a read-only receipt of the same boot:

- `chain_rows(rows,path)` — shape only (one row per component, six integer members).
- `walk_pinned(host,rows,gate,observed,compare_device=True) -> fd` — opens `/` and each component by `dir_fd`, `O_NOFOLLOW|O_NOATIME`; an `lstat` classifies each component first; the held descriptor must equal the row on all five values. Codes: `PARENT_MISSING`, `PARENT_SYMLINK_COMPONENT`, `PARENT_NOT_DIRECTORY`, `PARENT_CHANGED_DURING_WALK`, `PARENT_IDENTITY_MISMATCH`. `observed` receives the rows as read.
- `Pinned(host,fd,rows=rows)` or `Pinned(host,fd,parent=pinned,name=name)`; `.fd`, `.identity`, `.verify(gate)` (walks again; `PARENT_REPLACED`), `.close()`.
- `probe(host,path,gate) -> {'status':'COMPLETE','exists':False,'absent_at':...}` or `{'exists':True,'type','uid','gid','mode_octal','device','inode','links'}`; through a symbolic link nothing is said to be absent (`status UNAVAILABLE`).
- `descend(host,path,gate,rows=None) -> fd` (no expectation; fills `rows` in the signed format), `count_entries(host,fd,gate,limit=4096)`, `mount_point_of(rows)`, `row_of(path,stat)`, `row_root_safe(row)`.
- `read_regular(host,name,dir_fd,gate,limit) -> (bytes,stat)` — `FILE_NOT_REGULAR`, `FILE_TOO_LARGE`, `FILE_CHANGED_DURING_READ`; an absent name raises `FileNotFoundError`.
- `boot_id_sha256(host,gate)`.

The process (section 14): `dumps_disabled(library=None) -> True` — `prctl(PR_SET_DUMPABLE, 0)` must return 0, then `prctl(PR_GET_DUMPABLE)` must answer 0 (`PR_GET_DUMPABLE=3`, `PR_SET_DUMPABLE=4`); anything else is `Refused('PROCESS_DUMPABLE_NOT_DISABLED')`. Without `library` it loads the C library of the interpreter, `ctypes.CDLL(None, use_errno=True)`, inside the function, and never hands it out. `host.not_dumpable()` (`NativeRead`) is that call: make it the first call of the precheck of a source that reads a secret, before anything is opened. It changes the process, not the host: it is not a mutating call (not through `mutate()`).

Effects: `state=Effects()` (`issue done fail unknown`, `clean()`, `counts()`, `pending`, `started`); `mutate(state,gate,action)` is the only way a mutating system call is made (gate, count, call; an `OSError` of the call means it changed nothing). `filesystem_code(error)`. `digests(...)`, `envelope(status,outcome,code,bound)`, `seal(receipt)`.

### 6.2 `runner`

```python
command_row(tool,argv,middle,klass,kind,tail=(),stdin=False)
#   tool    key of BINARIES (the binary is taken only if every directory above it and the file are root-owned and closed to group and other)
#   argv    fixed prefix;  tail  fixed suffix;  middle  a sentence describing what a call puts between them, None when a call adds nothing
#   klass   a key of COMMAND_CLASSES;  kind  READ | CONTAINER | EFFECT;  stdin  whether a call gives bytes on standard input
commands=Commands(host,gate)
commands.call(name,*middle,capture=True,docker_config=None,stdin=None,variables=None) -> (returncode,bytes)                  # READ rows with a fixed template only
commands.output(name,*middle,docker_config=None,stdin=None,variables=None) -> bytes        # CommandFailed('COMMAND_FAILED',returncode) unless 0
commands.calls; commands.started -> {'READ':n,'CONTAINER':n,'EFFECT':n}
effects_budget(*row_names) -> seconds
effect(state,commands,name,*middle,capture=False,docker_config=None,stdin=None,variables=None) -> dict
```

The child gets: the fixed environment `PATH=/usr/bin:/bin LANG=C LC_ALL=C` (nothing inherited, no `HOME`), plus `DOCKER_CONFIG` when `docker_config` is given and `C3PO_BUILD_SHA` when `variables={'C3PO_BUILD_SHA':<40 hex>}` is given — no other variable exists; working directory `/`; a session and a process group of its own; stderr to `/dev/null` (never read, never echoed); standard input `/dev/null` or the bytes (at most 131,072, written and then closed). Input and output are moved by one `select` loop on non-blocking pipes, so neither a child that never reads nor one that floods its output can block the run.

`NotStarted` (a subclass of `Refused`) is raised only while no process was created: the row refused the call (`COMMAND_ARGUMENTS`, `COMMAND_STDIN`, `COMMAND_VARIABLES`, `COMMAND_KIND` — also for a `CONTAINER`, `EFFECT` or call-time-template row that was not started through its helper), `BINARY_UNAVAILABLE_OR_UNSAFE`, `COMMAND_SKIPPED_AFTER_TIMEOUT` (a tool that timed out twice is not started again), `COMMAND_NOT_STARTED_BUDGET`, `COMMAND_NOT_STARTED` (the process could not be created), or an expired gate before the start. After a process existed: `Refused('COMMAND_TIMEOUT')`, `Refused('COMMAND_OUTPUT_LIMIT')`, `Refused('GO_EXPIRED')`.

`effect()` returns `{'started','returned','returncode','output','code'}` and never raises for a failed command:

| started | returned | Settled by `effect()` | The caller |
|---|---|---|---|
| False | False | `state.fail()` — nothing ran, nothing changed | may still refuse (`state.clean()` unaffected) |
| True | False | `state.unknown()` — timeout, expiry, any failure after the process existed | reads back if it can; the run can no longer be a refusal |
| True | True | **not settled** (`state.pending`) | reads the result back, then calls exactly one of `state.done()`, `state.fail()` (a read proved nothing changed), `state.unknown()`. An unsettled call counts as uncertain |

### 6.3 `docker` (needs `runner`)

Rows a source copies into its `COMMANDS` (the row NAMES `image`, `container`, `container_list`, `container_environment` are fixed; the others are free):

```python
'image':                 command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ')
'container':             command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ')
'container_list':        command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ')
'container_environment': command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ')
'<any>': command_row('docker',RUN_PREFIX,'<what the middle is>','RUN_SHORT' or 'RUN','CONTAINER' or 'EFFECT',stdin=True)
'<any>': command_row('docker',['compose'],'--project-name, --env-file and the signed -f list','RENDER','READ',tail=COMPOSE_CONFIG_TAIL)              # render from files
'<any>': command_row('docker',['compose'],'... the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True)   # render with -f -
'<any>': command_row('docker',['compose'],'--project-name, --env-file and the signed -f list','RECREATE','EFFECT',tail=compose_up_tail('r2d2-worker'))
```

- `image_facts(commands,reference,docker_config=None) -> {'id','repo_tags','repo_tag_count','repo_tags_all_valid','reference_among_repo_tags','revision_label'}` — by ID or by reference; `COMMAND_FAILED` when absent.
- `container_facts(commands,target,expected_name=None,docker_config=None) -> {'name':'/<name>','id','image_id','image_reference','running','state','started_at','host_pid','restarts','health'}` — `target` a name or a 64-hex ID; the answer must be that container (`CONTAINER_METADATA_INVALID`).
- `container_list(commands,docker_config=None) -> [{'id','name','state'}]` sorted by ID, every container (`ps -a`), at most 128; a failed listing is never an empty list.
- `container_environment(commands,container_id,expected,docker_config=None) -> {NAME:{'present':bool,'equal':bool}}` — `expected` is `{NAME:VALUE}` (1 to 16 names; value grammar `[A-Za-z0-9_./:@+=-]{0,256}`). Booleans only; the compared values travel in the argv of the docker CLI, so **never pass a secret as expected**. By ID only.
- `RUN_PREFIX` = `run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges` (the supervisor README's catalog argv, option for option). A row may carry another prefix as long as it begins `run --rm`, has `--pull never`, and has no `-d`, `--privileged`, `-v`, `--mount`, `--device` or `--cap-add` (binds come at call time, through `run_arguments`). The emulation knows only the options of `RUN_PREFIX` and `--name`; another prefix needs a subclass of it in the operation's tests.
- `run_arguments(row,image_id,mounts,command,container_name=None)` — the middle: `[--name N] (--mount type=bind,source=S,target=T[,readonly])* IMAGE-ID COMMAND...`. `mounts` is a list of `{'source','target','read_only'}` (at most 4; paths `/[A-Za-z0-9._/-]+`, clean; one bind per target); the image is an ID, never a reference; command words `[A-Za-z0-9_./:@+=-]{1,200}`, at most 16, the first not an option. A `CONTAINER` row refuses a bind that is not read-only (`MOUNT_NOT_READ_ONLY`). Use it in `validate_plan` to refuse a bad plan before anything. Bind only directories the run has walked and holds pinned: a read-only bind of a socket or of a directory that holds one still lets the container talk to it.
- `container_run(commands,row,image_id,mounts,command,stdin,docker_config=None,container_name=None) -> dict` (the dict of `effect()`; `CONTAINER` rows only; never raises for a failed command). **A run that started and did not return may have left its container**: the timeout kills the docker CLI, the engine keeps the container until its process ends. The helper does not look; a caller that wants its receipt to say so calls `container_list()` before and after and reports whether a container exists that was not there (with `container_name`, whether that name exists). `container_effect(state,commands,row,...)` is the same through an `EFFECT` row, counted, settled by the caller.
- `RUN_ENGINE_STATUSES=(125,126,127)` — docker's own exit statuses (the engine could not run the container).
- `single_line(raw) -> dict` — exactly one JSON object on one line (`RUN_OUTPUT_NOT_ONE_LINE`).
- `compose_arguments(project,env_file,files,standard_input_last=False)` — `--project-name P --env-file E -f F1 [-f F2 ...] [-f -]`: **always an explicit file list**; absolute clean paths; 1 to 4 files, no repeats.
- `compose_render(commands,row,project,env_file,files,build_sha,override=None,docker_config=None) -> dict` — `config --format json`; with `override` (bytes) the row must take standard input and `-f -` is appended. `C3PO_BUILD_SHA=build_sha` is always passed (compose.yml defaults it to `development`). `COMPOSE_RENDER_INVALID`, `COMMAND_FAILED`. **The result carries every value of the environment file.**
- `compose_service(rendered,service) -> {'image':str,'environment':{name:str|None}}`.
- `compose_up(state,commands,row,project,env_file,files,build_sha,docker_config=None) -> dict` — the recreate of 28/09, word for word (`up -d --no-deps --no-build --pull never --force-recreate <service>`, the service in the row's tail); an `EFFECT`, output not captured, settled by the caller after it has read the containers back.

### 6.4 `parents`

- `validate_chain(rows,path,open_root=None,receives_entry=False) -> rows` — outside `open_root` every component must be root-owned and not writable by group or other (`CHAIN_ROW_UNSAFE`); at and below `open_root` (a directory the request names as owned by an operational account: the data volume root, the deploy tree) the observed owner and mode are accepted as signed, except a directory any user can write to without the sticky bit (`CHAIN_ROW_WORLD_WRITABLE`); with `receives_entry` the last row must not be setgid (`PARENT_SETGID`).
- `chain_effects(rows) -> {'path','row','chain_sha256','mount_point_by_device_change'}` — what goes into `effects_of`.
- `stat_signature(stat)` — identity, size, both change instants, owner, mode: "the same object, unchanged" without reading it. In memory only.
- `free_bytes(host,fd)` — `f_bavail * f_frsize` on a held descriptor.

### 6.5 `files` (writing sources only)

- `create_directory(key,path,mode,parent,host,gate,state,handles) -> row` — one `mkdir` by descriptor in a `Pinned` parent, proved, fsynced; `mode` 0o700 only; the held directory is `handles[key]` (close it in `finally`). States `NOT_ATTEMPTED NOT_CREATED CREATED_UNVERIFIED CREATED_METADATA_MISMATCH CREATED_NOT_EMPTY CREATED_NOT_DURABLE CREATED_DURABLE`; success is `CREATED_DURABLE`.
- `create_file(index,key,path,content,mode,directory,host,gate,state,go16) -> row` — exclusive temporary `.hostops-<go16>-<index>.partial`, unbuffered writes, fsync, exact metadata (regular, one link, 0:0, the mode, the size, the directory's device), `link` to the final name (never replaces), fsync of the directory, removal of the temporary proved by identity, fsync. `mode` 0o600 or 0o644; `index` 0 to 99, distinct per file of a run; `go16=bound['go_sha256'][:16]`. States `NOT_ATTEMPTED NOT_CREATED TEMPORARY_ONLY LINKED_TEMPORARY_PRESENT INSTALLED_NOT_DURABLE INSTALLED_DURABLE`; success is `INSTALLED_DURABLE`. The row carries the hash and the size of the bytes: **not for a secret**.
- `readback_file(row,content,mode,directory,host,gate) -> None | code`, `readback_directory(path,mode,handle,host,gate,entries) -> None | code`.
- `file_request(name,content_sha256,size,mode) -> bool` for `validate_plan`; `objects_left(directory_rows,file_rows)`; `FILES_SCOPE` for the scope.
- The caller sets the umask first (`host.umask(0o077)` for 0600 and 0700; `0o022` for 0644) and proves the final name absent in its precheck.

### 6.6 `lock`

- `fd=open_lock(host,name,directory,gate)` — the lock file by `dir_fd` in a `Pinned` directory, read-only, no link followed, never created (`LOCK_FILE_ABSENT`, `LOCK_FILE_NOT_REGULAR`, `LOCK_FILE_REPLACED`).
- `acquire_lock(host,fd,gate,wait_seconds,keep_seconds) -> attempts` — exclusive, non-blocking, again every 0.25 s; `DEPLOY_LOCK_BUSY`, `LOCK_NOT_TAKEN_BUDGET`, `LOCK_UNAVAILABLE`. Changes nothing on disk.
- `lock_still_named(host,name,directory,fd) -> bool`, `release_lock(host,fd)` (unlock and close, never raises), `probe_lock(host,fd) -> 'FREE' | 'BUSY'` (a shared, non-blocking request released at once: for a reading source), `LOCK_SCOPE`.
- On this host: `/opt/chief-of-staff-digital/runtime/security/deployment.lock`; the pipeline's deploy job (`flock -w 120`) and the security controller take it exclusively.

---

## 7. Test harness

An operation's `tests/conftest.py`:

```python
import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','core','tests'))
```

Run with both interpreters: `python3 -B -m pytest -p no:cacheprovider -q tests` (`/usr/bin/python3` 3.9 and the 3.12 environment).

### 7.1 `family`

```python
k=family.load(<operation directory>)     # k.m the source module, k.d dispatcher, k.l launcher, k.t transport, k.source bytes, k.name, k.dir (build/), k.report
host=family.world(k)                     # hostemu.world() wired to the source's Refused and NotStarted
docs=family.Docs(k,fields,now=None,minutes=5,evidence=None)   # fields: the operation's own plan keys, built from the emulated host as a binder would
docs.plan / docs.request / docs.authority / docs.go           # mutate, then docs.chain() to keep the hash chain
docs.authenticate(**options); docs.run(host,**options); docs.perform(host,gate=...,state=...); docs.go16()
family.moment(k)                         # 17:00 UTC on the first day of the source's date set (the default `now`)
family.refusal(action) -> code;  family.Untouchable();  family.sealed(receipt);  family.line(receipt)
family.Budget(now,command_seconds=0).attach(host).cost(seconds,*argv_words)   # then docs.run(host,**budget.options()): time passes with commands and lock pauses
family.Dispatch(docs,tmp_path)           # .prepare() .proof(intent) .resume(publication,transport) .claims() .fake(out=...,status=...)
family.assembler()                       # core/assemble.py as a module: .build(directory) -> {file name: bytes}, .lint(spec,source,module) -> [broken rules]
```

### 7.2 `hostemu` — how to fake the host

`host=hostemu.world()` is the host before any operation of the epoch: Docker 29.5.3 (containerd snapshotter), systemd 255, the compose project `c3po` under `/opt/chief-of-staff-digital` (`.env` 0600, `c3po/compose.yml`, `.deploy-version`, `runtime/security/deployment.lock`, all owned by uid 1000), eight running compose containers (`c3po-api-1` … `c3po-r2d2-worker-1`, `c3po-web-1`, `c3po-db-1`), three production images and a rollback tag, the data volume `/mnt/day-d-data` (1000:1000, its own device) with the pin `.r2d2-v2-pinned`, nothing of the supervisor. `hostemu.provision_supervisor(host)` adds what supervisor operation 2 leaves under placement A. Constants: `DATA DEPLOY PROJECT ENV_FILE COMPOSE_FILE LOCK_DIRECTORY LOCK_NAME PIN WORKER SERVICES BACKEND WEB DATABASE REVISION BOOT SECRET ROOT_DEVICE DATA_DEVICE`. Every number, ID and value is synthetic.

| To fake | Do |
|---|---|
| a path | `host.tree.add(path,kind='dir'|'file'|'symlink'|'fifo',uid=,gid=,mode=,dev=,ino=,content=b'')` (parents are created root 0755); `host.tree.get(path)` returns the node (`.uid .gid .mode .dev .ino .nlink .content .children .mtime .ctime`), `host.tree.remove(path)`, `host.tree.snapshot()` |
| signed rows | `hostemu.rows(host,path)` |
| the executor | `host.actor=(uid,gid)` |
| what created objects look like | `host.mask`, `host.creator=(uid,gid)`, `host.grpid`, `host.created_device`, `host.readonly=True` (EROFS) |
| a failure or a death at any call | `host.hook=lambda host,name,detail,calls: ...` — raise `OSError(errno,...)`, any exception, or `hostemu.Death` at call number `calls` or for a call `name` (`open fstat lstat read names fstatvfs readlink umask mkdir create write fsync link unlink flock pause run`) |
| a command that never starts / hangs / hangs after its effect | `host.absent`, `host.hang`, `host.hang_after`: sets of a tool name (`'docker'`) or of argv words in order (`('compose','up')`, `('run','--rm')`, `('image','inspect')`) |
| images | `host.docker.images` (list of inspect objects: `Id`, `RepoTags`, `Config.Labels`, `Config.Env`) |
| containers | `host.docker.containers` (inspect objects); `hostemu.container(name,image_id,reference,env_list,project=,service=,running=,restarts=,health=)`; `host.docker.container(name_or_id)`; knobs `ps_returncode`, `inspect_returncode` |
| what a container does | `host.docker.on_run=lambda call: (returncode,stdout_bytes)`; `call.image .command .stdin .mounts .network .name .environment .read_only_root`, and through the binds `call.listdir(path) call.read(path) call.stat(path) call.write(path,content,mode=0o600)` (EROFS through a read-only bind or outside every bind). The engine itself answers 125 for an image that is not present by ID and for a bind source that does not exist |
| compose | `host.docker.compose.base` (what `config` prints for the base file: `{'services':{name:{'image','environment'}}}`); an override is a JSON object in the tree or standard input, merged per service and per environment name; knobs `config_returncode`, `config_output`, `up_returncode`, `up_effect`, `after_up=lambda compose,new_container: ...`. `up` replaces `<project>-<service>-1` by a new container (new ID, restart count 0, environment = image + render) |
| the lock held by someone else | `host.lock_holder[path]='EX'|'SH'`, `host.lock_released_after=n` (refused requests); `host.lock_held(path)`; `host.paused` |
| systemctl | `host.units[name]={...}`, `host.is_enabled[name]='disabled'`, `host.systemd_version` (show, is-enabled, --version only) |
| the process's dumpable attribute (section 14) | `host.not_dumpable()` logs `('not_dumpable',)` and sets `host.dumpable` to 0 (it starts at 1); `host.dumpable_refused=True` makes it raise the core's refusal `PROCESS_DUMPABLE_NOT_DISABLED` with the attribute unchanged |
| what happened | `host.log` (every call), `host.commands` (argv, stdin, variables, seconds, limit, capture, docker_config), `host.mutating()`, `host.effect_commands()`, `host.container_runs()`, `host.docker.runs`, `host.docker.compose.calls`, `host.fds` (must be `{}` after a run) |

The emulated CLI asserts on anything outside the fixed argv set (an unknown `docker run` option, a compose call without `--project-name`, `--env-file` and `-f`, a blocking `flock`, an open without `O_NOFOLLOW`): a test fails loudly instead of emulating something the family never ran. Extend the emulation in your own test directory by subclassing; do not edit this one.

### 7.3 `conformance` — 121 tests an operation gets by subclassing

```python
import conformance
class TestConformance(conformance.Conformance):
    DIRECTORY=<operation directory>
    @staticmethod
    def case(now=None):          # a bound fixture that COMPLETES on a fresh emulated host: (family.Docs, FakeHost)
        ...                      # now=None -> family.moment(k); the suite also asks for other days
    OTHERS=(<other operation directories>,)      # optional; the two demonstration operations are always included
```

It covers: the build equals the assembly; the carried parts are the sealed ones; the same bytes at any path; unbound templates; the unbound payload refuses under `python3 -I -B -` and through the reviewed transport; the bound fixture completes and its real receipt passes the dispatcher; every unbound or foreign member has its constant refusal; documents of other operations and names of every earlier family are refused at both layers; uid; windows, span, UTC, one day; the date class at both layers; the dry gate; expiry; **every host call failing once in four ways** (a REFUSED receipt means nothing changed); the dispatcher's claim, bindings, date and late start. Tests named `static` pin bytes.

### 7.4 Real system calls

`tests/oslevel.py` substitutes `/` by a private temporary tree on the `os` module and records every system call with its arguments (section 14: also `ctypes.CDLL`, whose C library records each `prctl` in order with the system calls and emulates the dumpable attribute, so that the process of the suite is never made non-dumpable; `Substitute(root, real_prctl=True)`, in a child process on Linux only, passes each `prctl` to the kernel); `tests/native_child.py` runs one source in a child interpreter under an audit hook (copy it and change the import of `demos`). The source's own unmodified `Native` then makes real `mkdir`/`open`/`link`/`unlink`/`fsync`/`flock` calls. On Linux as real root (each operation's CI job) the same tests exercise the kernel's `O_NOATIME`, Linux errno values and uid 0.

---

## 8. Rules every operation must follow

`assemble.py` enforces the ones marked **[A]** (it refuses to build; 83 negative cases in `tests/test_assembly.py`); the conformance suite the ones marked **[C]**; the rest is on the author and the reviewer.

1. **One flag per source.** `WRITES_ALLOWED` is a constant; no source mixes read and write modes. A reading source does not carry `files`, has no `EFFECT` row and no creating call in its `Native` **[A]**. A container run with read-only binds is allowed in a reading source and is said in its scope statement and side effects.
2. **`ACTIVATION_ALLOWED` is True only where a systemd unit is switched** (a systemctl verb other than `--version`, `show`, `is-enabled`, `is-active`, `list-timers`, `cat`). Such a row needs the flag and kind `EFFECT` **[A]**; the three documents must carry the flag of the source **[C]**; the source sets `activation_performed` / `daemon_reload_performed` in its receipts to what its run did. Recreating a compose service is not an activation in this sense: `activate` (K6a) is `ACTIVATION_ALLOWED=False`.
3. **Refuse before any effect.** Everything is looked at before the first creation; the executor identity first, then the boot of the evidence; the lock and the budget are the last refusals (4.2, 4.3). A plan that can be refused from its bytes is refused in `validate_plan` (it runs locally in the dispatcher, before any claim).
4. **Every effect is counted and read back in the run.** System calls through `mutate()`, commands through `effect()`. REFUSED only while `state.clean()`; otherwise PARTIAL. Nothing is repaired, nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its identity is proved. No `os` member beyond those of the carried parts, and in the operation's own part none but the open flags: it makes no system call and starts no process of its own (no `subprocess`, `selectors`, `signal`, `fcntl`, `time`, `ctypes`, named or imported in any form) **[A]**.
5. **Commands**: only rows of the signed table; an absolute, trusted binary of one of two tools, docker and systemctl, so no shell **[A]**; no `docker exec` **[A]**; an attached run starts `run --rm`, never pulls, is not detached or privileged, adds no device or capability, and takes its binds at call time through `--mount` (no `-v`, no bind fixed in the row) **[A]**; a `CONTAINER` row is such a run **[A]** and, like an `EFFECT` row, is started only through its helper (refused otherwise, tested; the operation part cannot pass `through=` **[A]**); a docker read fixes its `--format`, a fixed template never names the environment of a container, and a template given at call time exists only for `container_environment`, started only through that helper **[A]**; compose always with `--project-name`, `--env-file` and an explicit `-f` list (nothing is taken from the working directory, from `COMPOSE_FILE` or from a default override file; the project directory is the directory of the first file, as in the pipeline), the same list for the render and for the recreate. Other options of a row (a network, `--pid`, `--tmpfs`) and other docker verbs in a writing source are not judged by the assembler: the table is in the signed scope and is the reviewer's.
6. **Secrets.** No value of an environment, no byte of `.env`, of a token or of `secret.env`, and no digest or size of them, reaches a receipt, an argv or a log. A compose render and a file read stay in memory; what leaves is a boolean. Constant codes only: raw exception text never leaves (`code_of`, `safe`).
7. **Identity of the source.** `OPERATION`, `PHASE`, schemas and `STEM` in the HOSTOPS02 grammar **[A]**; disjoint from every other operation **[C]**; `SCOPE` carries `core_sha256`, the flags, the command tables and the limits **[A]** and is what the request signs.
8. **Dates** from one class of the core **[A]**; evidence names every operation of `EVIDENCE_OPERATIONS` **[C]**; rows signed by a request come from a receipt of the same boot (`evidence_boot_id_sha256`).
9. **No waiting.** No sleep, no poll loop, no retry except `acquire_lock`'s bounded wait. A wait for a state (a unit that settles) is a later read under its own GO.
10. **Standard library only**, Python 3.7 syntax, ASCII, no `eval exec compile __import__ open print input globals setattr` **[A]**. `import base64` is the only addition a part may make. `ctypes` (a forbidden name of every source in the frozen core) occurs in a source of this revision exactly once, in the core part, as `ctypes.CDLL(None,use_errno=True)` (`CTYPES_LOAD`, section 14) **[A]**.
11. **An operation directory has its own seal** that lists `build/`, names the core generation (`ASSEMBLY.json`), and is checked before binding together with `assemble.py --check`.
12. **The core stays the core inside the source.** The operation part binds no top-level name of a carried part, stores into no object of the core, and leaves every data constant of the core as the parts give it **[A]** (section 1).

---

## 9. Mutation

`python3 -B mutation/mutate.py check | run [prefix ...]`. Each mutant is one literal replacement applied to a private copy (the built demonstration sources for a part; the generated dispatchers and launchers; `assemble.py` for the rules); the copy's tests run with `-k "not static"`, so no mutant dies because a hash changed; a run that exceeds the time limit is a kill. An operation copies `mutate.py` next to its own `mutants.py` and changes `SOURCE`, `CARRIES` (add its own `'op'` target) and `TESTS`; it adds one mutant per member of its `effects_of()` (HOSTOPS01's rule) and one per refusal of its `validate_plan` and precheck.

The list: 537 single mutants and 11 combined ones. By target: core 157, files 146, docker 69, runner 55, assemble (the rules) 50, lock 25, parents 15, dispatcher 12 + 2 + 2, launcher 4. 268 are rows of HOSTOPS01's list that apply unchanged (128 core, 119 files, 12 dispatcher, 4 runner, 4 launcher, 1 docker); 269 are new: the date classes, the activation flag in the three documents, the runner (standard input, classes, `NotStarted`, the budget rule, the accounting of `effect()`), every helper of `docker` (each word of `RUN_PREFIX` and of the recreate, each argument of compose, the environment template), `parents`, what `files` adds, the lock, and each rule of `assemble.py`. 27 of them came with the verification of section 13: the kill of the process group (the group, the session, a command that had already ended), the way each kind of row is started, and the new rules of the assembler with the cases of its top-level walk.

The token family's revision (section 14) adds 21: 13 of the core's `dumps_disabled()` and `NativeRead.not_dumpable()` (`DUMP01`–`DUMP13`: the set not made, the read-back skipped, the two calls swapped, either option number wrong, the attribute set to 1, any read-back accepted, a failure not refused, an exception of the library let through, another library, errno not kept by ctypes, an injected library ignored, the Native saying True without a call) and 8 of the assembler (`A_R51`–`A_R58`: an import of a forbidden module by the operation part, `ctypes` not forbidden to it, its `from` imports or renamed imports not seen, `ctypes` for anything, twice, for any library or without errno, the core not allowed to import it); `tests/test_dumpable.py` is the first file of `ORDER`. The records are those of a run of the whole list of this revision: Python 3.9.6: 567 killed, 0 survivors, 0 errors, 2 redundant survivors (T09_escape_with_a_pending_call_not_looked_at, T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held); Python 3.12.14: 567 killed, 0 survivors, 0 errors, 2 redundant survivors (T09_escape_with_a_pending_call_not_looked_at, T10_verify_does_not_compare_the_fresh_walk_with_the_descriptor_held).

Result of the frozen core (before section 14) on Python 3.9.6 and on 3.12.14: 546 killed, 0 survivors, 0 errors, 2 redundant survivors (`T09`, `T10`, inherited from HOSTOPS01: each removes a check a second check implies; each dies in its combined mutant). One mutant (`L04`, the wait not bounded by the number of attempts) is killed by the time limit: it makes a wait endless. The records pin the bytes they ran against; a record counts only while those pins equal `CORE_SHA256SUMS`.

Zero survivors of THIS list. HOSTOPS01's history applies: two reviews found survivors with mutants of their own after the author's list was clean. The first run of this list had 25 survivors and one harness defect (a byte comparison in a test that was not named `static` killed mutants by hash); the tests that answer them are in `tests/test_files.py`, `test_docker.py`, `test_parents.py`, `test_assembly.py`. The 27 mutants of the verification were written together with their tests and were dead at their first run; that says the tests answer the list, not that the list is complete.

---

## 10. Proven, emulated, unproven

**Proven on the host by earlier receipts** (not by these bytes): the launcher and the reviewed runner under `sudo -n /usr/bin/python3 -I -B -`; the walk by `dir_fd` with `O_NOFOLLOW|O_NOATIME`; `docker image inspect` with `IMAGE_FORMAT`; `docker container inspect` with `CONTAINER_FORMAT` and `docker ps -a --no-trunc` with `PS_FORMAT` (post-deploy readback); the template constructs `range .Config.Env`, `split`, `index`, `eq`, a variable assigned inside a range, `json` (post-deploy readback's flags template); `docker compose --project-name c3po --env-file … -f … [-f -] config --format json` and `… -f <override> up -d --no-deps --no-build --pull never --force-recreate r2d2-worker` (activation of 28/09, run by Codex's payload with the environment its process inherited).

**Real on the workstation** (`tests/test_runner.py`, `test_lock.py`, `test_native.py`; macOS, an ordinary user reported as root, a marker bit for `O_NOATIME`): the runner with real processes (standard input larger than a pipe, a child that never reads, time and output limits, the fixed environment, `/` as working directory, `NotStarted`, no process or descriptor left; the command in a session and group of its own, and a process it started killed with it after a timeout, after the output limit, and when the command itself had ended); the real `flock` on a read-only descriptor; the files part with real `mkdir`, `O_EXCL|O_NOFOLLOW`, `link`, `unlink`, `fsync` by descriptor and a real race at the final name; the docker helpers reaching a real process with the exact argv, bytes and environment.

**Emulated only** (`tests/hostemu.py`): the Docker CLI and compose, device numbers, uid 0, every errno injection and process death.

**Unproven — never executed anywhere; each tier 0 CI job and the Sunday dry run (K11 PRE) must close them:**

- U1 the mutating path of `files` as real root on Linux (the HOSTOPS01 proof ran HOSTOPS01's own bytes; `create_file`/`create_directory` differ by arguments only, but they are other bytes).
- U2 `docker run` with `RUN_PREFIX` on this host: `--init`, `--read-only`, `--mount … ,readonly`, bytes on standard input to `python -I -B -`, under an empty `DOCKER_CONFIG`.
- U3 `container_environment`'s template as composed here (an `if eq . "NAME=VALUE"` inside the proven range). Its constructs ran on the host; this composition did not.
- U4 `docker compose` started with the fixed environment (no `HOME`, `PATH=/usr/bin:/bin`) as root: plugin discovery and config directory. The run of 28/09 inherited the environment of its process.
- U5 `flock` on `deployment.lock` opened `O_RDONLY` as root while the pipeline holds or wants it (Linux allows a lock on any open mode; not run here on Linux).
- U6 the size of `docker compose config --format json` on this host against the 1 MiB class limit, and its duration against 15 s.
- U7 how long `compose up --force-recreate r2d2-worker` takes against the 30 s class (the 23 s of 28/09 is the whole activation).
- U8 Python 3.7 syntax level is checked best-effort only (walrus and positional-only parameters by syntax tree; the host runs 3.12).
- U9 what the kill of the process group reaches on this engine. Whether the compose plugin stays in the group of the docker CLI is a property of the CLI version (if it does not, the kill reaches the CLI alone and the plugin may go on; neither case was run on a real engine). And what a `compose up` killed part-way leaves (the old container stopped or renamed, the new one created and not started) is only known from a read afterwards: a recreate that times out is uncertain by rule, and K6a's receipt must say what the readback found.
- U10 a container that outlives its CLI. An attached run that reaches its time limit leaves its container to the engine (section 6.3). It ends when its process ends; a process that never ends keeps a container without a compose label on the host until someone removes it, and no source of this core removes one.

**The Linux job** (`linux_root/`, the structure of the HOSTOPS01 job that passed): `sh linux_root/run.sh [<operation directory> ...]` on a throwaway GitHub-hosted ubuntu-24.04 runner checks the seal, runs the core's suite as real root and as the runner's user (U1), does the same for each operation directory named (after `assemble.py --check`), switches the engine to the containerd snapshotter, pulls a python image, and runs `linux_root/shapes.py`: seven shapes with the demonstration sources' own tables, helpers, runner and Native on the real engine, and 25 expectations (U2 to U7), exit 0 only when all are met. `shapes.py --self-test` runs the same collection on the emulation (it is part of the suite). **The job was not run by the author**: no Linux and no docker offline. An operation's CI adds its own shapes for its own argv; it does not need to repeat these.

Known limits by design: the timeout of an attached run does not stop the container (the plan's decision: README argv verbatim, SIGKILL to the CLI). K1 (reboot) as built on 26/09 executes installed controller modules from pinned bytes; rule 10 forbids `exec`/`compile`, so K1 is not an operation of this core as it stands. A secret delivery (K3) must not use `create_file` (its ledger row carries a hash and a size). `systemctl` rows are possible but the emulation knows only `show`, `is-enabled`, `--version`.

---

## 11. Notes for the four tier 0 builders

| | K2a catalog init | K10 install_release | K11 epoch readback | K6a activate |
|---|---|---|---|---|
| `WRITES_ALLOWED` / `ACTIVATION_ALLOWED` | True / False | True / False | False / False | True / False |
| `DATE_CLASS` | `WRITE_WEEKEND` | `WRITE_FIRST_SESSION` | `READ` | `WRITE_FIRST_SESSION` |
| `PARTS` | core runner docker parents (+files for the throwaway root of REHEARSAL) | core runner docker parents files | core runner docker parents lock | core runner docker parents files lock |
| Modes | REHEARSAL, REAL (`SUCCESS_IN_TEMPLATE` as needed) | — | PRE, POST (`SUCCESS_IN_TEMPLATE=False` if the outcome differs) | — |
| Effects | one `container_effect` row `RUN` (40 s), bind read-write of the journal root, `docker_config` = the unit's empty directory | `create_directory` + `create_file` 0600 + readbacks | none; `container_run` (`RUN_SHORT` or `RUN`) with the release bytes framed on standard input, `compose_render` with the override on standard input, `probe_lock`, rows by `descend`/`walk_pinned` | lock, `create_directory`, two `create_file`, `compose_render` (stdin, then files), `compose_up`, then `container_facts`, `container_environment`, `container_list` |

- **K2a.** The README argv is `RUN_PREFIX` + `--mount type=bind,source=<journal>,target=/c3po-bar-journal` + image ID + `python -I -B - /c3po-bar-journal <epoch>`: exactly `container_effect(state,commands,row,image_id,[{'source':journal,'target':'/c3po-bar-journal','read_only':False}],['python','-I','-B','-','/c3po-bar-journal',epoch],script,docker_config=...)`. Before it: `effects_budget(row)` = 44 s must be left. After it nothing refuses: settle with `state.done()` only for a verified `CATALOG_READY`; otherwise `state.unknown()` and PARTIAL (the root is not used again). When the run started and did not return, list the containers again and say in the receipt whether one exists that was not there before: it may still be writing into the root.
- **K10 and K6a, before the signature is asked for:** `files` refuses a created object whose group is not 0 or whose device is not its parent's, and that refusal comes after the creation (PARTIAL). The binder checks in the read-only receipt that an entry root created earlier in the same parent is 0:0 (no group inheritance on that filesystem) and that the parent is not setgid (`validate_chain(...,receives_entry=True)` refuses that one from the bytes).
- **K10.** The parent on the data volume is uid 1000: `validate_chain(rows,path,open_root=<data volume>,receives_entry=True)`. The pin and the target are `probe()`s. Bytes travel base64 in the plan (a document is at most 65,536 bytes; `assemble.py` refuses an unbound request above 40,000).
- **K11.** The parser of `systemctl show` output (`properties()` in HOSTOPS01's `op_readback.py`) is not in the core: port it into the operation part. A snippet run with `python -I -B -` must put `/app` on `sys.path` itself and gets no network, no writable path and no environment of the worker; if it needs a writable `/tmp`, that is another row prefix (rule 5), not a change of the core. Report booleans, never the render. Start the container run before the slow reads: a `CONTAINER` row is not started with less than its class + 4 s left (24 s for `RUN_SHORT`), and a run that was not started is a finding. Bind only the directories the run holds pinned. If the image is known to have coreutils `timeout`, a command `timeout -s KILL <n> python -I -B -` (allowed by the grammar) ends the container itself before the CLI is killed, so that none outlives it; that is a choice for the signers, and nothing of it is proven on this image.
- **K6a.** Order: prechecks → `open_lock` → renders with the override on standard input → `acquire_lock(wait ≤ 20, keep = effects_budget('<recreate row>') + allowance)` → `need(gate() >= …)` → directory, policy file, override file → render from the files → `compose_up` → read back → `state.done()` only when the worker is a new container, running, restart count 0, same image, the four names equal, every other container unchanged. **The budget, in figures:** the recreate needs 30 + 4 s when it starts, and between the first creation and the recreate runs the render from the files, a `READ` of class `RENDER` (up to 15 s). `keep` and the check before the first creation must therefore be `effects_budget('<recreate row>')` + what that render can take + 2 s for the files. Take the time the render with the override on standard input took in this same run (`monotonic()` before and after), doubled, with a floor of 3 s: on a normal host that is 34 + 3 + 2 = 39 s, so the prechecks and the lock wait share 21 s; with the full class it would be 51 s and 9 s. An allowance that leaves the render out (the demonstration uses 2 s) turns a slow render into `COMMAND_NOT_STARTED_BUDGET` after the files exist: PARTIAL, on the one shot. `.env` unchanged: `stat_signature` before and after, a boolean in the receipt. Also `probe()` `/run/c3po-security/reboot.pending` after the lock, as the pipeline does. Every later compose command of any operation uses the same file list, override included.

---

## 12. Reproduce (offline; nothing here contacts a host)

```
cd <this directory, wherever it lies>
shasum -a 256 -c CORE_SHA256SUMS
/usr/bin/python3 -B seal.py check                                  # SEAL_OK
/usr/bin/python3 -B assemble.py --core                             # the generation
/usr/bin/python3 -B assemble.py --check tests/demo_read            # BUILD_EQUAL (and tests/demo_write)
/usr/bin/python3 -B delta.py check <hostops01 candidate>           # DELTA_OK
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q tests         # also with the 3.12 interpreter
/usr/bin/python3 -B mutation/mutate.py check                       # every anchor exactly once
/usr/bin/python3 -B mutation/mutate.py run                         # copies under ../work/mut-*; writes mutation/MUTATION_RUN.json
```

Two tests read things outside this directory and are skipped without them: the delta check needs the sealed HOSTOPS01 candidate (`HOSTOPS02_TEST_HOSTOPS01_DIR`, default `../../hostops01/candidate`), the README argv pin needs a checkout that holds dd4ec4bb (`HOSTOPS02_TEST_RELEASE_REPOSITORY`).

---

## 13. What the independent verification changed (2026-10-02)

One pass by a verifier who did not write the core: every part diffed against HOSTOPS01, the suite and the mutation list run on both interpreters, the new pieces attacked with real processes on the workstation. The delta against HOSTOPS01 in authentication, windows, effects binding and the single-use discipline is what section 2 lists and nothing else: the dispatcher differs from HOSTOPS01's shipped ones in literals only (17 or 18 lines, same line numbers), launcher and transport are byte-identical, `authenticate()` and what it calls differ in the three `ACTIVATION_ALLOWED` comparisons, the date set and one refusal code. The date rule was attacked at every edge on both interpreters (first and last instant of a day, a window that ends at midnight, the day before and after each class, the span to the microsecond, non-UTC offsets) and holds.

Defects found and fixed here (each with tests and mutants; the generation and every hash of the first build changed):

| # | Defect | Fix |
|---|---|---|
| 1 | **A timeout killed only the process the runner started.** A process that command had started (for `docker compose`, the plugin) survived, shown with real processes: it could go on acting on the engine after the receipt was sealed and the deployment lock released, and it survived as well when the command itself had ended and the timeout came from the pipe it still held. | The command gets a session and group of its own; a call that does not end by the command's return kills the group (`parts/runner.py`). Real-process tests: the session and the group, four ways a call ends without the command's return, and a return after which nothing is killed. |
| 2 | **Frozen bytes, free names.** The operation part is the last text of the module: `IMAGE_ID='sha256:…'`, a second `def need`, `COMMAND_ENVIRONMENT.update(…)` or `COMMAND_CLASSES['RUN']['seconds']=55` in an `op.py` changed what the sealed parts did, and the assembler built it. | Rule 12 **[A]** (section 1). |
| 3 | **The operation part could act on the host by itself.** `subprocess.Popen([...])`, `os.unlink(...)`, `os.write(...)`, `fcntl.flock(...)` and `time.sleep(...)` in an `op.py` passed the rules (the allow-lists were those of the whole source), outside the signed command table, `mutate()` and the budget. | Rule 4 **[A]**: the own part names `os` for open flags only and none of the five modules. |
| 4 | **`CONTAINER` and call-time-template rows could be started directly.** `commands.call('verify', …)` skipped `run_arguments` (image by ID, read-only binds, command grammar); `commands.output('container_environment', '{{json .Config.Env}}', id)` printed a whole environment into the run; a `CONTAINER` row could be any docker verb (`rm -f`), and a run row could fix a writable `--mount`, a device or a capability in its prefix. | `STARTED_THROUGH` in the runner, `through=` refused in an operation part, and the table rules of section 8, rule 5 **[A]**: two tools, a `CONTAINER` row is a run, no fixed bind, device or capability, a docker read fixes `--format`. |

Checked and left as built, with the reason:

- **A container can outlive its CLI** (U10). The plan decided it (README argv verbatim, SIGKILL to the CLI). Sending SIGTERM first would make the CLI stop the container, but it changes what a timeout does to the catalog run and eats the 4 s reserve; it is a decision for the signers, not a repair. Sections 6.3 and 11 now say what a caller reports.
- **`docker compose` without `HOME`** (U4) stays unproven; `COMMAND_ENVIRONMENT` is HOSTOPS01's reviewed constant. If the Linux job shows that compose needs it, that is a new generation, and every operation is assembled again from unchanged `op.py` and `spec.py`.
- **The demonstration's 2 s allowance** does not cover its render between two effects; with both effects in one run nothing larger fits in 60 s. It is kept as the worked example of the late refusal, and section 11 gives K6a its figures.
- **`probe_lock`** takes a shared lock for an instant; a non-blocking exclusive request of another process that falls in that instant fails (the pipeline's `flock -w 120` waits and is not affected). `LOCK_SCOPE` now says so; the code is unchanged.
- **`ACTIVATION_ALLOWED=False` for K6a** follows the family rule as written (a unit is switched only by systemctl). It is the signers' reading to confirm.
- **`linux_root/`** was read, not run. Its shapes call the helpers the way the rules above require.

---

## 14. The token family's revision: the process made non-dumpable (2026-10-03)

**What and for whom.** This directory is a copy of the frozen core `73fb546b9758718924b73200b48b7c0582a156a60da200ff83f4ca66e9e5c9b1` (generation `4c24c5cf…d0d6`) made for one operation, the token placement `GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01` (`token_from_env`, revision 3), which lies beside it (`hostops02-tok/token_from_env`, `../core` seen from it). The other operations of the tier (K2a, K10, K11, K6a, C3) keep the core `73fb546b…`, unchanged and not edited; their sources, scopes and receipts name its generation.

**Why.** The token placement reads the deploy `.env` (every secret of the host's backend) into its memory. A crash of the interpreter while those bytes are there would hand its memory to the kernel's core handler, and on the host `kernel.core_pattern` is a pipe to a crash collector (the precheck receipt L1: `is_pipe` true); `RLIMIT_CORE` does not stop a pipe (the kernel lets a pipe through any limit but 1). The co-auditor did not accept that residual (decision D9 of the token contract, comment 5973246540) and accepted either a proof that the exact process cannot produce or forward a dump, or a minimal revision of the core or the launcher that imposes the protection before the read, with a new review and a new binding. This is that revision. The frozen core could not do it: `ctypes` was a forbidden name of every source, and an operation part may import nothing but `base64`.

**The mechanism.** prctl(2), `PR_SET_DUMPABLE`: the dumpable attribute "determines whether core dumps are produced for the calling process upon delivery of a signal whose default behavior is to produce a core dump". In the kernel, `do_coredump()` (`fs/coredump.c`; `vfs_coredump()` in newer kernels) returns before it formats the core name from `kernel.core_pattern` when the dumpable bits of the process's memory are 0, so no pipe helper (a crash collector) is started and no core file is created; `RLIMIT_CORE` plays no part. The attribute belongs to the process's memory, is kept by a fork, and is set again only by an exec or a change of credentials; a source does neither (a command of the runner is a process of its own). `dumps_disabled()` sets it to 0 (`prctl(4, 0)` must return 0) and proves it (`prctl(3)` must answer 0); any other outcome is the refusal `PROCESS_DUMPABLE_NOT_DISABLED`, never an exception text. The arguments go to the C library as C ints: the kernel accepts only 0 or 1 for `PR_SET_DUMPABLE` (anything else is `EINVAL`, a refusal), and the read-back decides, so no detail of the calling convention can turn a failure into a pass. The C library is loaded inside the function (`ctypes.CDLL(None, use_errno=True)`: `dlopen` of the program itself, whose symbols include the C library's `prctl`; `use_errno` keeps the C errno of the call in ctypes' private copy) and is never handed out, so an operation part that calls `host.not_dumpable()` gets `True` or a refusal, never a handle on the C library.

**What changed, file by file.**

| File | Change |
|---|---|
| `parts/core.py` | `import ctypes`; `PR_GET_DUMPABLE=3`, `PR_SET_DUMPABLE=4`; `dumps_disabled(library=None)`; `NativeRead.not_dumpable()` (24 lines; nothing else of the part changed) |
| `assemble.py` | `ctypes` in `IMPORTS_OF['core']` and out of `FORBIDDEN_NAMES`; `CTYPES_LOAD='ctypes.CDLL(None,use_errno=True)'` and the rule that the name `ctypes` occurs in a source only at that call, at most once; `ctypes` in `OWN_MODULES_FORBIDDEN`; the operation part may not import any module of `OWN_MODULES_FORBIDDEN` in any form; the pin of `parts/core.py` (`seal.py write`), hence a new generation |
| `tests/test_dumpable.py` | new: the function with an injected C library (success and the order and arguments of the two calls; a first call that fails with `EPERM`, `EINVAL` or `ENOSYS`; a read-back of 1, 2 or -1; a library without `prctl`, or whose call raises, or answers a text), the library of the interpreter loaded once with `use_errno`, `NativeRead.not_dumpable()`, the emulated host, the C library of `oslevel`, macOS's refusal, and on Linux the real kernel in a child process (1 before, 0 after) |
| `tests/test_assembly.py` | the per-part table (`ctypes` in the core part, once, at `CTYPES_LOAD`), six rules (the operation part naming `ctypes`, importing it as another name, from it, plainly, and importing `subprocess` or `time` in another form), the whole-source rule against nine other uses, the delta count (60 added lines) |
| `tests/hostemu.py` | `FakeHost.not_dumpable()`, `dumpable`, `dumpable_refused` (section 7.2) |
| `tests/oslevel.py` | the substitution of `ctypes.CDLL` and its `Library` (section 7.4) |
| `tests/demo_read/build`, `tests/demo_write/build` | assembled again (the new generation; the demonstration operations do not call `not_dumpable()`) |
| `mutation/` | 21 mutants (section 9), `test_dumpable.py` first in `ORDER`, the two records of this revision |
| `DELTA/` | written again by `delta.py write` (the delta of `parts/core.py` against HOSTOPS01) |
| `CORE.md`, `CORE_SHA256SUMS` | this text; the seal |

`reviewed_base/`, `parts/runner.py`, `docker.py`, `parents.py`, `files.py`, `lock.py`, `delta.py`, `seal.py`, `linux_root/`, `tests/family.py`, `conformance.py`, `demos.py`, `native_child.py` and the other test files are the bytes of the frozen core.

**A finding while closing the hole for ctypes.** Rule 4 looked at the names an operation part uses, not at its imports: `from subprocess import Popen`, `import time as clock` or `import ctypes as c` in an operation part passed the assembler of the frozen core. This revision refuses an import of any module of `OWN_MODULES_FORBIDDEN` in any form. The frozen core `73fb546b…` keeps the old rule; none of the tier's five operation parts imports anything but `base64` (checked by syntax tree on 2026-10-03), so nothing built from it is affected; the finding is for its next revision. Not changed here either: `from os import <member>` in an operation part is not seen by the os-member rule (it looks at `os.X`); none of the six operation parts does it.

**What is proven and what is not.** Offline (macOS): the function against injected C libraries; the assembler's rules; the emulated host; the token placement's order on every path and its refusal (its own suite). On Linux (each operation's job, not run yet for this revision): the real kernel in a child of this suite (`test_dumpable.py`), the token placement's native child and its `linux_root/token_shape.py` process (the attribute 1, then 0 after its own run), and what the kernel dumps of a crash before and after the protection, through a pipe into a collector and into a file (`token_from_env/linux_root/dump_proof.py`). The real call cannot be made on macOS (no `prctl`): there the function refuses, as `test_dumpable.py` shows.

---

## 15. Generation core-k6b: the one exception to rule 4 (Codex decision 1, #429 5985748037; A2 amendment 1 rev 3, #429 5986005646)

Exactly one source and one row may change an object that exists:

| | |
|---|---|
| source | `NAME='capacity_switch'` (K6b, `GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01`), a writing source |
| row | `edit_env`, kind `EFFECT`, standard input, no tail, argv exactly `run --rm -i --pull never --init --user 1000:1000 --network none --read-only --cap-drop ALL --security-opt no-new-privileges` (`IN_PLACE_EDIT_EXCEPTION['argv']`) |
| object | the environment file of the compose project (`<deploy>/.env`), bound ALONE read-write at `/c3po-env/.env` (the source's own rule; the assembler checks the row, the source the bind) |
| what may change | the end of that file: an append after the last byte, or a cut of the trailing block of `C3PO_R2D2_V2_CAPACITY_` lines; every other byte, the inode, the owner and the mode stay as they were, compared by the source in memory and on the host |
| memory | the source's own process is made non-dumpable (section 14, `not_dumpable()`) before it opens the deploy tree; the editor's process makes itself non-dumpable (prctl `PR_SET_DUMPABLE` 0, read back 0) before it opens the file, and refuses otherwise with nothing written; the file's bytes stay in that memory only; no byte of the file outside the trailing capacity block is written back (an append writes after the last byte, a cut only shortens); no copy, log, argv or output of any of them |
| who | the account that owns the file, uid and gid 1000 (proven 1000:1000 0600 one link by the M2p receipt, `items.deploy_files.compose_inputs[0]`, 2026-10-04 15:26Z); never root |

Enforced by `assemble.py` (rule `[A]`): an attached run (`run …`) whose `--user` is not `0:0`, or that names no user,
is refused in every source, except that row of that source with that argv; tests in `tests/test_assembly.py`
(`test_the_one_in_place_edit_of_this_generation_is_allowed_to_one_row_of_one_source_only`), mutants `A_X01`–`A_X10`.
Everything else of rules 1–12 and of section 14 holds unchanged for every source, K6b included.

Not changed by this generation: every part (`PINS` equal), the reviewed base files, the runner's environment, the
budget, the date sets. A source assembled from the 2026-10-02 core keeps its bytes; it is NOT a source of this
generation. Only K6b is assembled from this one.

Open, stated by decision 6 of the same review: a bind source and all its ancestors must be root-controlled. The
`.env` bind cannot meet it: `/opt/chief-of-staff-digital` is 1000:1000 mode 0775 (M2p receipt, `chains`/rows), `.env`
itself 1000:1000 0600. This generation does not resolve that; it is an open item for Codex (k6b/DESIGN.md).

Results of this generation (2026-10-05, about 01:40Z, taken from the command output): the core's suite 571 passed and 3
skipped on Python 3.9.6 and on 3.12.14 (the skips need a hostops01 candidate, a release checkout and Linux beside);
mutation 568 single and 11 combined mutants, 579 killed, 0 survivors, 0 errors on both interpreters
(`mutation/MUTATION_RUN.json`, `MUTATION_RUN.py312.json`; the token core's records of generation 32c44cf8 are kept
outside this directory). Three of the kills are by the 900 s time limit on a heavily loaded workstation: `L04` (it makes
a wait endless, as before), and `T09`, `T10`, the two redundant mutants of the 2026-10-02 list: run again alone they end
as redundant survivors, each dead in its combined mutant, as recorded before.
