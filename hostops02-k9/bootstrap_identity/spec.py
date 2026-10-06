NAME='bootstrap_identity'
MODULE='bootstrap_identity'
STEM='HOSTOPS02_BOOTSTRAP_IDENTITY'
PARTS=['core','runner','docker','parents','claim']
HEADER='"""BOOTSTRAP_IDENTITY: own epoch claim and observed first-night worker identity.\n\nOwn core; exactly one durable exclusive claim outside SECRETS. No secret contents opened; Docker inspect emits only five LIVE comparison booleans. Docker CLI/daemon receive the inspect object. No action on import.\n"""\n'
def unbound_plan(module):return {name:None for name in sorted(module.PLAN_KEYS)}
