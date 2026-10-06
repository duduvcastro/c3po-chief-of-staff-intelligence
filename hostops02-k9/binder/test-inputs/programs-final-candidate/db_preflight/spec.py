"""Assembly specification of DBR: the three fixed read-only database queries of ORD:28 (M7)."""
NAME='db_preflight'
MODULE='db_preflight'
STEM='HOSTOPS02_DB_PREFLIGHT'
PARTS=['core','runner','docker','parents']
HEADER='''"""Separate DBR QUERIES family; readonly, own operation, request, GO and reviewed seal. No action on import."""\n'''
SUCCESS_IN_TEMPLATE=False                # the success outcome follows the signed mode: the GO template carries null

def unbound_plan(module):
    return {'mode':None,'priv_receipt':None,'secrets_chain':None,'image_id':None,'image_revision':None,'session':None,'release_receipt_sha256':None,'expected':None,
            'evidence_boot_id_sha256':None}
