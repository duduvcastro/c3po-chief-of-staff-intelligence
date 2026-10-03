HOSTOPS02 — Linux-as-root proof of the four tier 0 once payloads and of C3 (the TLS probe). A THROWAWAY branch: it never
merges.

WHAT THE BRANCH IS
  The release (main at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858), with every other workflow removed, plus:
    hostops02/core             the frozen core, sealed (CORE_SHA256SUMS)
    hostops02/catalog_init     K2a  GO_WRITE_HOSTOPS02_CATALOG_INIT_01        sealed (SHA256SUMS)
    hostops02/install_release  K10  GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01     sealed (SHA256SUMS)
    hostops02/epoch_readback   K11  GO_READONLY_HOSTOPS02_EPOCH_READBACK_01   sealed (SHA256SUMS; one file withheld, below)
    hostops02/activate         K6a  GO_WRITE_HOSTOPS02_ACTIVATE_01            sealed (SHA256SUMS)
    hostops02/tls_probe        C3   GO_READONLY_HOSTOPS02_TLS_PROBE_01        sealed (SHA256SUMS)
    hostops02/proof            what this job adds, sealed (PROOF_SHA256SUMS)
    .github/workflows/hostops02-linux-root.yml   the one workflow (= proof/WORKFLOW.yml.txt, byte for byte)
  Nothing under c3po/ differs from the release: proof/release_image.sh compares the tree of c3po/ with the release's
  before it builds the image. The sealed directories hold exactly the files their seals list, nothing of the scratch
  that stood beside them. The hashes of the seals and of the payloads are in SEALS.expected.json (written by command).
  Nothing here was run on Linux, on a real engine or on the host by the author. No file of this branch is a request, an
  authority or a GO: every document in a build/ directory is UNBOUND.

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
  3. core/linux_root/run.sh ../catalog_init ../install_release ../epoch_readback ../activate ../tls_probe   (sealed)
       The core's suite and the five operations' suites as REAL root (uid 0, the kernel's O_NOATIME, Linux errno
       values, ext4) and as the runner's user, under the distribution's pytest for /usr/bin/python3 3.12; the
       engine switched to the containerd image store; the core's seven shapes with the demonstration sources' own
       tables, runner and Native: attached `docker run` with the fixed prefix (read-only bind, read-write bind,
       standard input, empty DOCKER_CONFIG), the environment template, `docker compose` render (override on standard
       input and from a file) and the recreate of one service of a throwaway project, the deployment-lock probe and
       bounded wait against a lock another process holds. CORE.md section 10: U1 to U7.
  4. catalog_init/linux_root/run_catalog.sh <checkout>                                                    (sealed)
       K2a end to end on the real paths of supervisor operation 2, created and removed by the job: REHEARSAL (its own
       docker-cli directory, a throwaway root in /var/lib, a DIAG epoch), then REAL, then REAL again (refused), with
       the README's argv word for word and the pinned script on standard input, in an image built on the release's
       base by digest with the release's application modules. K2A-U1, U2 (for the runner's CLI), U3, U5, U6.
  5. install_release/binding/linux_proof.py on the two junit files of step 3                            (sealed)
       The gate of K10's binding: LINUX_PROOF_ACCEPTED only when the whole suite of this seal ran as uid 0 on ext4
       under Python 3.12 with the kernel's O_NOATIME and the creating tests ran for real. U-K10-2.
  6. activate/linux_root/run.sh                                                                             (sealed)
       K6a's own run() end to end on a throwaway compose project: refusals before any effect (wrong mount, lock held,
       leftover container, already activated), one complete run (policy file, override file, ONE recreate of the
       worker with the override passed with -f, readback), and one interrupted recreate of a third service, observed.
       UA-1 to UA-6, UA-8, UA-9, UA-11, UA-12; UA-7 and UA-10 observed for the runner's compose version only.
  7. proof/release_image.sh <checkout>                                                                 (this branch)
       The backend image built from this checkout as the pipeline builds it (c3po/backend/Dockerfile, the rebuild
       token, the revision label), under the containerd image store. With that image:
         - catalog_init/linux_root/catalog_shape.py again: the pinned script in the image the Dockerfile of the release
           makes (python on PATH, no entrypoint, the application's imports with its dependencies, the duration);
         - epoch_readback/linux_root/shapes_k11.py: K11-U1 (--name), K11-U2 (read-only bind under --read-only, read
           by the reader of the worker), K11-U3 (the alarm under --init, status 142), K11-U5 (systemctl show);
         - proof/release_verify_shape.py: nothing bound at /app. Release.verify, read_policy and validate_policy of the
           image's own application on SYNTHETIC documents built by epoch_readback/tests/real_documents.py inside the
           image; the release on standard input and through a read-only bind; a refusal by the release code's own
           code; the package hash the image computes against the signed one. K11-U4;
         - proof/release_compose_render.py: c3po/compose.yml of the release, rendered (config creates nothing) by the
           helpers of K11 and of K6a, and both sources' rule for the worker's data bind applied to it. K11-U6, UA-2,
           and UA-6/U6 for the real file;
         - activate/linux_root/shapes.py again, the three services of the throwaway project running that image.
  8. tls_probe/linux_root/run.sh <checkout>                                                              (sealed)
       C3 with the operation's own perform() and Native, its own argv (network bridge, --rm, no bind, the pinned script
       on standard input), against stand-ins INSIDE the runner, never the provider: the engine's "dns" is set to the
       gateway of the network bridge, where a stand-in DNS server answers socket.massive.com with that gateway and a
       stand-in TLS server listens on its port 443 with a leaf of a throwaway authority (made on the runner, keys never
       leave its temporary directory). Two images on the release's base by digest: one that trusts that authority
       (TEST ONLY), one as the base is. Six probes: verified (the leaf hash, the server name, 0 application bytes), an
       image that does not trust the authority (19 or 20), another name (62), a refused port, a name that does not
       exist, a handshake never answered (bounded at 4 s); the running container inspected (bridge only, no bind or
       mount, AutoRemove, read-only root, CapDrop ALL, init, 0:0, the image by ID); docker events of the verified probe
       (create, connect to bridge, start, die 0, destroy). Three FORWARD rules reject what the network bridge would send
       to port 443 or 53 anywhere; their counter must be 0. daemon.json is put back and the engine restarted.
       C3-U3 and C3-U5 for the runner's engine; the source's TLS path end to end.
  9. core/linux_root/report.py: the SHA-256 of every output and its content (junit: counts and every failure, error
     and skip). The outputs are uploaded as one artifact.

OUTPUTS
  hostops02/core/linux_root/TESTS.linux-{root,user}.xml, TESTS.<operation>.linux-{root,user}.xml, SHAPES.linux-root.json
  hostops02/catalog_init/linux_root/CATALOG_SHAPE.linux-root.json
  hostops02/activate/linux_root/SHAPES.activate.linux-root.json
  hostops02/tls_probe/linux_root/SHAPES.tls_probe.linux-root.json
  hostops02/proof/out/SEALS.json  LINUX_PROOF.install_release.json  IMAGE.release-image.txt
      CATALOG_SHAPE.release-image.linux-root.json  SHAPES.k11.release-image.linux-root.json
      RELEASE_VERIFY.release-image.linux-root.json  COMPOSE_RENDER.release.linux-root.json
      SHAPES.activate.release-image.linux-root.json

WHAT A GREEN JOB DOES NOT PROVE
  - Anything about the production host: its engine (29.5.3) and compose plugin versions, its image (the same
    Dockerfile and commit, another build), its filesystems, its deploy tree, its running project. The runner's
    versions are printed; where they differ, a shape is shown for the runner's version only.
  - K2A-U4 for the production image itself, and K2A-U2 for the host's docker CLI: the Saturday rehearsal (A6).
  - K2A-U7 (what a 40 s timeout of the catalog run leaves) and CORE U10 (a container that outlives its CLI).
  - U-K10-1, U-K10-3, U-K10-4: linkat/unlinkat in a new directory of the host's data volume, the ownership of what
    root creates there, and these bytes under the host's interpreter. First executed on Monday.
  - UA-7, UA-10, CORE U9: what an interrupted recreate leaves and in which order the host's compose plugin makes its
    calls. Observed here on a third service; K6a's own recreate is never interrupted by this job.
  - UA-5 for the production worker: the recreate is timed against a worker stopped the same way, not the worker.
  - The application's verdict on the REAL release and policy: the documents here are synthetic. That is the Sunday
    dry run (K11 PRE) and Monday's readback (K11 POST).
  - The dispatcher, launcher and transport against a real ssh and a real sudo: their suites run here, a dispatch does not.
  - CORE U8 (the Python 3.7 syntax level): the runner has 3.12, as the host.
  - C3-U1 and C3-U2: that the network bridge of the HOST reaches socket.massive.com:443 (egress, the engine's DNS) and
    that the production image's own trust store verifies the provider's chain. The job never contacts the provider and
    trusts its throwaway authority through a test image only: only the run on the host (A1 4.2, C3) shows these.
  - C3-U4: the host's docker CLI without DOCKER_CONFIG and HOME writes nothing.

PUBLIC SAFETY
  proof/public_safety.py runs in the job: the classes a pattern can name without naming a private value. Before the
  branch was made, every value of the signed receipts of the host was also looked for, offline and value by value, in
  every file of hostops02/; what that comparison found is in the report that accompanies the branch, not here. One
  file was withheld (above). The sealed directories could not be edited for this branch: a seal is its bytes.
