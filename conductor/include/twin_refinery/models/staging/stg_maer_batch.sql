-- stg_maer_batch.sql
-- Staging model: reads from raw HDFS load table, enforces P5 org_name seal
-- Source: raw.maer_batch_01 (loaded by scripts/load_hdfs_to_pg.py)
-- Governance: org_name must exclusively be 'Habib Bank' (P5)

with source as (
    select * from {{ source('raw', 'maer_batch_01') }}
),

p5_validated as (
    select
        session_id,
        org_name,
        channel,
        journey_step,
        event_ts,
        step_duration_s,
        outcome,
        hmac_ref,
        -- P5 guard: flag any row where org_name is not sealed
        case
            when org_name != 'Habib Bank' then 'P5_VIOLATION'
            else 'SEALED'
        end as p5_status,
        -- P4 guard: flag any row where hmac_ref was not placeholder
        case
            when hmac_ref != 'HASH_PENDING_ORIGINAL' then 'P4_VIOLATION'
            else 'SEALED'
        end as p4_status
    from source
),

sealed as (
    select * from p5_validated
    where p5_status = 'SEALED'
      and p4_status = 'SEALED'
)

select * from sealed
