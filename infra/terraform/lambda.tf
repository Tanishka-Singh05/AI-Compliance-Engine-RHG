terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "dashboard_url" {
  description = "Base URL used in report/alert links (Grafana)."
  type        = string
  default     = ""
}

variable "slack_webhook_url" {
  type      = string
  default   = ""
  sensitive = true
}

variable "private_subnet_ids" {
  description = "VPC subnets for the Lambdas. Empty = no VPC config (public egress)."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security groups for the Lambdas (only used with private_subnet_ids)."
  type        = list(string)
  default     = []
}

locals {
  name_prefix   = "ace-${var.environment}"
  scan_fn       = "ace-scan-${var.environment}"
  dispatcher_fn = "ace-dispatcher-${var.environment}"
  image_uri     = "${aws_ecr_repository.ace.repository_url}:${var.image_tag}"
  use_vpc       = length(var.private_subnet_ids) > 0
}

data "aws_caller_identity" "current" {}

# --- Container registry -------------------------------------------------------

resource "aws_ecr_repository" "ace" {
  name                 = "ace-rhg-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Alerts queue -------------------------------------------------------------

resource "aws_sqs_queue" "ace_alerts" {
  name                        = "ace-alerts-${var.environment}.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  message_retention_seconds   = 86400
  visibility_timeout_seconds  = 60
}

# --- IAM ----------------------------------------------------------------------

resource "aws_iam_role" "ace_lambda" {
  name = "ace-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.ace_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "sqs_send" {
  name = "ace-sqs-send-${var.environment}"
  role = aws_iam_role.ace_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
      Resource = aws_sqs_queue.ace_alerts.arn
    }]
  })
}

# --- Lambda: scan (FastAPI + OPA + Mangum) ------------------------------------

resource "aws_lambda_function" "ace_scan" {
  function_name = local.scan_fn
  role          = aws_iam_role.ace_lambda.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  timeout       = 60
  memory_size   = 512

  image_config {
    command = ["ace.lambda_handler.handler"]
  }

  environment {
    variables = {
      OPA_URL             = "http://localhost:8181"
      ACE_METRICS_ENABLED = "false"
      ACE_METRICS_PORT    = "9090"
      SQS_ALERT_QUEUE_URL = aws_sqs_queue.ace_alerts.url
      DASHBOARD_URL       = var.dashboard_url
    }
  }

  dynamic "vpc_config" {
    for_each = local.use_vpc ? [1] : []
    content {
      subnet_ids         = var.private_subnet_ids
      security_group_ids = var.security_group_ids
    }
  }
}

# --- Lambda: alert dispatcher (SQS -> Slack) ----------------------------------

resource "aws_lambda_function" "alert_dispatcher" {
  function_name = local.dispatcher_fn
  role          = aws_iam_role.ace_lambda.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  timeout       = 30
  memory_size   = 256

  image_config {
    command = ["handlers.alert_dispatcher_handler.handler"]
  }

  environment {
    variables = {
      SLACK_WEBHOOK_URL   = var.slack_webhook_url
      SQS_ALERT_QUEUE_URL = aws_sqs_queue.ace_alerts.url
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_to_alert" {
  event_source_arn = aws_sqs_queue.ace_alerts.arn
  function_name    = aws_lambda_function.alert_dispatcher.arn
  batch_size       = 10
}

# --- API Gateway (HTTP API) ---------------------------------------------------

resource "aws_apigatewayv2_api" "ace" {
  name          = "ace-api-${var.environment}"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "ace_scan" {
  api_id                 = aws_apigatewayv2_api.ace.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ace_scan.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.ace.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.ace_scan.id}"
}

resource "aws_apigatewayv2_route" "scan" {
  api_id    = aws_apigatewayv2_api.ace.id
  route_key = "POST /ace/scan"
  target    = "integrations/${aws_apigatewayv2_integration.ace_scan.id}"
}

resource "aws_apigatewayv2_route" "mutate" {
  api_id    = aws_apigatewayv2_api.ace.id
  route_key = "POST /ace/mutate"
  target    = "integrations/${aws_apigatewayv2_integration.ace_scan.id}"
}

resource "aws_apigatewayv2_route" "scan_and_mutate" {
  api_id    = aws_apigatewayv2_api.ace.id
  route_key = "POST /ace/scan-and-mutate"
  target    = "integrations/${aws_apigatewayv2_integration.ace_scan.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.ace.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ace_scan.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ace.execution_arn}/*/*"
}

# --- Outputs ------------------------------------------------------------------

output "api_endpoint" {
  value = aws_apigatewayv2_stage.default.invoke_url
}

output "scan_function" {
  value = aws_lambda_function.ace_scan.function_name
}

output "dispatcher_function" {
  value = aws_lambda_function.alert_dispatcher.function_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.ace.repository_url
}

output "alerts_queue_url" {
  value = aws_sqs_queue.ace_alerts.url
}
