"""Assembly specification of the token placement: the provider token of the supervisor, copied once from the deploy
environment file of the host into /etc/c3po-bar/token (decision of the owner: DUDU_DECISION_TOKEN_BY_PROGRAM)."""
NAME='token_from_env'
MODULE='token_from_env'
STEM='HOSTOPS02_TOKEN_FROM_ENV'
PARTS=['core','parents','files']
HEADER='''"""OP_TOKEN_FROM_ENV: the provider token of the Massive supervisor, placed once as /etc/c3po-bar/token from the
value the deploy environment file of the host already holds (MASSIVE_API_TOKEN, or C3PO_MASSIVE_API_TOKEN, the two
names the backend accepts). One source, one signed run, on 2026-10-03 or 2026-10-04 UTC only.

It reads ONE file: <signed deploy directory>/.env, by a descriptor walk from "/" that never follows a link, after
proving every component a directory, every component above the deploy directory root-owned and not writable by group
or other, none writable by any user without the sticky bit, and the file regular, with one link, not world-writable,
owned by root or by the owner of the deploy directory and at most 65536 bytes. The file is parsed in memory under a
strict subset of the dotenv grammar of docker compose; every definition of either name must be the plain form
NAME=VALUE, all of them byte-equal, no other line may hold the name in any case, and the value must match a fixed
grammar; anything else is a refusal with a constant code. It never reads an environment of a process, never runs
docker or any other program, and starts no process.

Then, relative to the held descriptor of /etc/c3po-bar (identity signed from the receipt of supervisor operation 2,
root:root 0700), ONE exclusive create of the name "token" (O_CREAT|O_EXCL|O_NOFOLLOW, 0600 under umask 0077), the
value and one newline written, the file and the directory fsynced, and the file read back by descriptor: uid 0, gid
0, mode 0600, one link, size within 1-4096, bytes equal to what was written (compared in memory only). Everything is
looked at before the creation; a token file that exists is never touched (refusal). If a step after the creation
fails, the file this run created is removed again, and only while its name still shows the inode this run holds (an
exception to rule 4 of the core, declared in the signed scope). The receipt carries listed codes, booleans and
identity rows only: never the value, a digest of it, its length or a line count. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
"""
'''
SUCCESS_IN_TEMPLATE=True

def unbound_plan(module):
    return {'config_chain':None,'deploy_directory':None,'evidence_boot_id_sha256':None}
