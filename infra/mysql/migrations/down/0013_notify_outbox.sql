-- Down for 0013_notify_outbox.sql (manual rollback only — the runner never
-- applies files under down/). Drops the notification outbox; any rows still
-- pending delivery are lost, which is acceptable ONLY because the direct
-- send lane (SPECPROOF_NOTIFY_OUTBOX off) does not depend on this table.

DROP TABLE IF EXISTS notify_outbox;
