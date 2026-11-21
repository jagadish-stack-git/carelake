# One-time: create the landing zone and print what the pipeline needs.
#   .\infra\up.ps1 -AccountName carelake<digits> -AlertTo you@example.com
# Afterwards, as repository secrets:
#   gh secret set CARELAKE_ADLS_ACCOUNT --body <account>
#   az storage account keys list -g rg-carelake -n <account> --query "[0].value" -o tsv | gh secret set CARELAKE_ADLS_KEY
param(
    [Parameter(Mandatory = $true)][string]$AccountName,
    [Parameter(Mandatory = $true)][string]$AlertTo,
    [string]$Group = "rg-carelake",
    [string]$Location = "eastus2"
)
$ErrorActionPreference = "Stop"
az account show --output none
az group create --name $Group --location $Location --output none
az deployment group create --resource-group $Group --template-file (Join-Path $PSScriptRoot "storage.bicep") `
    --parameters accountName=$AccountName alertTo=$AlertTo --query "properties.outputs" --output json
Write-Host ""
Write-Host "CARELAKE_ADLS_ACCOUNT=$AccountName"
Write-Host "key: az storage account keys list -g $Group -n $AccountName --query '[0].value' -o tsv   (store it as a secret, never in the repo)"
