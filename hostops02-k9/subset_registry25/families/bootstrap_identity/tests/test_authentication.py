"""Carry the shared authentication tests unchanged where their contract is unchanged.
New tests below declare the bootstrap's own one-day/fixed-slot/claim contract.
No host transport is sent; unbound payload runs only a local interpreter and refuses before Native use.
"""
import ast,json,re,sys
from datetime import timedelta
from pathlib import Path
import pytest
import fixtures as fx
import conformance

class TestBootstrapAuthentication:
    DIRECTORY=fx.DIRECTORY
    def one(self,now=None):
        docs,host=fx.case();return docs.k,docs,host
    test_static_build_is_exactly_the_assembly_of_the_frozen_core_and_the_operation_part=conformance.Conformance.test_static_build_is_exactly_the_assembly_of_the_frozen_core_and_the_operation_part
    test_static_source_carries_the_sealed_parts_unchanged_and_meets_every_rule=conformance.Conformance.test_static_source_carries_the_sealed_parts_unchanged_and_meets_every_rule
    test_static_assembly_yields_the_same_bytes_at_any_other_path_and_no_generated_file_names_a_path=conformance.Conformance.test_static_assembly_yields_the_same_bytes_at_any_other_path_and_no_generated_file_names_a_path
    test_static_unbound_templates_hash_chain_and_null_bindings=conformance.Conformance.test_static_unbound_templates_hash_chain_and_null_bindings
    test_shipped_unbound_dispatch_template_is_refused_by_its_dispatcher_and_a_null_path_is_no_path=conformance.Conformance.test_shipped_unbound_dispatch_template_is_refused_by_its_dispatcher_and_a_null_path_is_no_path
    test_shipped_unbound_documents_refuse_before_anything_is_touched=conformance.Conformance.test_shipped_unbound_documents_refuse_before_anything_is_touched
    test_final_unbound_stdin_payload_refuses_under_isolated_python_and_through_the_reviewed_transport=conformance.Conformance.test_final_unbound_stdin_payload_refuses_under_isolated_python_and_through_the_reviewed_transport
    test_every_unbound_or_foreign_member_has_its_constant_refusal=conformance.Conformance.test_every_unbound_or_foreign_member_has_its_constant_refusal
    test_activation_flag_is_the_constant_of_the_source_in_all_three_documents=conformance.Conformance.test_activation_flag_is_the_constant_of_the_source_in_all_three_documents
    test_owner_is_bound_and_equal_in_authority_and_go=conformance.Conformance.test_owner_is_bound_and_equal_in_authority_and_go
    test_transport_binding_and_writes_flag_in_every_document=conformance.Conformance.test_transport_binding_and_writes_flag_in_every_document
    test_hash_chain_between_the_three_documents=conformance.Conformance.test_hash_chain_between_the_three_documents
    test_host_binding_is_one_non_null_value_in_three_documents_and_the_plan=conformance.Conformance.test_host_binding_is_one_non_null_value_in_three_documents_and_the_plan
    test_effects_are_literal_in_authority_and_go_and_recomputed_from_the_plan=conformance.Conformance.test_effects_are_literal_in_authority_and_go_and_recomputed_from_the_plan
    test_effects_equal_in_authority_and_go_but_not_those_of_the_plan_are_refused=conformance.Conformance.test_effects_equal_in_authority_and_go_but_not_those_of_the_plan_are_refused
    test_claim_root_identity_transport_binding_and_plan_window_member_by_member=conformance.Conformance.test_claim_root_identity_transport_binding_and_plan_window_member_by_member
    test_evidence_names_the_prior_receipts_and_the_operations_the_source_requires=conformance.Conformance.test_evidence_names_the_prior_receipts_and_the_operations_the_source_requires


@pytest.mark.parametrize('shift',[timedelta(days=-1),timedelta(days=1),timedelta(days=2)])
def test_bootstrap_other_date_refuses_before_host_even_with_rebound_hashes(shift):
    docs,_=fx.case();docs.now+=shift;docs.shift(docs.now,docs.now+timedelta(minutes=5));receipt=docs.run(fx.f.Untouchable())
    assert receipt['status']=='REFUSED' and receipt['code']=='DATE_NOT_IN_SCOPE'


@pytest.mark.parametrize('start_delta,end_delta',[(-1,0),(0,-1),(0,1),(1,0)])
def test_smaller_or_shifted_window_is_not_authorized_bootstrap_slot(start_delta,end_delta):
    docs,_=fx.case();start=docs.now+timedelta(seconds=start_delta);end=fx.NOW+timedelta(minutes=5,seconds=end_delta)
    docs.now=max(start,fx.NOW);docs.shift(start,end);receipt=docs.run(fx.f.Untouchable())
    assert receipt['status']=='REFUSED' and receipt['phase_reached']=='AUTHENTICATION'
    assert receipt['code'] in ('BOOTSTRAP_WINDOW_NOT_COMPILED','WINDOW_SPAN')


@pytest.mark.parametrize('open_root',['/mnt','/mnt/day-d-data/r2d2-v2-live'])
def test_new_open_root_is_not_implicitly_allowed(open_root):
    docs,_=fx.case();docs.plan['policy_read']['policy']['directory']['open_root']=open_root;docs.chain()
    receipt=docs.run(fx.f.Untouchable())
    assert receipt['status']=='REFUSED'


def test_reduced_receipt_is_partial_and_retains_consumed_claim():
    docs,host=fx.case();m=docs.k.m;receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS
    receipt.pop('metadata_sha256');receipt['items']['synthetic_large']={'status':'COMPLETE','padding':'x'*100000}
    reduced=m.seal(receipt)
    assert reduced['status']==m.PARTIAL_STATUS and reduced['claim']['usage_consumed'] is True
    assert reduced['claim']['created_by_this_run'] is True and reduced['mutating_calls']['succeeded']>0
    assert fx.f.sealed(reduced) and reduced['size_reductions']
