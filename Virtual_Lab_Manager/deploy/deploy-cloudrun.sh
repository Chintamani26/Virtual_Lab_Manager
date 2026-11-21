#!/usr/bin/env bash
# =====================================================================================
# Deploy Virtual Lab Manager to Google Cloud Run (backend API + Next.js frontend).
#
# Prereqs: gcloud CLI logged in (`gcloud auth login`), billing-enabled project.
# Usage:   PROJECT_ID=my-project ./deploy/deploy-cloudrun.sh
#
# Secrets are read from Secret Manager. Create them once (values are prompted, never echoed):
#   ./deploy/deploy-cloudrun.sh secrets
# Optional secrets: database-url (omit => in-memory demo mode), judge0-api-key.
# =====================================================================================
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-south1}"          # Mumbai
API_SERVICE="${API_SERVICE:-vlm-api}"
WEB_SERVICE="${WEB_SERVICE:-vlm-web}"
REPO="${REPO:-vlm}"                       # Artifact Registry repo for the frontend image
JUDGE0_URL="${JUDGE0_URL:-}"              # e.g. https://judge0-ce.p.rapidapi.com
JUDGE0_RAPIDAPI_HOST="${JUDGE0_RAPIDAPI_HOST:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud config set project "$PROJECT_ID" >/dev/null

secret_exists() { gcloud secrets describe "$1" >/dev/null 2>&1; }

if [[ "${1:-}" == "secrets" ]]; then
  gcloud services enable secretmanager.googleapis.com
  for name in gemini-api-key jwt-secret database-url judge0-api-key; do
    if secret_exists "$name"; then echo "✓ $name exists"; continue; fi
    if [[ "$name" == "jwt-secret" ]]; then
      openssl rand -base64 48 | tr -d '\n' | gcloud secrets create "$name" --data-file=- && echo "✓ generated $name"
      continue
    fi
    read -r -s -p "Value for $name (Enter to skip): " value; echo
    [[ -z "$value" ]] && { echo "  skipped $name"; continue; }
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=-
  done
  PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  for name in gemini-api-key jwt-secret database-url judge0-api-key; do
    secret_exists "$name" && gcloud secrets add-iam-policy-binding "$name" \
      --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
      --role="roles/secretmanager.secretAccessor" >/dev/null && echo "✓ runtime can read $name"
  done
  exit 0
fi

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# ---------------------------------------------------------------- backend
SECRETS="GEMINI_API_KEY=gemini-api-key:latest,JWT_SECRET=jwt-secret:latest"
ENV_VARS="APP_ENV=production,DEMO_MODE=true"
SCALE_FLAGS=(--min-instances=1)
if secret_exists database-url; then
  SECRETS+=",DATABASE_URL=database-url:latest"
else
  echo "! No database-url secret: deploying in-memory demo mode (single instance)."
  SCALE_FLAGS+=(--max-instances=1)
fi
if [[ -n "$JUDGE0_URL" ]]; then
  ENV_VARS+=",EXECUTION_ENGINE=judge0,JUDGE0_URL=${JUDGE0_URL},JUDGE0_RAPIDAPI_HOST=${JUDGE0_RAPIDAPI_HOST}"
  secret_exists judge0-api-key && SECRETS+=",JUDGE0_API_KEY=judge0-api-key:latest"
else
  echo "! JUDGE0_URL not set: student code runs in the container's local runner (demo only)."
  ENV_VARS+=",EXECUTION_ENGINE=local,ALLOW_LOCAL_EXECUTION_IN_PRODUCTION=true"
fi

gcloud run deploy "$API_SERVICE" \
  --source "$ROOT/backend" --region "$REGION" --allow-unauthenticated \
  --cpu=1 --memory=1Gi --timeout=120 "${SCALE_FLAGS[@]}" \
  --set-env-vars "$ENV_VARS" --set-secrets "$SECRETS"

API_URL="$(gcloud run services describe "$API_SERVICE" --region "$REGION" --format='value(status.url)')"
echo "✓ API: $API_URL"

# ---------------------------------------------------------------- frontend (API URL baked at build time)
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/web:$(date +%Y%m%d-%H%M%S)"

gcloud builds submit "$ROOT/frontend" --config "$ROOT/deploy/cloudbuild.frontend.yaml" \
  --substitutions "_IMAGE=${IMAGE},_API_URL=${API_URL}"

gcloud run deploy "$WEB_SERVICE" --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --cpu=1 --memory=512Mi --min-instances=1

WEB_URL="$(gcloud run services describe "$WEB_SERVICE" --region "$REGION" --format='value(status.url)')"

# allow the frontend origin on the API
gcloud run services update "$API_SERVICE" --region "$REGION" --update-env-vars "CORS_ORIGINS=${WEB_URL}"

echo
echo "================================================================"
echo " Frontend : $WEB_URL"
echo " API      : $API_URL   (health: $API_URL/api/health)"
echo "================================================================"
