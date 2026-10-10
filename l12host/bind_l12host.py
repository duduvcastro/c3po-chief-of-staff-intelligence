"""L12-HOST v3.1 generators (Mac, Fable). Turn a lot SPEC into the signed data the shell runs, and nothing else: no host,
no network, no signature, no receipt. Every output is canonical JSON written O_EXCL under umask 077.

w-request  --family <dir> --layout <layout.json> --prepared-at Z --owner-deadline Z --out <dir>
                 W_REQUEST.json + W_QUESTION.txt + layout.json (lot W: prepare of this family under this layout)
lot        --spec <lot_spec.json> --layout <layout.json> --runtime <runtime.json> --prepared-at Z --out <dir>
                 authority.json + request.json (core ABI, validated by the vendored core) + question.txt + the signed
                 extra files (ext/, k9/, j/, image_go/, docs/, cap/) copied byte for byte
owner      --dir <dir> --published-at Z --signed-at Z [--w]
                 owner.json (or W_OWNER.json): the record of the owner's literal "Assino" to question.txt
                 (signature only 07:00:00-21:45:00 BRT; published <= signed)
bound      --dir <dir> --bound-at Z     bound.json (core L12_BOUND_CANDIDATE_V1), validated by the core
unit-row   --service <reviewed .service> --subst <json> --name <unit-e04> --launch-class C --layout <layout.json>
                 UNIT_START row copied from a reviewed unit (@PLACEHOLDER@ substituted, closed key list). B4: the copy's
                 Restart is ALWAYS no (an explicit, reported change of the reference's Restart=on-failure);
                 RestartSec / RestartPreventExitStatus / StartLimit* / OnFailure are dropped and reported.

There is NO import command: an imported original is never declared by an operator.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
sys.path.insert(0, str(HERE))
import l12host_runtime as rt          # noqa: E402
import install_l12host as inst        # noqa: E402

SPEC_SCHEMA = "L12HOST_LOT_SPEC_V3"
REQUEST_SCHEMA = "L12_FINITE_BATCH_REQUEST_CANDIDATE_V1"
DROPPED_UNIT_KEYS = ("OnFailure", "RestartSec", "RestartPreventExitStatus", "StartLimitIntervalSec", "StartLimitBurst")
need = rt.need


def read(path, limit=rt.LIMIT):
    raw = Path(path).read_bytes()
    need(0 < len(raw) <= limit, "INPUT_SIZE_INVALID")
    return raw


def loose_json(path):
    """Spec/layout inputs may be pretty-printed; strict keys, no duplicates, no NaN."""
    raw = read(path)

    def pairs(items):
        out = {}
        for k, v in items:
            need(k not in out, "JSON_DUPLICATE_KEY")
            out[k] = v
        return out

    def constant(_v):
        raise rt.Hold("JSON_NONFINITE")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    need(type(value) is dict, "JSON_NOT_OBJECT")
    return value


def write_out(directory, name, raw):
    os.umask(0o077)
    path = Path(directory) / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)
    return rt.sha(raw)


def brt(at):
    return rt.stamp(at, rt.Hold).astimezone(rt.BRT).strftime("%d/%m %H:%M:%S BRT")


# ------------------------------------------------------------------ W
def w_request(family, layout_path, prepared_at, owner_deadline, out):
    sys.path.insert(0, str(Path(family)))
    import verify_family
    seal = verify_family.verify(Path(family))["seal_sha256"]
    layout = rt.validate_layout(loose_json(layout_path), rt.Hold)
    need(rt.stamp(prepared_at, rt.Hold) < rt.stamp(owner_deadline, rt.Hold), "W_WINDOW_INVALID")
    request = rt.canonical({"schema": inst.W_REQUEST_SCHEMA, "seal_sha256": seal,
                            "layout_sha256": rt.sha(rt.canonical(layout)), "prepared_at": prepared_at,
                            "owner_deadline": owner_deadline})
    question = ("L12-HOST v3 lote W: preparar a familia L12-HOST no servidor (raiz %s, 0700; familia 0400; ledger vazio 0600).\n"
                "Nenhum timer, nenhum container, nenhuma leitura de segredo.\n"
                "W_REQUEST SHA256: %s\nSelo da familia (SHA256SUMS) SHA256: %s\nLayout SHA256: %s\n"
                "Assinatura aceita de 07:00 a 21:45 BRT, ate %s.\nResponda: Assino\n"
                % (layout["root"], rt.sha(request), seal, rt.sha(rt.canonical(layout)), brt(owner_deadline))).encode("ascii")
    write_out(out, "layout.json", rt.canonical(layout))
    return {"W_REQUEST.json": write_out(out, "W_REQUEST.json", request),
            "W_QUESTION.txt": write_out(out, "W_QUESTION.txt", question)}


# ------------------------------------------------------------------ lot
SPEC_KEYS = {"schema", "lot", "lane", "mode", "owner_deadline", "decision_sha256", "veto_max_age_seconds",
             "initial_receipts", "imports", "files", "external", "k9", "tasks", "extended", "bootstrap", "gate",
             "capacity", "ready", "j4"}
STEP_KEYS = {"step", "not_before", "not_after", "ceiling_seconds", "requires", "effect", "decoder", "pre_effect",
             "hold_until", "slots"}


def build_lot(spec, layout, runtime_raw, prepared_at, base_dir, *, physical=False):
    need(set(spec) == SPEC_KEYS and spec["schema"] == SPEC_SCHEMA, "SPEC_ABI_INVALID")
    layout = rt.validate_layout(layout, rt.Hold)
    runtime = rt.strict(runtime_raw, kind=rt.Hold)
    need(runtime.get("schema") == rt.RUNTIME_SCHEMA and runtime.get("layout_sha256") == rt.sha(rt.canonical(layout)),
         "RUNTIME_LAYOUT_UNBOUND")
    need(type(spec["files"]) is dict, "SPEC_FILES_INVALID")
    extra = {}
    for rel, local in spec["files"].items():
        need(type(rel) is str and rt.REL.fullmatch(rel) is not None and type(local) is str, "SPEC_FILES_INVALID")
        path = Path(local) if Path(local).is_absolute() else Path(base_dir) / local
        extra[rel] = read(path)
    need(type(spec["tasks"]) is list and spec["tasks"], "SPEC_TASKS_INVALID")
    bootstrap = spec["lane"] == "BOOTSTRAP_MONDAY"
    task_keys = {"operation", "not_before", "not_after", "budget_seconds", "requires", "slots", "effect", "decoder",
                 "image_go_sha256", "image_proposal_sha256"}
    tasks, effects, decoders, slots, deps = [], {}, {}, [], {}
    for t in spec["tasks"]:
        need(type(t) is dict and set(t) == task_keys, "SPEC_TASK_ABI_INVALID")
        op = t["operation"]
        row = {k: t[k] for k in ("operation", "not_before", "not_after", "budget_seconds", "requires")}
        if bootstrap:
            row.update(image_go_sha256=t["image_go_sha256"], image_proposal_sha256=t["image_proposal_sha256"])
        else:
            need(t["image_go_sha256"] is None and t["image_proposal_sha256"] is None, "SPEC_IMAGE_GO_OUTSIDE_BOOTSTRAP")
        tasks.append(row)
        effects[op], decoders[op], deps[op] = t["effect"], t["decoder"], list(t["requires"])
        need(type(t["slots"]) is list and t["slots"], "SPEC_SLOTS_INVALID")
        for s in t["slots"]:
            need(type(s) is dict and set(s) == {"slot", "at"}, "SPEC_SLOTS_INVALID")
            slots.append({"slot": s["slot"], "at": s["at"], "target_kind": "CORE", "target": op,
                          "timeout_start_seconds": rt.math_ceil(t["budget_seconds"]) + rt.CORE_TIMEOUT_MARGIN})
    extended = None
    if spec["extended"] is not None:
        steps = []
        need(type(spec["extended"]) is dict and set(spec["extended"]) == {"steps"}, "SPEC_EXTENDED_INVALID")
        for st in spec["extended"]["steps"]:
            need(type(st) is dict and set(st) == STEP_KEYS, "SPEC_EXTENDED_INVALID")
            steps.append({k: v for k, v in st.items() if k != "slots"})
            for s in st["slots"]:
                slots.append({"slot": s["slot"], "at": s["at"], "target_kind": "EXTENDED", "target": st["step"],
                              "timeout_start_seconds": st["ceiling_seconds"] + rt.CORE_TIMEOUT_MARGIN})
        extended = {"steps": steps}
    veto = rt.veto_authority(layout, spec["decision_sha256"], spec["veto_max_age_seconds"])
    authority = {"schema": rt.AUTHORITY_SCHEMA, "lot": spec["lot"], "lane": spec["lane"], "mode": spec["mode"],
                 "layout": layout, "veto": veto, "delegated_named_selectors": True, "dependencies": deps,
                 "effects": effects, "decoders": decoders, "files": {rel: rt.sha(raw) for rel, raw in extra.items()},
                 "external": spec["external"], "imports": spec["imports"], "slots": sorted(slots, key=lambda r: r["at"]),
                 "k9": spec["k9"], "extended": extended, "bootstrap": spec["bootstrap"], "gate": spec["gate"],
                 "capacity": spec["capacity"], "ready": spec["ready"], "j4": spec["j4"]}
    authority_raw = rt.canonical(authority)
    request = {"schema": REQUEST_SCHEMA, "lane": spec["lane"], "epoch": "R2D2-V2-SHADOW-2026-10-12",
               "session": "2026-10-12", "previous_session": "2026-10-09", "track": "BOOTSTRAP" if bootstrap else "P",
               "prepared_at": prepared_at, "owner_deadline": spec["owner_deadline"],
               "authority_sha256": rt.sha(authority_raw), "runtime_sha256": rt.sha(runtime_raw),
               "veto_authority_sha256": rt.sha(rt.canonical(veto)), "initial_receipts": spec["initial_receipts"],
               "tasks": tasks}
    request_raw = rt.canonical(request)
    fam = inst.family_core()
    try:
        q = fam.fb.validate_plan(request_raw)
    except fam.fb.Hold as error:
        raise rt.Hold(str(error)) from None
    rt.validate_authority(authority, q, fam, rt.Hold, physical=physical, files_raw=extra)
    return authority_raw, request_raw, authority, q, extra


def question_text(authority, q, request_raw, runtime_raw):
    lines = ["L12-HOST v3 lote %s (faixa %s, modo %s), epoca %s, sessao %s. Uma tentativa logica por operacao; "
             "horarios alternativos da mesma operacao partilham a mesma tentativa; sem nova tentativa."
             % (authority["lot"], q["lane"], authority["mode"], q["epoch"], q["session"]),
             "REQUEST SHA256: " + rt.sha(request_raw),
             "AUTHORITY SHA256: " + q["authority_sha256"],
             "RUNTIME (medicao) SHA256: " + rt.sha(runtime_raw),
             "VETO (pasta %s, validade %ss) SHA256: %s" % (authority["veto"]["directory"],
                                                           authority["veto"]["maximum_age_seconds"],
                                                           q["veto_authority_sha256"]),
             "Operacoes do nucleo (horario BRT; janela; orcamento; decodificador):"]
    for t in q["tasks"]:
        op = t["operation"]
        when = ", ".join(brt(s["at"]) + " " + s["slot"] for s in authority["slots"]
                         if s["target_kind"] == "CORE" and s["target"] == op)
        lines.append("- %s: %s (%s .. %s), orcamento %ss, depois de [%s]; efeito %s; recibo %s"
                     % (op, when, brt(t["not_before"]), brt(t["not_after"]), t["budget_seconds"],
                        ", ".join(t["requires"]), authority["effects"][op]["kind"], authority["decoders"][op]["kind"]))
    for st in (authority["extended"] or {}).get("steps", []):
        when = ", ".join(brt(s["at"]) + " " + s["slot"] for s in authority["slots"]
                         if s["target_kind"] == "EXTENDED" and s["target"] == st["step"])
        lines.append("- estendido %s: %s, teto declarado %ss, depois de [%s]; efeito %s; recibo %s"
                     % (st["step"], when, st["ceiling_seconds"], ", ".join(r[0] + ":" + r[1] for r in st["requires"]),
                        st["effect"]["kind"] if st["effect"] else "NENHUM (so leitura)", st["decoder"]["kind"]))
        if st["step"] == "ready_check":
            lines += ["  VERIFICACAO ANTECIPADA (so leitura): o ready.json de %s nao pode existir; se existir, o resultado"
                      " e HOLD (READY_LEFTOVER_PRESENT) para que uma pessoa o remova antes da partida da sessao."
                      % authority["ready"]["ready_path"]]
        if st["step"] == "session_start":
            r = authority["ready"]
            lines += ["  LEITOR (desvio explicito da tabela da ordem rev M3, linha 'leitor, partida PRE_OPEN 10:01 BRT'):"
                      " NAO ha partida PRE_OPEN do leitor. Partida UNICA e tardia, numa so reserva: ready.json AUSENTE"
                      " antes do supervisor (se presente: HOLD sem efeito), supervisor (efeito declarado), espera do"
                      " ready.json exato de %s ate %s (exclusive, so leitura), reconferencia, BEFORE_FIRST_READER,"
                      " supervisor ainda vivo (mesmo MainPID), veto atual, e a partida do leitor so com o mesmo ready.json"
                      " presente; observacao dos dois ate %s. Sem READY no prazo: HOLD, sem sessao, sem nova tentativa."
                      % (brt(r["not_before"]), brt(r["not_after"]), brt(st["hold_until"]))]
            # v3.3f (D-NET): the two unit networks, each its own pin, named in the question the owner signs
            nets = [row["unit"]["exec"][row["unit"]["exec"].index("--network") + 1]
                    for row in (st["effect"], st["pre_effect"])]
            lines += ["  REDES DAS UNIDADES: leitor %s, supervisor %s" % (nets[0], nets[1])]
    if authority["k9"] is not None:
        k9 = authority["k9"]
        lines.append("K9: runner %s SHA256 %s; secrets_root %s; redes %s"
                     % (k9["runner_source"], authority["files"][k9["runner_source"]], k9["secrets_root"],
                        ", ".join("%s=%s" % kv for kv in sorted(k9["networks"].items()))))
    for rel, digest in sorted(authority["files"].items()):
        lines.append("  arquivo %s SHA256 %s" % (rel, digest))
    lines += ["Assinatura aceita de 07:00 a 21:45 BRT, ate %s." % brt(q["owner_deadline"]),
              "Nao e GO operacional, prontidao ou E6. Responda: Assino"]
    return ("\n".join(lines) + "\n").encode("ascii")


def lot(spec_path, layout_path, runtime_path, prepared_at, out, *, physical=False):
    runtime_raw = read(runtime_path)
    authority_raw, request_raw, authority, q, extra = build_lot(loose_json(spec_path), loose_json(layout_path),
                                                                runtime_raw, prepared_at, Path(spec_path).parent,
                                                                physical=physical)
    question = question_text(authority, q, request_raw, runtime_raw)
    result = {"authority.json": write_out(out, "authority.json", authority_raw),
              "request.json": write_out(out, "request.json", request_raw),
              "runtime.json": write_out(out, "runtime.json", runtime_raw),
              "question.txt": write_out(out, "question.txt", question)}
    for rel, raw in sorted(extra.items()):
        result[rel] = write_out(out, rel, raw)
    return result


def owner(directory, published_at, signed_at, w=False):
    d = Path(directory)
    request_raw = read(d / ("W_REQUEST.json" if w else "request.json"))
    question_raw = read(d / ("W_QUESTION.txt" if w else "question.txt"))
    record = rt.canonical({"schema": "L12_OWNER_RECORD_CANDIDATE_V1", "answer": "Assino", "channel": "REGISTRO_PELA_FABLE",
                           "request_sha256": rt.sha(request_raw), "question_sha256": rt.sha(question_raw),
                           "question_published_at": published_at, "signed_at": signed_at})
    rt.validate_owner(record, request_raw, question_raw, rt.Hold)
    request = rt.strict(request_raw, kind=rt.Hold)
    need(rt.stamp(request["prepared_at"], rt.Hold) <= rt.stamp(published_at, rt.Hold)
         and rt.stamp(signed_at, rt.Hold) <= rt.stamp(request["owner_deadline"], rt.Hold), "OWNER_CHRONOLOGY_INVALID")
    name = "W_OWNER.json" if w else "owner.json"
    return {name: write_out(directory, name, record)}


def bound(directory, bound_at):
    d = Path(directory)
    request_raw = read(d / "request.json")
    docs = {name: read(d / (name + ".json")) for name in ("authority", "owner", "runtime")}
    raw = rt.canonical({"schema": "L12_BOUND_CANDIDATE_V1", "request_sha256": rt.sha(request_raw),
                        "documents_sha256": {k: rt.sha(v) for k, v in docs.items()}, "bound_at": bound_at})
    fam = inst.family_core()
    try:
        q = fam.fb.validate_plan(request_raw)
        fam.fb.Bundle(request_raw, raw, tuple(docs.items())).validate(q)
    except fam.fb.Hold as error:
        raise rt.Hold(str(error)) from None
    return {"bound.json": write_out(directory, "bound.json", raw)}


# ------------------------------------------------------------------ reviewed unit -> UNIT_START row
def unit_row(service_path, subst, name, launch_class, layout, renames=()):
    """Copy of a REVIEWED unit: @PLACEHOLDER@ substituted from data, whole-word renames (e.g. the container name
    c3po-reader -> c3po-reader-e04), every key in the closed list, ExecStart = docker argv under the closed flag table.
    B4: Restart of the copy is `no` (reported in `changed` when the reference said otherwise); the restart-family keys
    and OnFailure are dropped and reported. The reference bytes are never edited."""
    text = read(service_path).decode("ascii")
    need(all(re.fullmatch(r"@[A-Z_]{1,40}@", k) and type(v) is str and "@" not in v for k, v in subst.items()),
         "SUBST_INVALID")
    for key, value in subst.items():
        text = text.replace(key, value)
    need(re.search(r"@[A-Z_]{1,40}@", text) is None, "SUBST_INCOMPLETE")
    text = text.replace("\\\n", " ")
    words_map = dict(renames)
    props, exec_words, description, dropped, changed = [], None, None, [], []
    import l12host_effect as fx
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        key, _, value = line.partition("=")
        value = " ".join(words_map.get(w, w) for w in value.split())
        if key == "Description":
            description = value
        elif key == "ExecStart":
            exec_words = value.split(" ")
        elif key in DROPPED_UNIT_KEYS:
            dropped.append(key)
        elif key == "Restart":
            if value != "no":
                changed.append(["Restart", value, "no"])
            props.append(["Restart", "no"])
        else:
            need(key in fx.UNIT_KEYS, "SERVICE_KEY_NOT_IN_CLOSED_LIST")
            props.append([key, value])
    need(exec_words is not None and description is not None, "SERVICE_INCOMPLETE")
    if not any(p[0] == "Restart" for p in props):
        props.append(["Restart", "no"])
        changed.append(["Restart", None, "no"])
    row = {"kind": "UNIT_START", "unit": {"name": name, "description": description, "properties": props,
                                          "exec": exec_words}, "launch_class": launch_class}
    fx.validate_row(row, layout)
    return row, dropped, changed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("w-request", "lot", "owner", "bound", "unit-row"))
    for flag in ("--family", "--layout", "--prepared-at", "--owner-deadline", "--out", "--spec", "--runtime", "--dir",
                 "--published-at", "--signed-at", "--bound-at", "--service", "--subst", "--name", "--launch-class"):
        p.add_argument(flag)
    p.add_argument("--rename", action="append", default=[])
    p.add_argument("--w", action="store_true")
    p.add_argument("--physical", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.command == "w-request":
            result = w_request(a.family, a.layout, a.prepared_at, a.owner_deadline, a.out)
        elif a.command == "lot":
            result = lot(a.spec, a.layout, a.runtime, a.prepared_at, a.out, physical=a.physical)
        elif a.command == "owner":
            result = owner(a.dir, a.published_at, a.signed_at, a.w)
        elif a.command == "bound":
            result = bound(a.dir, a.bound_at)
        else:
            renames = [tuple(x.split(":", 1)) for x in a.rename]
            need(all(len(x) == 2 and all(re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,62}", y) for y in x) for x in renames),
                 "RENAME_INVALID")
            row, dropped, changed = unit_row(a.service, loose_json(a.subst), a.name, a.launch_class,
                                             rt.validate_layout(loose_json(a.layout), rt.Hold), renames)
            sys.stdout.write(json.dumps({"row": row, "dropped_keys": dropped, "changed": changed}, sort_keys=True,
                                        indent=1) + "\n")
            return 0
    except BaseException as error:
        print(json.dumps({"schema": "L12HOST_BIND_HOLD_V3", "command": a.command, "code": rt.safe_code(error)}))
        return 2
    print(json.dumps({"schema": "L12HOST_BIND_RESULT_V3", "command": a.command, "sha256": result}, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
