"""The bind-time input of K10: the release bytes. binding/release_fields.py computes the plan member from the release
file with the functions of the assembled source, and refuses a file that is not the release the binder expects: the
source judges code_revision and implementation_package_sha by grammar only, so this tool is where a release cut for
another revision, another package or other bytes is stopped before anything is bound (review of 2026-10-02).
The command line is run as the binder will run it, in a child interpreter. The one path the command line cannot show
with a fixture (a release of the deployed revision that is accepted) is run in this process, with the revision this
directory was built for replaced by the fixture's: no document that the deployed application could verify is written."""
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import family as f
import k10

TOOL=k10.DIRECTORY/'binding'/'release_fields.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
DEPLOYED_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
SYNTHETIC_REVISION='0123456789abcdef0123456789abcdef01234567'

def module():
    spec=importlib.util.spec_from_file_location('_k10_release_fields',TOOL);tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool);return tool
def expectations(raw,revision=None,package=None,sha256=None):
    body=json.loads(raw)
    return ['--expect-sha256',sha256 or f.sha(raw),'--expect-code-revision',revision or body['code_revision'],'--expect-package-sha',package or body['implementation_package_sha']]
def tool(*arguments):
    return subprocess.run([sys.executable,'-B',str(TOOL)]+[str(item) for item in arguments],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
def unmarked(**changes):
    """The fixture without any SYNTHETIC_FIXTURE reference: still a synthetic revision, still nothing the application accepts."""
    body=json.loads(k10.RELEASE);body['authorization_ref']='TEST_DOCUMENT_NOT_AN_AUTHORIZATION'
    for consent in body['package_consents']:consent['receipt_ref']='TEST_DOCUMENT_NOT_A_RECEIPT'
    body.update(changes);return (json.dumps(body,indent=1,sort_keys=True)+'\n').encode('ascii')
def inside(raw,arguments,tmp_path,deployed=None):
    """One call of the tool's main() in this process: (exit code, standard output, standard error)."""
    path=tmp_path/'release.CERTIFIED.json';path.write_bytes(raw);out,err=io.StringIO(),io.StringIO()
    code=module().main([str(path)]+arguments,deployed=deployed,out=out,err=err);return code,out.getvalue(),err.getvalue()

def test_constants_of_the_tool_are_the_deployed_revision_and_package_and_the_fixture_is_neither():
    tool_module=module()
    assert tool_module.DEPLOYED=={'code_revision':DEPLOYED_REVISION,'implementation_package_sha':PACKAGE}
    body=json.loads(k10.RELEASE);assert body['code_revision']==SYNTHETIC_REVISION!=DEPLOYED_REVISION and body['authorization_ref'].startswith(tool_module.SYNTHETIC_MARK)
    assert all(consent['receipt_ref'].startswith(tool_module.SYNTHETIC_MARK) for consent in body['package_consents'])

def test_binding_member_is_the_one_the_source_accepts_and_a_plan_built_from_it_completes(tmp_path):
    raw=unmarked();before=sorted(item.name for item in tmp_path.iterdir())
    code,out,err=inside(raw,expectations(raw),tmp_path,deployed={'code_revision':SYNTHETIC_REVISION,'implementation_package_sha':PACKAGE})
    assert code==0 and err=='',err
    out=json.loads(out);k=k10.K()
    assert out['release']==k10.release_member(raw) and out['payload_sha256']==f.sha(k.source) and out['schema']=='HOSTOPS02_INSTALL_RELEASE_BINDING_FIELDS_V2'
    assert out['facts']==k.m.release_facts(raw) and out['facts']['epoch']=='R2D2-V2-SHADOW-2026-10-05'
    assert out['expected']=={'sha256':f.sha(raw),'code_revision':SYNTHETIC_REVISION,'implementation_package_sha':PACKAGE,'expectations_met':True}
    assert sorted(item.name for item in tmp_path.iterdir())==before+['release.CERTIFIED.json'],'nothing is written'
    host=f.world(k);fields=k10.fields(host);fields['release']=out['release'];docs=f.Docs(k,fields)
    template=json.loads((k.dir/'REQUEST.UNBOUND.json').read_bytes())
    assert len(docs.raw()[0])-len(f.canonical(dict(docs.request,plan=dict(docs.plan,release=template['plan']['release']))))==out['request_bytes_added']
    receipt=docs.run(host);assert receipt['status']==k.m.COMPLETE_STATUS and receipt['installed']['sha256']==out['release']['sha256']

def test_binding_refuses_a_release_that_is_not_the_expected_one_before_anything_is_bound(tmp_path):
    """The gap the review found: every one of these files passes authenticate() and would be installed by the source."""
    k=k10.K();deployed={'code_revision':SYNTHETIC_REVISION,'implementation_package_sha':PACKAGE};raw=unmarked()
    assert k.m.release_facts(k.m.release_of({'release':k10.release_member(raw)}))['code_revision']==SYNTHETIC_REVISION,'the source accepts it'
    def refused(document,arguments,code,deployed=deployed):
        found=inside(document,arguments,tmp_path,deployed=deployed);assert found==(1,'','REFUSED %s\n'%code),(code,found)
    refused(raw,expectations(raw,sha256='a'*64),'RELEASE_SHA256_NOT_THE_EXPECTED_HASH')
    refused(raw,expectations(raw,revision=DEPLOYED_REVISION),'RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION')
    refused(raw,expectations(raw,package='c'*64),'RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE')
    other=unmarked(implementation_package_sha='c'*64)
    refused(other,expectations(other,package=PACKAGE),'RELEASE_PACKAGE_NOT_THE_EXPECTED_PACKAGE')
    # the expectations agree with the file, but the file was cut for a revision or a package this directory was not built for
    refused(raw,expectations(raw),'EXPECTATION_NOT_THE_DEPLOYED_RELEASE',deployed=None)
    refused(other,expectations(other),'EXPECTATION_NOT_THE_DEPLOYED_RELEASE')
    refused(raw,expectations(raw),'EXPECTATION_NOT_THE_DEPLOYED_RELEASE',deployed={'code_revision':SYNTHETIC_REVISION,'implementation_package_sha':'c'*64})
    # the fixture of this directory, whatever the binder expects of it
    refused(k10.RELEASE,expectations(k10.RELEASE),'RELEASE_IS_A_SYNTHETIC_FIXTURE')
    for change in (lambda body:body.update(authorization_ref='SYNTHETIC_FIXTURE_X'),lambda body:body['package_consents'][2].update(receipt_ref='SYNTHETIC_FIXTURE'),
                   lambda body:body.update(note={'deep':['SYNTHETIC_FIXTURE_ANYWHERE']})):
        body=json.loads(raw);change(body);marked=(json.dumps(body,indent=1,sort_keys=True)+'\n').encode('ascii')
        refused(marked,expectations(marked),'RELEASE_IS_A_SYNTHETIC_FIXTURE')
    # an expectation that is not a hash or a revision is refused as such, never compared
    for arguments in (expectations(raw,sha256='A'*64),expectations(raw,sha256='0'*64),expectations(raw,revision='dd4ec4bb'),expectations(raw,package='b5ce527a'),
                      expectations(raw,revision='0'*40)):
        refused(raw,arguments,'EXPECTATION_INVALID')

def test_command_line_requires_the_three_expectations_and_refuses_the_fixture_and_what_the_source_would_refuse(tmp_path):
    def refused(raw,code,name='release.json',arguments=None):
        path=tmp_path/name;path.write_bytes(raw);done=tool(path,*(expectations(raw) if arguments is None else arguments))
        assert done.returncode==1 and done.stdout==b'' and done.stderr.decode()=='REFUSED %s\n'%code,(code,done.stderr)
    # exactly the usage: the file and each option once
    path=tmp_path/'fixture.json';path.write_bytes(k10.RELEASE);full=expectations(k10.RELEASE)
    for arguments in ([],[path],[path]+full[:4],[path]+full[2:],full,[path,path]+full,[path]+full+full[:2],[path]+full+['--force'],['--force']+full,[path]+full[:5]):
        done=tool(*arguments);assert done.returncode==2 and done.stdout==b'' and b'--expect-sha256' in done.stderr,arguments
    # the fixture and an unmarked synthetic document through the command line: the sealed constants decide
    refused(k10.RELEASE,'RELEASE_IS_A_SYNTHETIC_FIXTURE')
    refused(unmarked(),'EXPECTATION_NOT_THE_DEPLOYED_RELEASE')
    refused(unmarked(),'RELEASE_CODE_REVISION_NOT_THE_EXPECTED_REVISION',arguments=expectations(unmarked(),revision=DEPLOYED_REVISION))
    # what the source refuses, with the source's own code
    for raw,code in ((k10.altered(epoch='R2D2-V2-SHADOW-2026-09-28'),'RELEASE_EPOCH_NOT_THIS_EPOCH'),(k10.altered(first_session='2026-10-06'),'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH'),
                     (k10.altered(mode='DIAGNOSTIC'),'RELEASE_NOT_A_CERTIFIED_V3_RELEASE')):
        refused(raw,code)
    arguments=['--expect-sha256',f.sha(b'{not json'),'--expect-code-revision',DEPLOYED_REVISION,'--expect-package-sha',PACKAGE]
    refused(b'{not json','RELEASE_NOT_JSON',arguments=arguments)
    large=k10.altered(authorization_ref='x'*40000);refused(large,'RELEASE_FILE_NOT_REGULAR_OR_TOO_LARGE')
    fixed=['--expect-sha256','a'*64,'--expect-code-revision',DEPLOYED_REVISION,'--expect-package-sha',PACKAGE]
    (tmp_path/'empty').write_bytes(b'');assert tool(tmp_path/'empty',*fixed).stderr==b'REFUSED RELEASE_FILE_NOT_REGULAR_OR_TOO_LARGE\n'
    os.symlink('release.json',str(tmp_path/'link'));done=tool(tmp_path/'link',*fixed);assert done.returncode==1 and done.stderr==b'REFUSED RELEASE_FILE_UNREADABLE\n'
    done=tool(tmp_path,*fixed);assert done.returncode==1 and done.stderr in (b'REFUSED RELEASE_FILE_NOT_REGULAR_OR_TOO_LARGE\n',b'REFUSED RELEASE_FILE_UNREADABLE\n')
    assert tool(tmp_path/'absent',*fixed).stderr==b'REFUSED RELEASE_FILE_UNREADABLE\n'
