#!/usr/bin/env bash
# Build, push, and deploy the ACE Lambda stack (scan + alert dispatcher).
#
# Idempotent: creates the ECR repo / SQS queue / event-source mapping only if
# missing, then pushes the image and updates both Lambda functions.
#
# Usage:  scripts/deploy_aws.sh [--skip-build]
# Config: env vars, falling back to .env (last occurrence wins).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

load_env() {
  [ -f .env ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    local key="${line%%=*}" val="${line#*=}"
    case "$key" in *[!A-Za-z0-9_]*) continue ;; esac
    val="${val%\"}"; val="${val#\"}"
    # Skip empty values so blank .env entries (e.g. AWS_ACCESS_KEY_ID=) do not
    # shadow real credentials from ~/.aws or the ambient environment.
    [ -n "$val" ] || continue
    printf -v "$key" '%s' "$val"
    export "$key"
  done < .env
}
load_env

AWS_REGION="${AWS_REGION:-ap-south-1}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
ECR_REPO="${ECR_REPO:-ace-rhg-${ENVIRONMENT}}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SCAN_FN="${SCAN_FN:-ace-scan-${ENVIRONMENT}}"
DISPATCH_FN="${DISPATCH_FN:-ace-dispatcher-${ENVIRONMENT}}"
QUEUE_NAME="${QUEUE_NAME:-ace-alerts-${ENVIRONMENT}.fifo}"
API_NAME="${API_NAME:-ace-api-${ENVIRONMENT}}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker not found"
command -v aws >/dev/null || die "aws CLI not found"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" || die "no AWS credentials"
ECR_HOST="${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_HOST}/${ECR_REPO}:${IMAGE_TAG}"

log "account=${ACCOUNT} region=${AWS_REGION} image=${IMAGE_URI}"

# --- ECR ----------------------------------------------------------------------
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null
log "ECR repo ready: ${ECR_REPO}"

# --- Build & push -------------------------------------------------------------
if [ "${1:-}" != "--skip-build" ]; then
  log "building image (linux/amd64)"
  docker build --platform linux/amd64 \
    -f infra/docker/Dockerfile.lambda \
    -t "$IMAGE_URI" .
fi

log "docker login + push"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_HOST" >/dev/null
docker push "$IMAGE_URI"

# --- SQS ----------------------------------------------------------------------
if ! aws sqs get-queue-url --queue-name "$QUEUE_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  log "creating SQS queue: ${QUEUE_NAME}"
  aws sqs create-queue --queue-name "$QUEUE_NAME" --region "$AWS_REGION" \
    --attributes FifoQueue=true,ContentBasedDeduplication=true,VisibilityTimeout=60 >/dev/null
fi
QUEUE_URL="$(aws sqs get-queue-url --queue-name "$QUEUE_NAME" --region "$AWS_REGION" --query QueueUrl --output text)"
QUEUE_ARN="$(aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names QueueArn --region "$AWS_REGION" --query 'Attributes.QueueArn' --output text)"
log "queue ready: ${QUEUE_URL}"

# --- Lambda: scan -------------------------------------------------------------
log "updating ${SCAN_FN}"
aws lambda update-function-code --function-name "$SCAN_FN" --image-uri "$IMAGE_URI" --region "$AWS_REGION" >/dev/null
aws lambda wait function-updated --function-name "$SCAN_FN" --region "$AWS_REGION"
aws lambda update-function-configuration --function-name "$SCAN_FN" --region "$AWS_REGION" \
  --timeout 60 --memory-size 512 \
  --image-config 'Command=ace.lambda_handler.handler' \
  --environment "Variables={OPA_URL=http://localhost:8181,ACE_METRICS_ENABLED=false,ACE_METRICS_PORT=9090,SQS_ALERT_QUEUE_URL=${QUEUE_URL},DASHBOARD_URL=${DASHBOARD_URL}}" >/dev/null
aws lambda wait function-updated --function-name "$SCAN_FN" --region "$AWS_REGION"

# --- Lambda: dispatcher -------------------------------------------------------
log "updating ${DISPATCH_FN}"
aws lambda update-function-code --function-name "$DISPATCH_FN" --image-uri "$IMAGE_URI" --region "$AWS_REGION" >/dev/null
aws lambda wait function-updated --function-name "$DISPATCH_FN" --region "$AWS_REGION"
DISPATCH_ENV="Variables={SQS_ALERT_QUEUE_URL=${QUEUE_URL},SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}}"
aws lambda update-function-configuration --function-name "$DISPATCH_FN" --region "$AWS_REGION" \
  --timeout 30 --memory-size 256 \
  --image-config 'Command=handlers.alert_dispatcher_handler.handler' \
  --environment "$DISPATCH_ENV" >/dev/null
aws lambda wait function-updated --function-name "$DISPATCH_FN" --region "$AWS_REGION"
[ -n "$SLACK_WEBHOOK_URL" ] && log "dispatcher Slack webhook: set (len=${#SLACK_WEBHOOK_URL})" \
  || log "WARNING: SLACK_WEBHOOK_URL empty — dispatcher will have no channels"

# --- SQS -> dispatcher trigger ------------------------------------------------
EXISTING="$(aws lambda list-event-source-mappings --function-name "$DISPATCH_FN" \
  --event-source-arn "$QUEUE_ARN" --region "$AWS_REGION" \
  --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || echo None)"
if [ "$EXISTING" = "None" ] || [ -z "$EXISTING" ]; then
  log "creating event source mapping SQS -> ${DISPATCH_FN}"
  aws lambda create-event-source-mapping --function-name "$DISPATCH_FN" \
    --event-source-arn "$QUEUE_ARN" --batch-size 10 --region "$AWS_REGION" >/dev/null
else
  log "event source mapping already present (${EXISTING})"
fi

# --- API Gateway permission ---------------------------------------------------
API_ID="$(aws apigatewayv2 get-apis --region "$AWS_REGION" \
  --query "Items[?Name=='${API_NAME}'].ApiId | [0]" --output text 2>/dev/null || echo None)"
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
  SRC_ARN="arn:aws:execute-api:${AWS_REGION}:${ACCOUNT}:${API_ID}/*/*"
  aws lambda add-permission --function-name "$SCAN_FN" \
    --statement-id AllowAPIGatewayInvoke --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com --source-arn "$SRC_ARN" --region "$AWS_REGION" >/dev/null 2>&1 \
    || log "invoke permission already present"
  ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com"
else
  die "API '${API_NAME}' not found — create it (terraform apply) or set API_NAME"
fi

# --- Smoke test ---------------------------------------------------------------
log "smoke testing ${ENDPOINT}/health"
for _ in $(seq 1 20); do
  if curl -fsS -m 20 "${ENDPOINT}/health" >/dev/null 2>&1; then
    log "healthy: $(curl -fsS -m 20 "${ENDPOINT}/health")"
    break
  fi
  sleep 3
done

log "done. API: ${ENDPOINT}  image: ${IMAGE_URI}"
