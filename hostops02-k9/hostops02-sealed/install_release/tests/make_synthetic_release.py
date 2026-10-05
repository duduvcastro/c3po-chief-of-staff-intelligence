"""Author's tool, offline: writes tests/fixtures/release.SYNTHETIC.json and RELEASE_VERIFY.SYNTHETIC.json.

The fixture is a release document in the shape the application reads (R2D2_V2_RELEASE_V3, CERTIFIED, three package
consents), with the constants of epoch R2D2-V2-SHADOW-2026-10-05 and the implementation package of the release tree
it is run against, and it is VERIFIED HERE BY THE APPLICATION'S OWN CODE: app.r2d2_v2_shadow.Release.verify with the
real ShadowCalendar, at the instant the install is planned for (Monday 2026-10-05 08:27 UTC).

It is not a release and can never pass on the host: its code_revision is a synthetic value (SYNTHETIC_REVISION), so
Release.verify with the build revision of any deployed image answers RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED; every
audit, review, readiness and consent hash is the SHA-256 of a text that says SYNTHETIC; no party approved anything.

usage: <python with exchange_calendars> make_synthetic_release.py <checkout of the release: the directory that holds c3po/backend/app>
"""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
FIRST_SESSION='2026-10-05'
SYNTHETIC_REVISION='0123456789abcdef0123456789abcdef01234567'
VERIFY_AT='2026-10-05T08:27:00+00:00'
def fake(label):return hashlib.sha256(('SYNTHETIC HOSTOPS02 INSTALL_RELEASE FIXTURE: '+label).encode()).hexdigest()

def build(app):
    """The fixture as a dict, with the constants read from the application's own modules."""
    bindings={'earnings_amendment_sha':app['package'].EARNINGS_AMENDMENT_SHA,'earnings_closed_manifest_sha':app['package'].EARNINGS_CLOSED_MANIFEST_SHA,
              'implementation_contract_sha':app['package'].implementation_contract_sha(),'implementation_package_sha':app['package'].implementation_package_sha(),
              'code_revision':SYNTHETIC_REVISION,'code_audit_sha':fake('code audit'),'source_audit_sha':fake('source audit'),'readiness_sha':fake('readiness'),
              'ebar_amendment_sha':app['shadow'].EBAR_AMENDMENT_SHA}
    def consent(party,at):
        return dict(bindings,schema=app['package'].CONSENT_SCHEMA,party=party,approved=True,approved_at=at,
                    receipt_sha=fake('consent receipt '+party),receipt_ref='SYNTHETIC_FIXTURE_NO_PARTY_APPROVED_ANYTHING')
    release=dict(bindings,schema=app['package'].RELEASE_SCHEMA,mode='CERTIFIED',epoch=EPOCH,first_session=FIRST_SESSION,
                 approved_at='2026-10-03T19:40:00+00:00',authorization_ref='SYNTHETIC_FIXTURE_NOT_AN_AUTHORIZATION',
                 source_codex_signature_sha=fake('source review codex'),source_fable_signature_sha=fake('source review fable'),
                 manifest_sha=app['shadow'].SIGNED_MANIFEST_SHA,signed_manifest_sha=app['shadow'].SIGNED_MANIFEST_SHA,amendment_sha=app['shadow'].AMENDMENT_SHA,
                 calibration_status='ACCEPTED',calibration_protocol='C3PO-V2-CAL-3',calibration_sha=fake('calibration'),
                 calibration_acceptance_sha=fake('calibration acceptance'),
                 readiness_at='2026-10-03T17:00:00+00:00',readiness_publication_at='2026-10-03T17:05:00+00:00',deploy_completed_at='2026-10-02T14:00:00Z',
                 package_consents=[consent('CODEX','2026-10-03T17:10:00+00:00'),consent('FABLE','2026-10-03T17:20:00+00:00'),consent('DUDU','2026-10-03T19:30:00+00:00')])
    return release

def load_app(checkout):
    sys.path.insert(0,str(Path(checkout).resolve()/'c3po'/'backend'))
    from app import r2d2_v2_earnings_package as package
    from app import r2d2_v2_shadow as shadow
    from app.r2d2_v2_calendar import ShadowCalendar
    return {'package':package,'shadow':shadow,'calendar':ShadowCalendar}

def verify(app,raw,revision=SYNTHETIC_REVISION,at=VERIFY_AT):
    """The application's own verification of release bytes at one instant, for one build revision."""
    return app['shadow'].Release.verify(raw,hashlib.sha256(raw).hexdigest(),now=datetime.fromisoformat(at),build_sha=revision,calendar=app['calendar']())

def main(checkout):
    app=load_app(checkout);release=build(app)
    # the bytes as the releases of the earlier epochs were written: sorted keys, one space of indentation, a final newline
    raw=(json.dumps(release,indent=1,sort_keys=True)+'\n').encode('ascii')
    verified=verify(app,raw)
    assert (verified.mode,verified.epoch,verified.first_session.isoformat(),verified.code_revision)==('CERTIFIED',EPOCH,FIRST_SESSION,SYNTHETIC_REVISION)
    try:verify(app,raw,revision='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858');refused=None
    except Exception as error:refused=str(error)
    assert refused=='RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED',refused
    target=HERE/'fixtures';target.mkdir(exist_ok=True)
    (target/'release.SYNTHETIC.json').write_bytes(raw)
    record={'schema':'HOSTOPS02_INSTALL_RELEASE_SYNTHETIC_FIXTURE_V1','release_sha256':hashlib.sha256(raw).hexdigest(),'release_bytes':len(raw),
            'verified_by':'app.r2d2_v2_shadow.Release.verify of the release tree, real ShadowCalendar','verified_at_instant':VERIFY_AT,
            'build_revision_used':SYNTHETIC_REVISION,'calendar_library_version':app['calendar']().version,
            'implementation_package_sha':release['implementation_package_sha'],'implementation_contract_sha':release['implementation_contract_sha'],
            'result':{'mode':verified.mode,'epoch':verified.epoch,'first_session':verified.first_session.isoformat(),'approved_at':verified.approved_at.isoformat()},
            'with_the_deployed_build_revision':refused,'python':sys.version.split()[0]}
    (target/'RELEASE_VERIFY.SYNTHETIC.json').write_bytes((json.dumps(record,indent=1,sort_keys=True)+'\n').encode('ascii'))
    sys.stdout.write(json.dumps(record,indent=1,sort_keys=True)+'\n');return 0

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
