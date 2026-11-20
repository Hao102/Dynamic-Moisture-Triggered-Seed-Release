# Technical Documentation

Technical documentation for the Dynamic Moisture-Triggered Seed Release System.

## Documentation

- [Handover notes](handover.md) — current implementation status, verified work, remaining work, and hardware-integration boundary.
- [Controller contract](controller-contract.md) — component responsibilities, controller interface, release-generation behaviour, timing compensation, 
current limitations, and verified test baseline.
- [Data-flow diagram](Data-Flow%20Diagram.md) — Level 1 data flow for dataset loading, replay, moisture prediction, depth control, release generation, simulation, and dashboard presentation.
- [Dataset guide](dataset-guide.md) — dashboard dataset format, default dataset and model, model inputs, client raw-data boundary, and future importer requirements.

## Repository entry point

See the repository root [`README.md`](../README.md) for setup instructions, system overview, dashboard workflow, dataset limitations, testing, and remaining engineering work.

## Documentation status

Supporting documentation may describe earlier execution paths or proposed interfaces. Cross-check technical claims against the current source code, tests, and root README until each document has been updated.