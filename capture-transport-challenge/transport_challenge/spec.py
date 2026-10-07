NAME='capture_transport_challenge'
MODULE='capture_transport_challenge'
STEM='HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE'
PARTS=['core']
HEADER='"""One dated transport challenge, separate from consumed BOOT and epoch claims.\nThe exact signed input is echoed only after core authentication. No host file read/write or tool call.\nLocal once claims and ordinary SSH/sudo audit effects belong to the dispatcher and transport.\nOutside-Mac authority and actual owner answer are independently required. No action on import.\n"""\n'
def unbound_plan(module):
    return {'session':None,'run_id':None,'run_attempt':None,'nonce':None}
