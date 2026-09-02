# Five failure analyses

These are observed errors from the measured portfolio run, selected before any manual review.

## 1. sentinel_full: `bad_configmap_001`

- Expected root cause: `bad_configmap`
- Predicted root cause: `undetermined` (insufficient_evidence)
- Evidence recall: 0.000
- Why it failed: the verifier rejected the leading diagnosis because the selected evidence did not clear the corroboration margin against a competing signature.
- Missing discriminators: `configmap_diff, connection_error, rollout_event`.
- Corrective action: retain this seed as a regression fixture and require both the ConfigMap diff and an upstream URL validation error.

## 2. sentinel_full: `image_pull_failure_002`

- Expected root cause: `image_pull_failure`
- Predicted root cause: `undetermined` (insufficient_evidence)
- Evidence recall: 0.000
- Why it failed: the verifier rejected the leading diagnosis because the selected evidence did not clear the corroboration margin against a competing signature.
- Missing discriminators: `image_pull_backoff, manifest_diff, zero_ready_pods`.
- Corrective action: retain this seed as a regression fixture and pair registry manifest existence with the ImagePullBackOff event.

## 3. sentinel_full: `dependency_timeout_002`

- Expected root cause: `dependency_timeout`
- Predicted root cause: `undetermined` (insufficient_evidence)
- Evidence recall: 0.000
- Why it failed: the verifier rejected the leading diagnosis because the selected evidence did not clear the corroboration margin against a competing signature.
- Missing discriminators: `downstream_latency, timeout_log, trace_span`.
- Corrective action: retain this seed as a regression fixture and correlate the downstream trace span with the client timeout log.

## 4. sentinel_full: `slow_query_lock_002`

- Expected root cause: `slow_query_lock`
- Predicted root cause: `undetermined` (insufficient_evidence)
- Evidence recall: 0.000
- Why it failed: the verifier rejected the leading diagnosis because the selected evidence did not clear the corroboration margin against a competing signature.
- Missing discriminators: `lock_wait, slow_query, trace_span`.
- Corrective action: retain this seed as a regression fixture and collect a lock-wait sample and the blocked query fingerprint.

## 5. sentinel_full: `downstream_rate_limit_001`

- Expected root cause: `downstream_rate_limit`
- Predicted root cause: `undetermined` (insufficient_evidence)
- Evidence recall: 0.000
- Why it failed: the verifier rejected the leading diagnosis because the selected evidence did not clear the corroboration margin against a competing signature.
- Missing discriminators: `http_429_cluster, rate_limit_headers, traffic_spike`.
- Corrective action: retain this seed as a regression fixture and require a 429 cluster plus the rate-limit response headers.

Selection distribution: sentinel_full=5
