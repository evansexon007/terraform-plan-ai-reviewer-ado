# Terraform Plan AI Reviewer for Azure DevOps

A small Azure DevOps-focused project that uses an OpenAI agent to review Terraform plan output and produce a markdown risk report before `terraform apply`.

The goal is to support safer Infrastructure-as-Code delivery by flagging potentially risky changes such as:

- Resource deletion
- Resource replacement
- Network/security changes
- Public exposure changes
- Identity/RBAC changes
- Key Vault changes
- Storage/database/data-loss risks
- Diagnostic/logging removal
- AKS/App Gateway/WAF changes

This project is designed to be **read-only**. It reviews a Terraform plan file and writes a report. It does not apply Terraform, modify Azure, or change infrastructure.

---

## Intended Azure DevOps Flow

```text
Azure DevOps pipeline
  |
  |-- terraform init
  |-- terraform plan -out=tfplan
  |-- terraform show -no-color tfplan > plan.txt
  |-- python agent.py --plan-file plan.txt --output plan-review.md
  |-- publish plan-review.md as a pipeline artifact
```

Optional later enhancement:

```text
--fail-on-high-risk
```

This can fail the pipeline if the AI review identifies high-risk changes.

---

## Repository Structure

```text
terraform-plan-ai-reviewer-ado/
  agent.py
  requirements.txt
  README.md
  .gitignore
  .env.example
  pipelines/
    azure-pipelines-example.yml
  docs/
    ado-setup.md
    example-plan-review.md
    security-model.md
```

---

## Local Setup

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

Set your OpenAI API key:

```powershell
$env:OPENAI_API_KEY = "paste-your-api-key-here"
```

Run a local review:

```powershell
python .\agent.py --plan-file .\plan.txt --output .\plan-review.md
```

Optional:

```powershell
python .\agent.py --plan-file .\plan.txt --output .\plan-review.md --fail-on-high-risk
```

---

## Azure DevOps Usage

Store the OpenAI key as a secret pipeline variable:

```text
OPENAI_API_KEY
```

Then use the pipeline template in:

```text
pipelines/azure-pipelines-example.yml
```

The pipeline:

1. Runs Terraform plan
2. Exports the plan to `plan.txt`
3. Runs the AI review
4. Publishes `plan-review.md` as a build artifact

---

## Output

The generated markdown report includes:

- Overall risk rating
- Terraform action summary
- High-risk findings
- Medium-risk findings
- Low-risk observations
- Security and governance notes
- Recommended approval decision

---

## Safety Model

The reviewer is intentionally read-only.

It does not:

- Run `terraform apply`
- Modify Azure
- Modify Terraform code
- Modify state
- Delete or create resources
- Call Azure APIs

It only:

- Reads `plan.txt`
- Sends the plan content to the model for analysis
- Writes `plan-review.md`

---

## Important Notes

This tool should support, not replace, human review.

For production use, consider:

- Human approval gates
- Pull request policies
- Terraform plan artifacts
- Branch protection
- Azure DevOps environments and approvals
- Clear risk thresholds
- Model output review
- Avoiding secrets in Terraform plan output

Terraform plans can contain sensitive values depending on provider/resource behaviour. Review your own security requirements before sending plan content to any external AI service.
