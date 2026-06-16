# Terraform Plan AI Review

## Overall Risk
High

## Approval Recommendation
Do not apply until reviewed

## Summary
This plan creates a new prod-tagged Azure environment with major security and exposure concerns. The biggest risks are public network exposure on Key Vault, SQL, Storage, Web App and AKS, weak or disabled protection settings, hardcoded secret exposure in app settings, overly permissive NSG rules, and minimal logging/retention. No destructive changes are shown, but the resulting environment would be high risk if applied as-is.

## Action Summary
Creates: 19
Updates: 0
Deletes: 0
Replacements: 0

Visible creates include:
- Resource group
- Virtual network, subnet, NSG, NIC, public IP
- AKS cluster
- Linux VM
- Linux Web App
- Log Analytics workspace
- SQL Server and firewall rule
- Storage account and public blob container
- Key Vault and secret
- Service plan
- Random string

## High-Risk Findings
- Key Vault is publicly reachable: `public_network_access_enabled = true`, `purge_protection_enabled = false`, `soft_delete_retention_days = 7`. This weakens secret protection and recovery.
- SQL Server is public: `public_network_access_enabled = true` plus firewall rule `0.0.0.0/0` to `255.255.255.255` allows broad internet access.
- Storage account is publicly exposed: `public_network_access_enabled = true`, `allow_nested_items_to_be_public = true`, `shared_access_key_enabled = true`, `local_user_enabled = true`, `min_tls_version = "TLS1_0"`.
- Storage container is public: `container_access_type = "blob"` for `public-data`, which allows anonymous blob access.
- Web App contains a hardcoded secret in app settings: `DATABASE_PASSWORD = "HardcodedPassword123!"`. This is a major secret leakage risk.
- Web App is widely exposed: `public_network_access_enabled = true`, `https_only = false`, `minimum_tls_version = "1.0"`, FTP/basic auth and Web Deploy basic auth are enabled, and default IP restrictions allow all.
- AKS cluster is internet-exposed: `private_cluster_enabled = false`, `private_cluster_public_fqdn_enabled = false`, `run_command_enabled = true`, `workload_identity_enabled = false`, `local_account_disabled = false`, `sku_tier = "Free"`, and `kubenet` with standard LB increases operational and security risk.
- NSG allows broad inbound access: SSH from `0.0.0.0/0` and RDP from `Internet`, plus outbound `Allow-All-Outbound`.
- Linux VM appears to have a public IP possible and password auth is enabled (`disable_password_authentication = false`), increasing compromise risk.
- Log Analytics workspace uses weak operational controls: `retention_in_days = 30`, internet ingestion/query enabled, and no evidence of diagnostics/alerts being configured.
- Public IP and default outbound access on subnet increase external exposure of workloads.

## Medium-Risk Findings
- AKS uses a single-node `Standard_B2s` system pool and Free tier, which may be fragile and capacity-constrained for prod.
- Service plan is `B1`, which is low capacity for production workloads.
- Storage account uses `LRS` only, so there is limited resilience to regional failure.
- Web App has `always_on = true`, which is good for uptime but increases ongoing cost.
- Storage blob delete retention is only 1 day, which reduces recovery window.
- SQL admin credentials are created from sensitive input, but there is no visible Key Vault integration or managed identity usage.
- Subnet has `private_endpoint_network_policies = "Disabled"` and VNet policies disabled, which can be expected for Private Link but should be validated against intended design.

## Low-Risk Observations
- Tags include `environment = "prod"` on most resources, which helps governance.
- AKS has RBAC enabled.
- Storage account uses HTTPS only.
- Public IP uses Standard SKU with static allocation, which is generally preferable to basic/dynamic public IPs.

## Security and Governance Notes
- Multiple resources are created in a production-tagged deployment without strong guardrails.
- No management locks, policy assignments, Defender settings, or diagnostic settings are visible.
- Secret handling is weak: a hardcoded app password is present and several sensitive platform credentials will be created.
- Key Vault protection is insufficient for prod due to public access and purge protection being disabled.
- Web App, SQL, Storage and AKS all have public exposure or weak network controls.
- Monitoring and audit coverage appears incomplete; only a Log Analytics workspace is created.
- The resource group tag `owner = "unknown"` is a governance gap.

## Recommended Next Steps
- Stop and review before apply.
- Remove all hardcoded secrets; move credentials to Key Vault and use managed identity.
- Disable public access where possible, especially Key Vault, SQL, Storage, and AKS.
- Add proper NSG rules; remove SSH/RDP from Internet.
- Enable Key Vault purge protection and extend soft delete retention.
- Require HTTPS and raise TLS minimums for Web App and Storage.
- Rework Storage public access settings; disable anonymous blob access unless explicitly required.
- Validate AKS production readiness: private cluster, workload identity, stronger SKU, node pool sizing, and network controls.
- Add diagnostic settings, alerts, and backup/retention controls before deployment.
- Confirm whether the plan is complete and whether any missing networking or identity resources are intended.
