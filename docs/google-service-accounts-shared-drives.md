# Google Service Accounts & Shared Drives

This guide covers a production-first setup for SlideFlow Google providers
(`google_slides`, `google_docs`, and `google_sheets`) using a service account
and Shared Drive destinations.

## Why Shared Drive-first

Use Shared Drive output folders as the default operational pattern:

- avoids service-account My Drive quota/ownership edge cases
- keeps ownership with the team workspace, not a single user
- simplifies access control through Shared Drive membership
- reduces failures during post-render sharing and cleanup

## Required APIs

Enable these APIs in your Google Cloud project:

- Google Drive API (`drive.googleapis.com`)
- Google Slides API (`slides.googleapis.com`) for Slides outputs
- Google Docs API (`docs.googleapis.com`) for Docs outputs
- Google Sheets API (`sheets.googleapis.com`) for Sheets outputs

## Service Account Bootstrap (Placeholders Only)

```bash
PROJECT_ID="<gcp-project-id>"
SA_ID="<slideflow-runner-sa-name>"
SA_EMAIL="${SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account
gcloud iam service-accounts create "${SA_ID}" \
  --project "${PROJECT_ID}" \
  --display-name "<display-name>"

# Enable required APIs
gcloud services enable \
  drive.googleapis.com \
  slides.googleapis.com \
  docs.googleapis.com \
  sheets.googleapis.com \
  --project "${PROJECT_ID}"

# Optional: create local key for non-workload-identity flows
KEY_PATH="/tmp/${SA_ID}.json"
gcloud iam service-accounts keys create "${KEY_PATH}" \
  --project "${PROJECT_ID}" \
  --iam-account "${SA_EMAIL}"
```

## Runtime Permissions Model: Cloud IAM vs Drive ACL

Cloud IAM and Drive ACL solve different problems:

- Cloud IAM controls project-level ability to use Google APIs and manage service accounts.
- Drive ACL / Shared Drive membership controls runtime access to templates and output folders.

For SlideFlow runtime success, Drive access is mandatory even when Cloud IAM is correctly configured.

## Shared Drive Membership Recommendations

Grant the runtime service account access in the Shared Drive where templates and outputs live.

Recommended baseline:

- Shared Drive role: `Content manager` (or least privilege that still allows copy/write/share flows)
- Ensure template files are in, or shared to, the same drive scope
- Ensure destination folders for outputs and uploaded chart images are accessible

## Provider Config Patterns (Shared Drive-first)

Google Slides:

```yaml
provider:
  type: google_slides
  config:
    credentials: null
    template_id: "{template_id}"
    presentation_folder_id: "<shared_drive_folder_id>"
    drive_folder_id: "<shared_drive_folder_id>"
    requests_per_second: 1.0
    # transfer_ownership_to: omit for Shared Drive outputs
    # transfer_ownership_strict: omit for Shared Drive outputs
```

Google Docs:

```yaml
provider:
  type: google_docs
  config:
    credentials: null
    template_id: "{template_id}"
    document_folder_id: "<shared_drive_folder_id>"
    drive_folder_id: "<shared_drive_folder_id>"
    requests_per_second: 1.0
    # transfer_ownership_to: omit for Shared Drive outputs
    # transfer_ownership_strict: omit for Shared Drive outputs
```

Google Sheets:

```yaml
provider:
  type: google_sheets
  config:
    credentials: null
    drive_folder_id: "<shared_drive_folder_id>"
    requests_per_second: 1.0
    # transfer_ownership_to: omit for Shared Drive outputs
    # transfer_ownership_strict: omit for Shared Drive outputs
```

Set credentials through:

- `provider.config.credentials` (file path or raw JSON), or
- `GOOGLE_SLIDEFLOW_CREDENTIALS`, or
- provider-specific env vars where supported.

## Verification Steps

### 1) Confirm APIs are enabled

```bash
gcloud services list --enabled --project "<gcp-project-id>" \
  | rg "drive.googleapis.com|slides.googleapis.com|docs.googleapis.com|sheets.googleapis.com"
```

### 2) Confirm Drive visibility for runtime identity

```bash
python - <<'PY'
from google.oauth2 import service_account
from googleapiclient.discovery import build

sa_file = "<path-to-service-account-json>"
shared_drive_id = "<shared-drive-id>"

creds = service_account.Credentials.from_service_account_file(
    sa_file,
    scopes=["https://www.googleapis.com/auth/drive"],
)
drive = build("drive", "v3", credentials=creds)

about = drive.about().get(
    fields="user(emailAddress),storageQuota(limit,usage),canCreateDrives"
).execute()
print("about:", about)

drives = drive.drives().list(pageSize=100, fields="drives(id,name)").execute()
visible = any(d["id"] == shared_drive_id for d in drives.get("drives", []))
print("shared_drive_visible:", visible)
PY
```

### 3) Confirm SlideFlow preflight passes

```bash
slideflow doctor --config-file config.yml --strict
slideflow validate config.yml --provider-contract-check
```

## Troubleshooting Map

| Error / Symptom | Likely Cause | Remediation |
|---|---|---|
| `storageQuotaExceeded` | writing into service-account My Drive | write outputs to Shared Drive folder IDs |
| `consentRequiredForOwnershipTransfer` | domain policy blocks transfer in My Drive | use Shared Drive outputs or disable transfer settings |
| `Ownership transfer is not supported for files in Shared Drives` | transfer fields enabled for Shared Drive artifacts | remove `transfer_ownership_to` and `transfer_ownership_strict` |
| `File not found` for template/folder | service account lacks Drive ACL or Shared Drive membership | add service-account membership/share on template and output folders |
| `403` during copy/write/share | insufficient Drive permissions for target location | raise Shared Drive role or folder-level permissions for runtime service account |

For broader diagnostics, also see [Troubleshooting](troubleshooting.md).

## Security and Operations Notes

- Prefer workload identity / secret manager over long-lived key files where possible.
- If key files are required, rotate regularly and avoid committing key material.
- Run `slideflow doctor` in CI before `validate`/`build` to fail fast.

## Related Docs

- [Getting Started](getting-started.md)
- [Google Slides Provider](providers/google-slides.md)
- [Google Docs Provider](providers/google-docs.md)
- [Google Sheets Provider](providers/google-sheets.md)
- [Deployments](deployments.md)
- [Security](security.md)
