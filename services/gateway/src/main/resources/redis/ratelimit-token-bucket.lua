-- Distributed token-bucket rate limiter for the SpecProof edge.
--
-- One Redis hash per bucket key holds {tokens, ts}. The whole admission decision
-- is ONE EVAL, so two gateway replicas racing on the same key cannot both believe
-- a token was free (the lost-update a read-then-write would suffer).
--
-- Refill is LAZY: we add (now - ts) * rate and cap at capacity. Cost is O(1)
-- regardless of how long the bucket sat idle. `ts` advances to `now` on every
-- call so the next call measures only the interval since this one -- no drift, no
-- double-counting of idle time. PEXPIRE lets Redis own the wall clock: an idle
-- key simply expires instead of being kept warm by a fleet that forgot it.
--
-- ARGV: capacity, rate_per_ms, now_ms, requested, ttl_ms
-- Returns a flat integer list: { allowed(1|0), remaining_tokens, retry_after_ms }

local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])   -- tokens replenished per millisecond
local now      = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl      = tonumber(ARGV[5])

local data   = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts     = tonumber(data[2])

if tokens == nil then
  -- First sight of this key: hand out a full bucket, start the clock now.
  tokens = capacity
  ts = now
end

local delta = now - ts
if delta < 0 then delta = 0 end

-- Lazy refill, capped at burst capacity.
local filled = tokens + delta * rate
if filled > capacity then filled = capacity end

local allowed = 0
local remaining = filled
if filled >= requested then
  allowed = 1
  remaining = filled - requested
end

-- When denied, tell the caller how long until one token frees up so it can
-- back off instead of spinning. Ceil keeps the hint honest (never "0ms").
local retry_after = 0
if allowed == 0 then
  retry_after = math.ceil((requested - filled) / rate)
  if retry_after < 1 then retry_after = 1 end
end

-- Persist. `ts` moves to `now`; `tokens` holds what is left (unchanged when we
-- did not admit, already decremented when we did).
redis.call('HSET', key, 'tokens', tostring(remaining), 'ts', tostring(now))
redis.call('PEXPIRE', key, ttl)

return { allowed, math.floor(remaining), retry_after }
