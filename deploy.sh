#!/bin/bash
set -e

# ============================================================
# Deploy TQF App to Google Cloud Run
# ============================================================
# Usage: ./deploy.sh [PROJECT_ID] [REGION]
# Example: ./deploy.sh my-gcp-project asia-southeast1
# ============================================================

PROJECT_ID="${1:-qualificationsframework}"
REGION="${2:-asia-southeast1}"
SERVICE_NAME="tqf-app"
REPO_NAME="tqf-repo"

# Artifact Registry image path (replaces deprecated gcr.io)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "(unset)" ]; then
  echo "ERROR: PROJECT_ID is not set."
  echo "  Run: gcloud config set project YOUR_PROJECT_ID"
  echo "  Or:  ./deploy.sh YOUR_PROJECT_ID"
  exit 1
fi

echo "Project : $PROJECT_ID"
echo "Region  : $REGION"
echo "Image   : $IMAGE"
echo ""

# -- SECRET_KEY -------------------------------------------------------
# Use an existing env var, or generate a fresh random key each deploy.
if [ -z "$SECRET_KEY" ]; then
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || openssl rand -hex 32)
  echo ">> Generated new SECRET_KEY (stored only in this shell session)"
fi

# 1. Set active project
gcloud config set project "$PROJECT_ID"

# 2. Enable required APIs
echo ">> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  --project "$PROJECT_ID"

# 3. Create Artifact Registry repo (idempotent — skips if already exists)
echo ">> Ensuring Artifact Registry repository exists..."
gcloud artifacts repositories describe "$REPO_NAME" \
  --location "$REGION" \
  --project "$PROJECT_ID" > /dev/null 2>&1 \
|| gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format docker \
  --location "$REGION" \
  --project "$PROJECT_ID"

# 4. Configure Docker auth for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 5. Build & push image via Cloud Build
echo ">> Building image..."
gcloud builds submit --tag "$IMAGE" .

# 6. Deploy to Cloud Run
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
  --set-env-vars "FLASK_ENV=production,SECRET_KEY=${SECRET_KEY}" \
  --project "$PROJECT_ID"

echo ""
echo ">> Deploy complete!"
echo ">> URL: $(gcloud run services describe $SERVICE_NAME \
  --platform managed --region $REGION \
  --format 'value(status.url)' \
  --project $PROJECT_ID)"
