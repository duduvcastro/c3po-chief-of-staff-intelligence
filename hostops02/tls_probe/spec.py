"""Assembly specification of C3: the TLS probe of the supervisor README's rehearsal item 2, before the units go in."""
NAME='tls_probe'
MODULE='tls_probe'
STEM='HOSTOPS02_TLS_PROBE'
PARTS=['core','runner','docker']
HEADER='''"""OP_TLS_PROBE: rehearsal item 2 of the supervisor README at dd4ec4bb ("A TLS connection to socket.massive.com:443
succeeds from @NETWORK@, without a token"), for the network the owner's sheet chose, the engine's default network
bridge. A reading source of the frozen core: it creates and changes nothing on the filesystem of the host.

It starts ONE attached container of the signed image ID (the production backend image by its local ID, carrying the
release revision label and the signed retention tag) on the network bridge, removed by the engine when its process
ends, with no bind, no environment file, no DOCKER_CONFIG and no token, a read-only root filesystem, uid 0 and no
capability, and gives it on standard input the pinned probe script that this source carries. The script resolves the
provider host, opens one TCP connection to port 443 and makes one TLS handshake with Python's default verifying
context (server name socket.massive.com), then closes. It sends no application byte and no HTTP request, and prints
one JSON line of counts, booleans, constant codes, the SHA-256 of the leaf certificate and timings. Before the
container: the executor, the boot of the evidence, the image by ID and by its retention tag, and the container list,
under which a refusal has started nothing. After it: the container list again, so that the receipt says whether a
container of its name, or any container that was not there before, is still listed. Success is one outcome: TLS
verified to the provider host, and the container removed. Nothing is removed, retried or repaired by this process.
The caller authenticates exact request/authority/GO/source bytes first; the source accepts only a window inside the
band of the weekend authority (2026-10-04, 11:45 to 12:30 UTC).
No action on import.
"""
'''

def unbound_plan(module):
    return {'image_id':None,'image_revision':None,'retention_tag':None,'script_sha256':None,'evidence_boot_id_sha256':None}
