param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId
)

$ErrorActionPreference = "Stop"

function Read-PlainSecret {
    param([string]$Prompt)

    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Upsert-Secret {
    param(
        [string]$ProjectId,
        [string]$SecretId,
        [string]$Value
    )

    $tmp = New-TemporaryFile
    try {
        [System.IO.File]::WriteAllText($tmp.FullName, $Value, [System.Text.UTF8Encoding]::new($false))

        $existingName = & gcloud secrets list `
            --project $ProjectId `
            --filter "name:projects/*/secrets/$SecretId" `
            --format "value(name)"
        $exists = -not [string]::IsNullOrWhiteSpace($existingName)

        if ($exists) {
            Write-Host "Adding new version: $SecretId"
            & gcloud secrets versions add $SecretId --data-file $tmp.FullName --project $ProjectId
        }
        else {
            Write-Host "Creating secret: $SecretId"
            & gcloud secrets create $SecretId --replication-policy automatic --data-file $tmp.FullName --project $ProjectId
        }
    }
    finally {
        Remove-Item -LiteralPath $tmp.FullName -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI was not found. Install Google Cloud CLI first, then run this script again."
}

Write-Host "Project: $ProjectId"
Write-Host "Enabling Secret Manager API..."
& gcloud services enable secretmanager.googleapis.com --project $ProjectId

$githubToken = Read-PlainSecret "MY_GITHUB_TOKEN"
$gistId = Read-PlainSecret "MY_GIST_ID"
$telegramToken = Read-PlainSecret "MY_TELEGRAM_TOKEN"
$chatId = Read-PlainSecret "MY_CHAT_ID"

Upsert-Secret -ProjectId $ProjectId -SecretId "stock-alarm-github-token" -Value $githubToken
Upsert-Secret -ProjectId $ProjectId -SecretId "stock-alarm-gist-id" -Value $gistId
Upsert-Secret -ProjectId $ProjectId -SecretId "stock-alarm-telegram-token" -Value $telegramToken
Upsert-Secret -ProjectId $ProjectId -SecretId "stock-alarm-chat-id" -Value $chatId

Write-Host "Secret setup complete."
