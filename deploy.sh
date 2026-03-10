#!/bin/bash
set -e

# ============================================================
# Deploy TQF App to Google Cloud Run
# ============================================================
# Usage: ./deploy.sh [PROJECT_ID] [REGION]
# Example: ./deploy.sh my-gcp-project asia-southeast1
# ============================================================

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="${2:-asia-southeast1}"
SERVICE_NAME="tqf-app"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "Project : $PROJECT_ID"
echo "Region  : $REGION"
echo "Image   : $IMAGE"
echo ""

# 1. Set active project
gcloud config set project "$PROJECT_ID"

# 2. Enable required APIs
echo ">> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  firestore.googleapis.com \
  --project "$PROJECT_ID"

# 3. Build & push image via Cloud Build
echo ">> Building image..."
gcloud builds submit --tag "$IMAGE" .

# 4. Deploy to Cloud Run
echo ">> Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 5 \
  --set-env-vars "FLASK_ENV=production" \
  --project "$PROJECT_ID"

echo ""
echo ">> Deploy complete!"
echo ">> URL: $(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)' --project $PROJECT_ID)"
