import pytest
import dbr
import family as f

def test_other_program_mode_is_refused_before_any_host_access():
 docs,host=dbr.case();docs.plan['mode']='PRIV';docs.chain()
 assert f.refusal(docs.authenticate)=='MODE_INVALID'
 result=docs.run(f.Untouchable());assert result['status']=='REFUSED' and result['code']=='MODE_INVALID'

def test_scope_and_snippet_contain_only_this_program():
 m=dbr.K().m;s=dbr.snippet_module()
 assert m.MODES==('QUERIES',) and set(m.SCOPE['modes'])=={'QUERIES'}
 assert m.PRIV_OPERATION=='GO_READONLY_HOSTOPS02_DB_PRIV_01' and not hasattr(s,'PRIVILEGE_SQL') and not hasattr(s,'privileges_read')

@pytest.mark.parametrize('operation',['GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01','GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'])
def test_queries_cannot_use_a_priv_receipt_from_combined_or_other_operation(operation):
 docs,host=dbr.case();docs.plan['priv_receipt']['operation']=operation;docs.chain()
 assert f.refusal(docs.authenticate)=='PRIV_RECEIPT_NOT_OF_THIS_OPERATION'
 assert docs.run(f.Untouchable())['status']=='REFUSED'
