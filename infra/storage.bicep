// The landing zone: one ADLS Gen2 account, a filesystem per layer, a monthly
// budget that emails at $1. Resource-group scope.
//
//   az deployment group create -g rg-carelake -f infra/storage.bicep \
//      -p accountName=<3-24 lowercase alphanumerics, globally unique> alertTo=<email>

@minLength(3)
@maxLength(24)
param accountName string
param alertTo string
param location string = resourceGroup().location
param monthlyBudgetUsd int = 1
param thisMonth string = utcNow('yyyy-MM')   // utcNow is only legal as a parameter default

var layers = ['raw', 'curated', 'serving', 'feeds']

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: accountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
  tags: { project: 'carelake', data: 'synthetic' }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
  properties: { deleteRetentionPolicy: { enabled: true, days: 7 } }
}

resource filesystems 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for layer in layers: {
  parent: blobs
  name: layer
  properties: { publicAccess: 'None' }
}]

// raw is identified data: cool it after 60 days, never delete automatically
resource tiering 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'cool-raw'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['raw/'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 60 } } }
          }
        }
      ]
    }
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'carelake-monthly'
  properties: {
    category: 'Cost'
    amount: monthlyBudgetUsd
    timeGrain: 'Monthly'
    timePeriod: { startDate: '${thisMonth}-01' }
    notifications: {
      spent80: { enabled: true, operator: 'GreaterThan', threshold: 80, thresholdType: 'Actual', contactEmails: [alertTo] }
      forecast100: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 100, thresholdType: 'Forecasted', contactEmails: [alertTo] }
    }
  }
}

output account string = account.name
output dfs string = account.properties.primaryEndpoints.dfs
