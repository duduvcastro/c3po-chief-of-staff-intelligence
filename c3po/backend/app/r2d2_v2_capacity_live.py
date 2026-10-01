"""Planner injected into the existing controller, never a second stream writer."""
from .r2d2_v2_capacity_bound import DailyCapacityBinding
from .r2d2_v2_live_group import plan_live_group
from .r2d2_v2_calendar import NEW_YORK
from .r2d2_v2_store import digest,utc,ShadowIntegrityError


def capacity_live_plan(saved,release,policy,now,*,calendar,authority):
    fallback=plan_live_group(saved,release,capacity=policy['capacity'])
    try:
        evidence=authority.check_restore_revocation(now)
        if policy['capacity']!=550:raise ShadowIntegrityError('CAPACITY_POLICY')
        day=now.astimezone(NEW_YORK).date().isoformat()
        persisted=saved['state']['sessions'][day]['capacity_binding']
        binding=DailyCapacityBinding.restore(persisted,release=release,calendar=calendar,
            authority_verifier=lambda doc:authority.verify_binding(doc,now))
        p=binding.current_session(state=saved['state'],current_day=day,now=now,calendar=calendar)
        if digest(policy)!=digest(p['contract']['policy']):raise ShadowIntegrityError('CAPACITY_POLICY_CHANGED')
        return {**fallback,'symbols':p['monitored_symbols'],'capacity_plan_sha':binding.sha,'capacity_mode':'BOUND_MONITORED',
                'capacity_veto_mode':getattr(authority,'capacity_veto_mode','CONTINUOUS'),
                'capacity_evidence_valid_until':evidence['valid_until'] if evidence is not None else None,
                'capacity_fallback_symbols':fallback['symbols']}
    except Exception:
        return {**fallback,'capacity_plan_sha':None,'capacity_mode':'OPEN_ONLY_FALLBACK'}
