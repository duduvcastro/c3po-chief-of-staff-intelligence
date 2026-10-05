"""Synthetic release and policy documents that the application code of the release itself accepts, built with that
code's own constants. Run as a script: real_documents.py <directory that holds the package app>. Prints one JSON
line {"release": base64, "policy": base64}. Nothing here is a real release, consent or policy: every pin is a
repeated character and every reference says SYNTHETIC."""
import base64
import hashlib
import json
import sys

def main():
    sys.path.insert(0,sys.argv[1])
    from app import r2d2_v2_shadow as shadow,r2d2_v2_epoch_assembler as assembler
    from app.r2d2_v2_earnings_package import implementation_contract_sha,implementation_package_sha
    revision=sys.argv[2];pin=lambda letter:letter*64
    bindings={'earnings_amendment_sha':shadow.EARNINGS_AMENDMENT_SHA,'earnings_closed_manifest_sha':shadow.EARNINGS_CLOSED_MANIFEST_SHA,
              'implementation_contract_sha':implementation_contract_sha(),'implementation_package_sha':implementation_package_sha(),'code_revision':revision,
              'code_audit_sha':pin('a'),'source_audit_sha':pin('b'),'readiness_sha':pin('c'),'ebar_amendment_sha':shadow.EBAR_AMENDMENT_SHA}
    def consent(party,moment):
        return dict(bindings,schema=shadow.CONSENT_SCHEMA,party=party,approved=True,receipt_sha=pin('d'),receipt_ref='SYNTHETIC',approved_at=moment)
    release=dict(bindings,schema=shadow.RELEASE_SCHEMA,manifest_sha=shadow.SIGNED_MANIFEST_SHA,signed_manifest_sha=shadow.SIGNED_MANIFEST_SHA,amendment_sha=shadow.AMENDMENT_SHA,
                 epoch=assembler.EPOCH,mode='CERTIFIED',approved_at='2026-10-02T14:00:05+00:00',first_session=assembler.FIRST_SESSION,authorization_ref='SYNTHETIC',
                 package_consents=[consent('CODEX','2026-10-02T14:00:02+00:00'),consent('FABLE','2026-10-02T14:00:03+00:00'),consent('DUDU','2026-10-02T14:00:04+00:00')],
                 calibration_status='ACCEPTED',calibration_protocol='C3PO-V2-CAL-3',calibration_sha=pin('e'),calibration_acceptance_sha=pin('f'),
                 source_codex_signature_sha=pin('1'),source_fable_signature_sha=pin('2'),readiness_at='2026-10-02T14:00:00+00:00',
                 readiness_publication_at='2026-10-02T14:00:01+00:00',deploy_completed_at='2026-10-02T13:59:00+00:00')
    release.update(json.loads(sys.argv[3]));raw=assembler.canonical(release)
    policy={'schema':'R2D2_V2_LIVE_POLICY_V1','mode':'LIVE','epoch':assembler.EPOCH,'release_sha':hashlib.sha256(raw).hexdigest(),'code_revision':revision,
            'package_sha':implementation_package_sha(),'order_sha':assembler.RUNTIME_ORDER_SHA,'capacity':550,'c8_receipt_sha':pin('3'),'head_go_sha':pin('4'),
            'valid_from':'2026-10-02T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00','automatic_retry':False,'first_session':assembler.FIRST_SESSION}
    policy.update(json.loads(sys.argv[4]))
    sys.stdout.write(json.dumps({'release':base64.b64encode(raw).decode(),'policy':base64.b64encode(assembler.canonical(policy)).decode()})+'\n')

if __name__=='__main__':main()
