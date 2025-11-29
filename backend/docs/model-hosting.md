# Model Hosting Recommendation

For AIM's film-analysis workloads (possession tracking, jersey detection, shooter profiling), we need GPU-backed inference with low-latency REST hooks. Recommended approach:

1. **Modal or AWS SageMaker Endpoint**
   - Package the HanaFEKI-derived models into Docker images.
   - Deploy as autoscaling GPU endpoints (SageMaker `ml.g4dn.xlarge` or Modal's GPU containers).
   - Expose HTTPS endpoints secured via bearer tokens. Configure `MODEL_GATEWAY_URL` + token in `.env`.

2. **Job Pipeline**
   - Film upload triggers a queue job (e.g., AWS SQS + Lambda worker) that calls the model endpoint.
   - Store possession outputs + metadata in PostgreSQL.

3. **Fallback / Batch Processing**
   - For heavy training runs, use AWS Batch or GCP Vertex AI custom jobs.

This keeps the FastAPI backend lightweight while offloading GPU work to a managed service.
