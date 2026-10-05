HOSTOPS02 - Linux-as-root proof of the K9 families and their neighbours, and the real-Docker shapes on the image of the
release. A THROWAWAY branch: it never merges.

WHAT THE BRANCH IS
  The release commit (main at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858) with every other workflow removed, plus:
    hostops02-k9/<family>/<directory>   each sealed directory, byte for byte, at the place it has in the authors' work
                                        tree, so that every relative path of its tests and seal (../core, ../k9_phase_read,
                                        ../../hostops02-sealed/activate, ...) means what it meant when it was sealed
    hostops02-k9/<family>/core and the sibling names   symbolic links, as in the work tree (proof/UNITS.json lists them)
    hostops02-k9/proof                  what the jobs add; its files are listed in PROOF_SHA256SUMS
    .github/workflows/hostops02-k9-proof.yml   the one workflow (= proof/WORKFLOW.yml.txt, byte for byte)
  proof/UNITS.json names every sealed directory, its seal file and the SHA-256 of that seal file, the files withheld
  from publication (each with its sealed hash and the reason) and the links. proof/GROUPS.json names the jobs. Both,
  the workflow and PROOF_SHA256SUMS were written by stage_branch.sh, which verified every seal with shasum -a 256 -c at
  its source, in the copy, and at its source again after the copy, then once more in a git-archive export of the commit.
  No file of this branch is a request, an authority or a GO: every document in a build/ directory is UNBOUND. Every
  token, password and secret value in the branch is a fake test value.

WITHHELD
  A sealed file that names a path of the author's workstation is not published (proof/UNITS.json, "withheld"). It is
  ABSENT from the branch; proof/seals.py accepts exactly that absence. A directory with a withheld file cannot run its
  own seal.py check (recorded NOT_RUN), and a linux_root/run.sh that verifies every sealed file refuses (the group
  records NOT_RUN_WITHHELD and is red). Its suite still runs, without the withheld test file if it is one.

THE JOBS (ubuntu-24.04, GitHub-hosted, HOSTOPS_THROWAWAY_RUNNER=yes, one fresh runner per group)
  seals        proof/seals.py (strict: every seal, every link, no unlisted file, each directory's own seal.py check,
               proof/ and the workflow) and proof/public_safety.py (no workstation path, key material, token of a known
               form, address or mail word outside the reserved ones; findings in files the owner accepted are reported).
  linux-root   one job per group of GROUPS.json: proof/seals.py, then proof/run_group.py <group>, then
               proof/seals.py --after (the outputs of the job allowed and listed), then the artifact
               hostops02-k9-proof-<group>. run_group.py: the runner shown (RUNNER.txt), /opt made root:root 0755 when the
               image leaves it writable (the programs refuse a deploy chain below such a directory), a sudoers drop-in
               that keeps the release-tree variables of the tests across sudo, the release exported with git archive
               (byte-identical to the dd4ec4bb.tar the authors used: checked) and extracted, an app interpreter (a venv
               with the release's requirements) for the groups that need one; then the steps:
                 core     the core's own linux_root/run.sh with the operations: the core's and each operation's suite
                          as REAL root and as the runner's user, each build is the assembly of that core, the core's
                          command shapes under the containerd image store
                 opsh     the operation's own linux_root/run.sh (K9W: its engine shapes; PROBE: the release image)
                 runner-tests   the K9 runner's tests with the app interpreter, as the user and as root
                 release-image  the backend image built from this checkout as the pipeline builds it
                 docker-shapes  proof/docker_shapes.py (N-7 of the K9 interface note; K12 U1-U6, U9, U10)
                 k9w-release-shapes   K9W's own linux_root/shapes.py with the release image instead of a stand-in
                 systemd-shapes proof/systemd_shapes.py (the K5, K13 and K13R systemctl rows on stand-in units)

HOW TO READ A RUN
  Each artifact holds out/<group>/RESULT.json (every step, its exit status and time; every output file with its
  SHA-256, junit counts and failing tests, or a shape file's unmet expectations), RUNNER.txt (the runner as found and
  as left), the junit and shape files themselves under out/<group>/files/, and SEALS.after.json. A group is GREEN only
  when every step exited 0. The job log prints the same, step by step.

WHAT A GREEN RUN DOES NOT PROVE
  Anything about the production host: its kernel, its Docker and compose versions, its systemd, its filesystems (and
  the 200 GiB the K9 tree needs: K4-E0's suite raises the free space it reads only where the runner has less, and says
  so), its networks (c3po_c3po_internal and c3po_db_loopback are made here by a throwaway project), its images (the
  image here is built from the release; the production image ID is another), its units (stand-ins under the same names),
  its secrets (fakes). Nothing here dispatches a request, binds a plan or reads a provider. The runner's /opt is not
  the production /opt.
