-- Scope the read-through leaderboard cache and its freshness marker to the chain on
-- which each score was resolved. The previous global rows could survive an Oracle network
-- switch and be served as if they described the newly configured chain.
--
-- This cache is derived data and safe to rebuild. Clear it before adding required provenance
-- rather than inventing a chain ID for historical rows whose origin cannot be established.
TRUNCATE TABLE leaderboard_cache, leaderboard_sync;

ALTER TABLE leaderboard_cache
    ADD COLUMN chain_id BIGINT NOT NULL;
ALTER TABLE leaderboard_cache
    DROP CONSTRAINT leaderboard_cache_pkey;
ALTER TABLE leaderboard_cache
    ADD PRIMARY KEY (agent_id, chain_id);
CREATE INDEX idx_leaderboard_cache_chain_id ON leaderboard_cache(chain_id);

ALTER TABLE leaderboard_sync
    ADD COLUMN chain_id BIGINT NOT NULL;
ALTER TABLE leaderboard_sync
    DROP CONSTRAINT leaderboard_sync_pkey;
ALTER TABLE leaderboard_sync
    ADD PRIMARY KEY (chain_id);
