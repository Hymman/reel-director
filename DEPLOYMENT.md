# Google Cloud Run Deployment

The runtime container serves the FastAPI API, the compiled React application, SPA deep links, and FFmpeg-based finishing.

## Required resources

1. A Google Cloud project with billing enabled.
2. Cloud Run, Cloud Build, Artifact Registry, Vertex AI, Cloud Storage, Secret Manager, and IAM Credentials APIs.
3. A private GCS bucket. Do not grant `allUsers` or `allAuthenticatedUsers` access.
4. A dedicated Cloud Run service account with Vertex AI User, bucket-scoped object access, and Secret Manager access to the Parallel key.
5. The Parallel API key stored in Secret Manager as `parallel-api-key`.

## Build and deploy

```bash
PROJECT_ID="your-google-cloud-project"
REGION="us-central1"
REPOSITORY="reel-director"
SERVICE="reel-director"
BUCKET="your-private-bucket"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com storage.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com --project "$PROJECT_ID"

gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location "$REGION" --project "$PROJECT_ID"

gcloud builds submit --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:submission" --project "$PROJECT_ID"

gcloud run deploy "$SERVICE" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:submission" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "reel-director-run@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-env-vars "ENVIRONMENT=production,DEMO_MODE=false,MEDIA_DELIVERY_MODE=signed,USE_VERTEX_AI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GCS_BUCKET_NAME=$BUCKET,GEMINI_MODEL_NAME=gemini-2.5-flash,VEO_MODEL_NAME=veo-3.1-fast-generate-001,IMAGE_MODEL_NAME=gemini-2.5-flash-image" \
  --set-secrets "PARALLEL_API_KEY=parallel-api-key:latest" \
  --memory 4Gi \
  --cpu 2 \
  --timeout 3600 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 1 \
  --project "$PROJECT_ID"
```

`--max-instances 1` matches the hackathon build's JSON-backed state. Instance replacement can still clear local metadata; move state to Firestore or Cloud SQL for a general production release.

## Post-deploy acceptance

```bash
SERVICE_URL="$(gcloud run services describe reel-director --region us-central1 --format='value(status.url)')"
curl -fsS "$SERVICE_URL/api/health"
curl -fsS "$SERVICE_URL/"
curl -fsS "$SERVICE_URL/campaigns/new"
```

Verify that the bucket is private, the app opens in English, campaign routes survive refresh, media seeking returns HTTP 206, downloads work, and no credential or workspace identity appears in a client URL.
