-- Synapse serverless SQL over the serving layer in ADLS Gen2, no copy. The
-- workspace's managed identity needs Storage Blob Data Reader on the account.
-- Replace <account>.
CREATE DATABASE carelake;
GO
USE carelake;
GO
CREATE EXTERNAL DATA SOURCE serving WITH (LOCATION = 'https://<account>.dfs.core.windows.net/serving');
GO
CREATE OR ALTER VIEW patient_dim AS SELECT * FROM OPENROWSET(BULK 'patient_dim.parquet', DATA_SOURCE = 'serving', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW encounter_fact AS SELECT * FROM OPENROWSET(BULK 'encounter_fact.parquet', DATA_SOURCE = 'serving', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW chronic_pairs AS SELECT * FROM OPENROWSET(BULK 'chronic_pairs.parquet', DATA_SOURCE = 'serving', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW diabetes_care_gaps AS SELECT * FROM OPENROWSET(BULK 'diabetes_care_gaps.parquet', DATA_SOURCE = 'serving', FORMAT = 'PARQUET') AS r;
GO
SELECT TOP 10 bucket_a, bucket_b, both_n, lift FROM chronic_pairs ORDER BY both_n DESC;
