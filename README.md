# Terraform Plan AI Reviewer for Azure DevOps

AI-assisted Terraform plan risk reviewer for **Azure DevOps Terraform pipelines**.

This project reviews Terraform plan output and generates a markdown risk report before `terraform apply`. It is designed to support human approval, not replace it.

The reviewer is read-only:

- It reads a Terraform plan text file.
- It sends the plan content to an OpenAI model for review.
- It writes a markdown report.
- It does not run `terraform apply`.
- It does not modify Azure.
- It does not modify Terraform state or code.

---

## What problem does this solve?

Terraform plans can be long and difficult to review quickly, especially in Azure platform environments where a single plan may include networking, RBAC, Key Vault, storage, diagnostics, AKS, App Gateway, WAF or private endpoint changes.

This tool produces a human-readable review that highlights:

- Resource deletion
- Resource replacement
- Force replacement
- Public exposure changes
- NSG/firewall/route/DNS/private endpoint changes
- RBAC and managed identity changes
- Key Vault changes
- Storage account and database risks
- Backup, retention and data protection concerns
- Diagnostic/logging/monitoring removal
- AKS, App Gateway and WAF changes

The output is intended to be published as an **Azure DevOps pipeline artifact**.

---

## Intended Azure DevOps flow

```text
Azure DevOps pipeline
  |
  |-- terraform init
  |-- terraform validate
  |-- terraform plan -out=tfplan
  |-- terraform show -no-color tfplan > plan.txt
  |-- AI review plan.txt
  |-- publish plan-review.md as a pipeline artifact
  |-- human approval
  |-- terraform apply
```

Recommended starting mode:

```text
Advisory only
```

Optional later mode:

```text
--fail-on-high-risk
```

This can fail the pipeline if the review reports High or Critical risk.

---

## Repository structure

```text
terraform-plan-ai-reviewer-ado/
  .gitignore
  .env.example
  README.md
  agent.py
  requirements.txt
```

Optional supporting folders can be added later:

```text
pipelines/
docs/
examples/
```

---

## Local setup

Create a Python virtual environment:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Set your OpenAI API key locally:

```powershell
$env:OPENAI_API_KEY = "paste-your-api-key-here"
```

Run a local review:

```powershell
python .\agent.py --plan-file .\plan.txt --output .\plan-review.md
```

Optional high-risk blocking mode:

```powershell
python .\agent.py --plan-file .\plan.txt --output .\plan-review.md --fail-on-high-risk
```

---

## Azure DevOps configuration

### 1. Store the OpenAI API key securely

Create an Azure DevOps variable group.

Recommended variable group name:

```text
ai-secrets
```

Recommended variable name:

```text
openAiApiKey
```

Mark the variable as secret.

In Azure DevOps:

```text
Pipelines
  -> Library
  -> Variable groups
  -> New variable group
```

Create:

```text
Variable group name: ai-secrets
Variable name: openAiApiKey
Value: your OpenAI API key
Secret: enabled
```

Then authorise the pipeline to use the variable group:

```text
Library
  -> ai-secrets
  -> Pipeline permissions
  -> Authorise the pipeline
```

Do not hard-code the API key in YAML.

---

## If using this from a pipeline template

If your Terraform pipeline uses a reusable template, the variable group should normally be referenced in the **main pipeline YAML that calls the template**, not only inside the template.

Example main pipeline:

```yaml
trigger: none

variables:
  - group: ai-secrets

stages:
  - template: templates/terraform-template.yml
    parameters:
      serviceConnectionShared: "sc-shared"
      serviceConnection: "sc-workload"
      resourceGroup: "rg-tfstate-uks-001"
      storageAccount: "sttfstateuks001"
      containerName: "tfstate"
      backendKey: "platform/terraform.tfstate"
      workingDirectory: "$(System.DefaultWorkingDirectory)/terraform"
      environment: "lab"
```

The important part is:

```yaml
variables:
  - group: ai-secrets
```

Then the template can reference the secret variable using:

```yaml
env:
  OPENAI_API_KEY: $(openAiApiKey)
```

---

## Terraform plan stage example

This is the key pattern inside the Terraform plan stage.

It:

1. Runs Terraform plan.
2. Saves the binary plan as `tfplan`.
3. Converts it to readable text as `plan.txt`.
4. Publishes `plan.txt`.
5. Clones this AI reviewer from GitHub.
6. Runs the AI review.
7. Publishes `plan-review.md`.

```yaml
- stage: terraform_plan
  displayName: "Terraform Plan"
  dependsOn: terraform_validate
  jobs:
    - job: plan
      displayName: "Run Terraform Plan"
      steps:
        - checkout: self

        - task: TerraformInstaller@1
          displayName: "Install Terraform"
          inputs:
            terraformVersion: "latest"

        - task: TerraformTaskV4@4
          displayName: "Terraform Init"
          inputs:
            provider: "azurerm"
            command: "init"
            workingDirectory: ${{ parameters.workingDirectory }}
            environmentServiceNameAzureRM: ${{ parameters.serviceConnection }}
            backendServiceArm: ${{ parameters.serviceConnectionShared }}
            backendAzureRmResourceGroupName: ${{ parameters.resourceGroup }}
            backendAzureRmStorageAccountName: ${{ parameters.storageAccount }}
            backendAzureRmContainerName: ${{ parameters.containerName }}
            backendAzureRmKey: ${{ parameters.backendKey }}

        - task: TerraformTaskV4@4
          displayName: "Terraform Plan"
          inputs:
            provider: "azurerm"
            command: "plan"
            workingDirectory: ${{ parameters.workingDirectory }}
            environmentServiceNameAzureRM: ${{ parameters.serviceConnection }}
            commandOptions: '-out="$(Build.ArtifactStagingDirectory)/tfplan"'

        - pwsh: |
            terraform show -no-color "$(Build.ArtifactStagingDirectory)/tfplan" | Out-File -FilePath "$(Build.ArtifactStagingDirectory)/plan.txt" -Encoding utf8
          displayName: "Export Terraform Plan to Text"
          workingDirectory: ${{ parameters.workingDirectory }}

        - publish: "$(Build.ArtifactStagingDirectory)/plan.txt"
          artifact: "terraform-plan-text"
          displayName: "Publish Terraform Plan Text"

        - task: UsePythonVersion@0
          displayName: "Use Python 3.x"
          inputs:
            versionSpec: "3.x"

        - pwsh: |
            git clone https://github.com/evansexon007/terraform-plan-ai-reviewer-ado.git ai-reviewer

            python -m pip install --upgrade pip
            pip install -r ai-reviewer/requirements.txt

            if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
              Write-Error "OPENAI_API_KEY is empty or not mapped."
              exit 1
            }

            if ($env:OPENAI_API_KEY -like '$(*') {
              Write-Error "OPENAI_API_KEY was not expanded by Azure DevOps."
              exit 1
            }

            Write-Host "OPENAI_API_KEY is mapped."

            python ai-reviewer/agent.py `
              --plan-file "$(Build.ArtifactStagingDirectory)/plan.txt" `
              --output "$(Build.ArtifactStagingDirectory)/plan-review.md"
          displayName: "AI Review Terraform Plan"
          env:
            OPENAI_API_KEY: $(openAiApiKey)

        - publish: "$(Build.ArtifactStagingDirectory)/plan-review.md"
          artifact: "terraform-plan-ai-review"
          displayName: "Publish AI Plan Review"
```

---

## Full template integration notes

If your existing Terraform template has stages like this:

```text
terraform_init
terraform_validate
terraform_plan
terraform_apply
```

Add the AI review only to the `terraform_plan` stage after the plan has been exported to `plan.txt`.

Recommended order:

```text
Terraform Init
Terraform Plan
Export Terraform Plan to Text
Publish Terraform Plan Text
Use Python 3.x
AI Review Terraform Plan
Publish AI Plan Review
```

Do not enable `--fail-on-high-risk` at first.

Start with advisory review only. Let the pipeline continue and publish the report.

---

## Pipeline artifacts

After a successful run, Azure DevOps should show two artifacts:

```text
terraform-plan-text
  plan.txt

terraform-plan-ai-review
  plan-review.md
```

The reviewer or approver can open `plan-review.md` before approving apply.

---

## Example output

```markdown
# Terraform Plan AI Review

## Overall Risk

High

## Approval Recommendation

Do not apply until reviewed

## Summary

The plan contains potentially high-impact changes, including public exposure changes, network security changes and possible data-loss risks. Manual review is required before apply.

## Action Summary

- Creates: 4 resources
- Updates: 3 resources
- Replacements: 1 resource
- Deletes: 1 resource

## High-Risk Findings

### 1. Public network exposure detected

A resource appears to enable public access or broaden an existing network rule.

Risk:

This may increase external exposure and weaken the approved security posture.

Recommended action:

Validate this change against the approved network and security design before apply.

### 2. Destroy action detected

A resource is marked for deletion.

Risk:

Deletion may cause data loss, service disruption or loss of configuration.

Recommended action:

Confirm the deletion is expected, approved and recoverable before apply.

## Medium-Risk Findings

### 1. Resource replacement detected

Replacement can cause downtime depending on the resource type and dependencies.

## Low-Risk Observations

Tag changes or metadata-only updates may be present.

## Security and Governance Notes

Review public access, RBAC, Key Vault, diagnostics, monitoring and backup implications.

## Recommended Next Steps

1. Review high-risk findings with the platform owner.
2. Confirm whether destructive changes are expected.
3. Validate public exposure changes.
4. Proceed only after manual approval.
```

---

## Optional blocking mode

Once you trust the output, you can add:

```powershell
--fail-on-high-risk
```

Example:

```yaml
python ai-reviewer/agent.py `
  --plan-file "$(Build.ArtifactStagingDirectory)/plan.txt" `
  --output "$(Build.ArtifactStagingDirectory)/plan-review.md" `
  --fail-on-high-risk
```

Recommended approach:

```text
Phase 1: Advisory only
Phase 2: Fail on Critical only
Phase 3: Fail on High or Critical
```

---

## Troubleshooting

### Error: Incorrect API key provided: $(openAiApiKey)

This means Azure DevOps passed the literal string `$(openAiApiKey)` instead of substituting the secret.

Fix:

1. Confirm the variable group is referenced:

```yaml
variables:
  - group: ai-secrets
```

2. Confirm the variable group is authorised for the pipeline.
3. Confirm the variable name is exactly:

```text
openAiApiKey
```

4. Confirm the AI step maps the environment variable:

```yaml
env:
  OPENAI_API_KEY: $(openAiApiKey)
```

### Error: OPENAI_API_KEY is empty or not mapped

The variable group is missing, not authorised, or the variable name is wrong.

### Error: plan.txt not found

Confirm the plan export step ran successfully:

```powershell
terraform show -no-color "$(Build.ArtifactStagingDirectory)/tfplan" | Out-File -FilePath "$(Build.ArtifactStagingDirectory)/plan.txt" -Encoding utf8
```

### Error: git clone failed

Confirm the GitHub repository is public or configure an Azure DevOps service connection/personal access token for private repo access.

### Error: pip install failed

Confirm the agent has internet access to install Python packages.

---

## Security considerations

Terraform plan output can contain sensitive data depending on the provider, resource type and configuration.

Before using this in production:

- Confirm whether plan output can be sent to an external AI API.
- Review data classification requirements.
- Avoid including secrets in Terraform code.
- Use Azure DevOps secret variables.
- Consider redaction.
- Keep the report as advisory unless governance approves blocking behaviour.
- Use human approval before `terraform apply`.

This tool should complement, not replace:

- Terraform validate
- Checkov, Trivy, TFLint or similar IaC scanners
- OPA/Sentinel/policy-as-code
- Pull request review
- Azure DevOps environment approvals
- Change management

---

## Important note

This is a demonstration of AI-assisted platform engineering.

It should not be treated as an enterprise control without further review, testing, policy alignment, audit logging and approval workflow design.
