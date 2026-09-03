ALTER TABLE r2d2_shadow_candidates
    DROP CONSTRAINT IF EXISTS r2d2_shadow_candidates_cascade_step_check;

ALTER TABLE r2d2_shadow_candidates
    ADD CONSTRAINT r2d2_shadow_candidates_cascade_step_check
    CHECK (
        cascade_step IN (
            'technical_review_capacity',
            'daily_order_capacity',
            'portfolio_capacity',
            'session_reentry_policy',
            'entry_quality',
            'entry_confirmation',
            'entry_cycle_capacity',
            'entry_execution'
        )
    );
