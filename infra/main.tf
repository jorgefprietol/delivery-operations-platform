terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.6.0"
    }
  }
}

provider "docker" {}

variable "image" {
  type        = string
  description = "Verified GHCR image pinned by registry digest"
  validation {
    condition     = can(regex("^ghcr\\.io/jorgefprietol/delivery-operations-platform@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Use the project's GHCR image with an immutable sha256 digest."
  }
}

variable "operator_token" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.operator_token) >= 32
    error_message = "Token must contain at least 32 characters."
  }
}

variable "approver_token" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.approver_token) >= 32
    error_message = "Token must contain at least 32 characters."
  }
}

variable "port" {
  type    = number
  default = 18096
  validation {
    condition     = var.port >= 1024 && var.port <= 65535 && floor(var.port) == var.port
    error_message = "Port must be an integer between 1024 and 65535."
  }
}

resource "docker_volume" "data" {
  name = "delivery-operations-iac-data"
}

resource "docker_image" "api" {
  name         = var.image
  keep_locally = true
}

resource "docker_container" "api" {
  name      = "delivery-operations-iac"
  image     = docker_image.api.image_id
  restart   = "unless-stopped"
  read_only = true
  memory    = 256
  env = [
    "OPERATOR_TOKEN=${var.operator_token}",
    "APPROVER_TOKEN=${var.approver_token}"
  ]
  ports {
    internal = 8080
    external = var.port
    ip       = "127.0.0.1"
  }
  volumes {
    volume_name    = docker_volume.data.name
    container_path = "/data"
  }
  tmpfs = { "/tmp" = "rw,noexec,nosuid,size=32m" }
  capabilities {
    drop = ["ALL"]
  }
  security_opts = ["no-new-privileges:true"]
  healthcheck {
    test         = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2)"]
    interval     = "10s"
    timeout      = "3s"
    start_period = "15s"
    retries      = 6
  }
  wait         = true
  wait_timeout = 120
  lifecycle {
    precondition {
      condition     = var.operator_token != var.approver_token
      error_message = "Operator and approver credentials must differ."
    }
  }
}

output "dashboard_url" {
  value = "http://127.0.0.1:${var.port}"
}
