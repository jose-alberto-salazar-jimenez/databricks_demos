# Evidence - Phase 1: Foundation

Run date: 2026-11-11. Workspace host and user identifiers omitted.

## Unity Catalog objects

Schemas in `weather_forecast_warnings_comms` (query on `information_schema.schemata`):

```
bronze | default | gold | information_schema | silver
```

## Bundle validation 

`databricks bundle validate --strict --target dev`: OK. Resolved resource:

```
volumes.landing
  catalog_name: weather_forecast_warnings_comms
  schema_name:  bronze
  name:         dev_<user>_landing
  volume_type:  MANAGED
```

`databricks bundle validate --strict --target prod`:

```
Name: weather_forecast_warning_comms
Target: prod
Validation OK!
```

## Dev deployment

`databricks bundle deploy --target dev`:

```
Created volumes.landing
Resources: 1 created, 0 changed, 0 deleted, 0 unchanged
```

Verification (`information_schema.volumes`):

```
volume_schema | volume_name        | volume_type
bronze        | dev_<user>_landing | MANAGED
```

## Decision recorded

Dev and prod share one workspace and catalog. Development mode prefixes jobs and pipelines
but not volumes, so the dev target overrides the volume name per user to avoid a collision
with the prod `landing` volume.
