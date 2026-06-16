# Terraform Plan AI Reviewer for Azure DevOps

AI-assisted Terraform plan risk reviewer for **Azure DevOps Terraform pipelines**.

This project reviews the **full Terraform plan output** and generates a human-readable markdown risk report before `terraform apply`.

It is designed to support a human reviewer or approver. It is **not** intended to replace Terraform validation, IaC scanning, policy-as-code, peer review, or change approval.

---

## Why I built this

In real Terraform delivery workflows, plan reviews can be difficult to do properly under time pressure.

A Terraform plan can easily run to hundreds or thousands of lines, especially in Azure platform environments with networking, identity, monitoring, diagnostics, private endpoints, storage, AKS, App Gateway, WAF and RBAC changes.

When someone is asked to review a long plan quickly, it is easy to miss important details such as:

* A resource replacement hidden in the middle of the output
* A public access setting changing from `false` to `true`
* An NSG rule being opened to `0.0.0.0/0`
* A diagnostic setting being removed
* A Key Vault, RBAC or managed identity change
* A storage account, disk or database deletion
* A route table, private endpoint or DNS change with connectivity impact
* A SKU, scale or capacity change with cost or performance impact

I built this project to act as a second pair of eyes during the review process.

The goal is not to let AI approve infrastructure changes automatically. The goal is to produce a quick, readable risk summary that helps the human reviewer focus on the parts of the plan that matter most.

It is especially useful when:

* The plan output is long
* The reviewer is under time pressure
* Multiple teams are submitting changes
* The change spans several Azure services
* The risk is not obvious from the Terraform output alone

The reviewer remains human. The AI report is there to support faster, safer and more consistent review.

---

## What it does

The tool reads a Terraform plan text file, reviews the visible resource changes, and produces a markdown report such as:

```text
plan-review.md
```

The report includes:

* Overall risk rating
* Approval recommendation
* Summary of the planned change
* Action summary
* High-risk findings
* Medium-risk findings
* Low-risk observations
* Security and governance notes
* Recommended next steps

The output can be published in Azure DevOps as:

* A downloadable pipeline artifact
* A rendered pipeline summary

## Example output

A full example review report is available here:

[View an example AI-generated Terraform plan review](./terraform-plan-ai-review-example.MD)

---

## Important scope clarification

This tool reviews the **entire Terraform plan**, not only a fixed list of Azure resource types.

The risk categories below are areas the reviewer gives **additional attention** to because they are commonly high-impact in Azure platform environments.

It should still assess all visible Terraform changes in the plan, including resource groups, tags, policies, monitoring, compute, networking, storage, identity, databases, Kubernetes, application services, and other Azure resources.

---

## High-impact risk areas

The reviewer gives additional focus to:

* Resource deletion
* Resource replacement
* Force replacement
* Public exposure changes
* NSG, firewall, route, DNS, private endpoint and private DNS changes
* RBAC and managed identity changes
* Key Vault changes
* Storage account and database risks
* Backup, retention and data protection changes
* Diagnostic, logging and monitoring removal
* AKS, App Gateway and WAF changes
* SKU, scale, capacity and cost-impacting changes
* Policy, lock, tag and governance changes

---

## Safety model

The reviewer is read-only.

It does:

* Read `plan.txt`
* Send the plan content to the OpenAI model for analysis
* Write `plan-review.md`

It does **not**:

* Run `terraform apply`
* Modify Azure
* Modify Terraform code
* Modify Terraform state
* Create, update or delete infrastructure
* Call Azure APIs directly

Recommended starting mode:

```text
Advisory only
```

Optional later mode:

```text
--fail-on-high-risk
```

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
  |-- publish plan-review.md as pipeline summary
  |-- publish plan-review.md as pipeline artifact
  |-- human approval
  |-- terraform apply
```

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

## Azure DevOps variable group

Create a variable group for the OpenAI API key.

Recommended variable group name:

```text
openAiApiKey
```

Recommended secret variable name:

```text
openAiApiKey
```

In Azure DevOps:

```text
Pipelines
  -> Library
  -> Variable groups
  -> New variable group
```

Create the variable:

```text
Variable group name: openAiApiKey
Variable name: openAiApiKey
Value: your OpenAI API key
Secret: enabled
```

Then authorise the pipeline to use the variable group:

```text
Library
  -> openAiApiKey
  -> Pipeline permissions
  -> Authorise the pipeline
```

Do not hard-code the API key in YAML.

---

## If using a pipeline template

If your Terraform pipeline uses a reusable template, reference the variable group in the YAML that is actually being run.

Example:

```yaml
variables:
  - group: openAiApiKey
```

The AI review step then maps the secret into the Python process as an environment variable:

```yaml
env:
  OPENAI_API_KEY: $(openAiApiKey)
```

If Azure DevOps passes the literal value `$(openAiApiKey)` to the script, the variable group is not linked, not authorised, or the variable name does not match.

---

## Terraform plan stage example

This is the key pattern inside the `terraform_plan` stage.

It:

1. Runs Terraform plan.
2. Saves the binary plan as `tfplan`.
3. Converts it to readable text as `plan.txt`.
4. Publishes `plan.txt`.
5. Clones this AI reviewer from GitHub.
6. Runs the AI review.
7. Uploads the markdown as a pipeline summary.
8. Publishes `plan-review.md` as an artifact.

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

        - pwsh: |
            Write-Host "Uploading AI Terraform Plan Review as pipeline summary..."
            Write-Host "##vso[task.uploadsummary]$(Build.ArtifactStagingDirectory)/plan-review.md"
          displayName: "Upload AI Plan Review Summary"

        - publish: "$(Build.ArtifactStagingDirectory)/plan-review.md"
          artifact: "terraform-plan-ai-review"
          displayName: "Publish AI Plan Review"
```

---

## Pipeline artifacts and summary

After a successful run, Azure DevOps should show:

```text
terraform-plan-text
  plan.txt

terraform-plan-ai-review
  plan-review.md
```

The review is also uploaded as a pipeline summary, so it can be read directly in the pipeline run without downloading the markdown file.

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

Once you trust the output, add:

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

Recommended rollout:

```text
Phase 1: Advisory only
Phase 2: Fail on Critical only
Phase 3: Fail on High or Critical
```

---

## Troubleshooting

### Incorrect API key provided: $(openAiApiKey)

Azure DevOps passed the literal string `$(openAiApiKey)` instead of substituting the secret.

Fix:

1. Confirm the variable group is referenced:

```yaml
variables:
  - group: openAiApiKey
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

### OPENAI_API_KEY is empty or not mapped

The variable group is missing, not authorised, or the variable name is wrong.

### plan.txt not found

Confirm the plan export step ran successfully:

```powershell
terraform show -no-color "$(Build.ArtifactStagingDirectory)/tfplan" | Out-File -FilePath "$(Build.ArtifactStagingDirectory)/plan.txt" -Encoding utf8
```

### git clone failed

Confirm this GitHub repository is public or configure authentication for private repo access.

### pip install failed

Confirm the Azure DevOps agent has internet access to install Python packages.

---

## Security considerations

Terraform plan output can contain sensitive data depending on provider behaviour and resource configuration.

Before using this in production:

* Confirm whether Terraform plan content can be sent to an external AI API.
* Review data classification requirements.
* Avoid secrets in Terraform code.
* Use Azure DevOps secret variables.
* Consider additional redaction.
* Keep the report advisory unless governance approves blocking behaviour.
* Use human approval before `terraform apply`.

This tool should complement, not replace:

* Terraform validate
* Checkov, Trivy, TFLint or similar IaC scanners
* OPA, Sentinel or policy-as-code
* Pull request review
* Azure DevOps environment approvals
* Change management

---

## Important note

This is a demonstration of AI-assisted platform engineering.

It should not be treated as an enterprise control without further review, testing, policy alignment, audit logging and approval workflow design.
