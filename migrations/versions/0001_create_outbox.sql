-- Create outbox table.
-- revision: 0001
-- down_revision:
-- create_date: 2026-06-23T00:00:00+00:00

CREATE TABLE IF NOT EXISTS outbox (
    id VARCHAR(128) NOT NULL,
    trace_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(256),
    topic VARCHAR(128) NOT NULL,
    kind VARCHAR(128) NOT NULL,
    version INTEGER NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    locked_at TIMESTAMPTZ,
    done_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_outbox PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_outbox_idempotency_key
ON outbox (idempotency_key);
