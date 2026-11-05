terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
}

provider "azurerm" {
  features {}
}

variable "prefix"   { default = "citriage" }
variable "location" { default = "centralindia" }
variable "image_tag" { default = "latest" }

# Secrets are passed in, never committed: TF_VAR_azure_openai_key / TF_VAR_github_token
variable "github_repo" {
  type        = string
  description = "owner/repo whose CI runs the agent triages"
}
variable "azure_openai_endpoint" { type = string }
variable "azure_openai_key" {
  type      = string
  sensitive = true
}
variable "github_token" {
  type      = string
  sensitive = true
}

resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
}

resource "azurerm_container_registry" "acr" {
  name                = "${var.prefix}acr${substr(md5(azurerm_resource_group.rg.id), 0, 6)}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${var.prefix}-logs"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "env" {
  name                       = "${var.prefix}-env"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
}

resource "azurerm_container_app" "app" {
  name                         = "${var.prefix}-app"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }
  secret {
    name  = "aoai-key"
    value = var.azure_openai_key
  }
  secret {
    name  = "gh-token"
    value = var.github_token
  }

  template {
    min_replicas = 1 # keep 1: pending approvals live in process memory (see README)
    max_replicas = 1

    container {
      name   = "agent"
      image  = "${azurerm_container_registry.acr.login_server}/ci-triage-agent:${var.image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = var.azure_openai_endpoint
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "aoai-key"
      }
      env {
        name        = "GITHUB_TOKEN"
        secret_name = "gh-token"
      }
      env {
        name  = "TRIAGE_SOURCE_MODE"
        value = "github"
      }
      env {
        name  = "TRIAGE_GITHUB_REPO"
        value = var.github_repo
      }
      env {
        name  = "TRIAGE_DRY_RUN"
        value = "true" # flip to false only after you trust the agent
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/healthz"
        port      = 8000
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

output "app_url"      { value = "https://${azurerm_container_app.app.ingress[0].fqdn}" }
output "acr_name"     { value = azurerm_container_registry.acr.name }
output "acr_server"   { value = azurerm_container_registry.acr.login_server }
