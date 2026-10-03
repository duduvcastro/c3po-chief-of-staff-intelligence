HOSTOPS02 — Linux-as-root proof of the token placement (token_from_env, revision 2c), beside the four tier 0 once
payloads and C3.
A THROWAWAY branch: it never merges.

WHAT THE BRANCH IS
  The release (main at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858), with every other workflow removed, plus:
    hostops02/core             the frozen core, sealed (CORE_SHA256SUMS)
    hostops02/catalog_init     K2a  GO_WRITE_HOSTOPS02_CATALOG_INIT_01        sealed (SHA256SUMS)
    hostops02/install_release  K10  GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01     sealed (SHA256SUMS)
    hostops02/epoch_readback   K11  GO_READONLY_HOSTOPS02_EPOCH_READBACK_01   sealed (SHA256SUMS; one file withheld, below)
    hostops02/activate         K6a  GO_WRITE_HOSTOPS02_ACTIVATE_01            sealed (SHA256SUMS)
    hostops02/tls_probe        C3   GO_READONLY_HOSTOPS02_TLS_PROBE_01        sealed (SHA256SUMS)
    hostops02/token_from_env        GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01      sealed (SHA256SUMS)
    hostops02/proof            what the jobs add, sealed (PROOF_SHA256SUMS)
    .github/workflows/hostops02-linux-root.yml   the one workflow (= proof/WORKFLOW.yml.txt, byte for byte)
  The branch starts from the C3 proof branch (febb51f) and adds hostops02/token_from_env; of proof/ it changes seals.py
  (the new directory in ORDER; the outputs of the Linux job matched without "/", [^/]*), SEALS.expected.json, this file,
  WORKFLOW.yml.txt and PROOF_SHA256SUMS. No byte of the core, of the five earlier operations or of c3po/ changed.
  Revision 2 (the second commit of the branch) replaces hostops02/token_from_env with the answers to the security and
  conformance reviews of revision 1 (its CONTRACT.txt, section 11). Revision 2c (the third commit) changes the proof
  environment only, after the first job of revision 2 (run 37150103273) refused every real-filesystem shape at PRECHECK
  with DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY: linux_root/run.sh makes the runner's /opt root:root 0755, as the
  production host has it, before the shapes (CONTRACT.txt section 12); the source, the final payload, the scope, the
  tests and the mutation records are those of revision 2. The hashes of the seals and of the payloads are in
  SEALS.expected.json (written by command). Nothing here was run on Linux or on the host by the author. No file of this
  branch is a request, an authority or a GO: every document in a build/ directory is UNBOUND. Every token in the branch is
  fake.

WITHHELD
  epoch_readback/DESIGN.md is listed by that directory's seal and is not in the branch (WITHHELD.json: its sealed
  hash and why). proof/seals.py accepts exactly that absence and nothing else. No test, tool or run reads the file.

THE JOB (ubuntu-24.04, GitHub-hosted, HOSTOPS_THROWAWAY_RUNNER=yes; every step after the checkout runs always)
  1. proof/seals.py
       Each seal file is the recorded one; every listed file has its hash; no unlisted file; each operation's build/
       is what the frozen core assembles (BUILD_EQUAL) and names this core generation; payload hashes as recorded;
       each directory's own seal.py check; proof/ against its seal; the workflow file against its copy.
  2. proof/public_safety.py
       hostops02/ and the workflow hold no workstation path, no key material or token of a known form, no address.
  3. token_from_env/linux_root/run.sh                                                                     (sealed)
       a. the seal of the operation and of the core, and build/ is what the frozen core assembles;
       b. the core's suite and the operation's suite as REAL root (uid 0, the kernel's O_NOATIME, Linux errno values,
          ext4) and as the runner's user, under the distribution's pytest for /usr/bin/python3;
       c. first, / and /opt as found (uid, gid, octal mode), then /opt alone made root:root 0755 (chown 0:0, chmod
          0755; the GitHub-hosted image leaves it writable by every user, and the program refuses a deploy directory
          below such a component by design; the production /opt is root:root 0755) and both shown again: the shapes
          run only when both are then owned by uid 0 and not writable by group or other. Then
          linux_root/token_shape.py as root, with the operation's own run() and unmodified Native on the real
          filesystem: it creates /etc/c3po-bar (root:root 0700, the two children of operation 2) and a FAKE deploy tree
          /opt/hostops02-token-ci (the runner's user, 0755; .env 0600 with fake lines and a fake token), refusing if
          either exists, and removes them at the end. Shapes: the complete run (the file root:root 0600, one link, the
          bytes; the access time of the environment file unchanged, which only the kernel's O_NOATIME explains); the run
          again (refused, the file as it was); a token of another value and length (the receipt the same, the inode of
          the file aside); a tmpfs of four pages mounted on /etc/c3po-bar and filled, so that the write fails with ENOSPC
          (the file of this run withdrawn by identity, nothing left), then unmounted; six refusals before any effect
          (the environment file through a link, a world-writable deploy directory, the export form, a quoted value, the
          name of the token in a value of another name, a second hard link to the environment file); the literal fake
          value FAKE-TOKEN-FOR-TESTS-0001. Every receipt is scanned for every substring of four characters
          or more of the token. Seven expectations;
       d. linux_root/token_shape.py --compose-agreement as the runner's user, a required stage: every listed
          environment file of tests/envfiles.py and the first 500 generated files (seed 20261003) the parser accepts,
          each given to the runner's `docker compose config` for a service of a throwaway project (nothing pulled,
          created or started). For each accepted file: the value the backend would take (the first of its two names
          present), each of the two names, and no other name a case-insensitive reader would take for one of them,
          against the parser. It fails on any disagreement, on a listed accepted file compose refuses, and when
          docker compose is not there. For the refused files, what compose would have given is recorded, not judged;
       e. the seals again; nothing of /etc/c3po-bar, of the fake deploy tree or of the tmpfs is left (/opt stays
          root:root 0755: the runner is discarded).
  4. core/linux_root/report.py: the SHA-256 of every output and its content (junit: counts and every failure, error
     and skip). The outputs are uploaded as one artifact.

OUTPUTS
  hostops02/token_from_env/linux_root/TESTS.core.linux-{root,user}.xml, TESTS.token_from_env.linux-{root,user}.xml
  hostops02/token_from_env/linux_root/SHAPES.token_from_env.linux-root.json, SHAPES.token_from_env.compose.json
  hostops02/proof/out/SEALS.json

WHAT A GREEN JOB DOES NOT PROVE
  - Anything about the production host: its .env (its form, owner and mode, that it holds the key), its compose version
    (the agreement is shown for the runner's; older parsers only by offline ports, DESIGN.md section 4), its root
    filesystem under /etc/c3po-bar.
  - That the value in the host's .env is the value the running containers hold (they read it at their last recreate).
  - The dispatcher, launcher and transport against a real ssh and a real sudo: their suites run here, a dispatch does not.
  - The earlier operations: their proofs are the jobs of their own branches; here only their seals are checked.

PUBLIC SAFETY
  proof/public_safety.py runs in the job: the classes a pattern can name without naming a private value. Before the
  branch was made, the values of the receipts of the host that the binding of this operation will copy (device and
  inode numbers, the boot hash, the host binding) were looked for in every file of hostops02/token_from_env, offline
  and value by value; none is there: the tests use the synthetic values of the core's emulation and a temporary tree.
