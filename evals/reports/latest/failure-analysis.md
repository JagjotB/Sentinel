# Five measured failure analyses

These errors come from independent trial rows and were selected mechanically before manual review.

## 1. sentinel_full: `cpu_throttling_002`

- Trace ID: `2d0fc47bfddfb9264e2fca37d2c55825`
- Expected root cause: `cpu_throttling`
- Predicted root cause: `dependency_regression` (supported, confidence 0.679)
- Evidence precision/recall: 0.200/0.667
- Actual total time/tools/models: 418.65 ms / 9 / 2
- Why it failed: The full verifier abstained or selected a competing signature under the measured evidence.
- Missing discriminators: `cpu_throttle, latency_spike, resource_limit`.
- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.

## 2. sentinel_full: `selector_mismatch_001`

- Trace ID: `7b151602a5c6170db91b402f59bb720a`
- Expected root cause: `selector_mismatch`
- Predicted root cause: `bad_readiness_probe` (supported, confidence 0.724)
- Evidence precision/recall: 0.200/0.667
- Actual total time/tools/models: 452.70 ms / 11 / 2
- Why it failed: The full verifier abstained or selected a competing signature under the measured evidence.
- Missing discriminators: `empty_endpoints, selector_diff, healthy_pods`.
- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.

## 3. sentinel_full: `bad_configmap_001`

- Trace ID: `2c6f7912184eca997797c385964ede41`
- Expected root cause: `bad_configmap`
- Predicted root cause: `undetermined` (insufficient_evidence, confidence 0.490)
- Evidence precision/recall: 0.176/1.000
- Actual total time/tools/models: 454.36 ms / 11 / 2
- Why it failed: The full verifier abstained or selected a competing signature under the measured evidence.
- Missing discriminators: `configmap_diff, connection_error, rollout_event`.
- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.

## 4. sentinel_full: `image_pull_failure_002`

- Trace ID: `47211c36af0dff3440a8805bd3f06078`
- Expected root cause: `image_pull_failure`
- Predicted root cause: `undetermined` (insufficient_evidence, confidence 0.490)
- Evidence precision/recall: 0.176/1.000
- Actual total time/tools/models: 431.19 ms / 11 / 2
- Why it failed: The full verifier abstained or selected a competing signature under the measured evidence.
- Missing discriminators: `image_pull_backoff, manifest_diff, zero_ready_pods`.
- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.

## 5. sentinel_full: `dependency_timeout_002`

- Trace ID: `4bb65aa8677d3ffbd1faf458c6a8f7b3`
- Expected root cause: `dependency_timeout`
- Predicted root cause: `undetermined` (insufficient_evidence, confidence 0.490)
- Evidence precision/recall: 0.214/1.000
- Actual total time/tools/models: 370.51 ms / 7 / 2
- Why it failed: The full verifier abstained or selected a competing signature under the measured evidence.
- Missing discriminators: `downstream_latency, timeout_log, trace_span`.
- Corrective action: retain this exact scenario/system pair as a regression fixture and require one additional independent category-specific signal before a supported claim.

Selection distribution: sentinel_full=5
