import pytest
import dbr
import family as f

def test_other_program_mode_is_refused_before_any_host_access():
 docs,host=dbr.case();docs.plan['mode']='QUERIES';docs.chain()
 assert f.refusal(docs.authenticate)=='MODE_INVALID'
 result=docs.run(f.Untouchable());assert result['status']=='REFUSED' and result['code']=='MODE_INVALID'

def test_scope_and_snippet_contain_only_this_program():
 m=dbr.K().m;s=dbr.snippet_module()
 assert m.MODES==('PRIV',) and set(m.SCOPE['modes'])=={'PRIV'}
 assert hasattr(s,'PRIVILEGE_SQL') and not hasattr(s,'EPOCH_ROW_SQL') and not hasattr(s,'reader_queries') and not hasattr(s,'emitter_query')
