# sisyphus-hermes architecture

`sisyphus-hermes` is a Hermes-native plugin project described by the Seed at
`.ouroboros/seeds/sisyphus-hermes.seed.yaml`.

The architecture is intentionally built around Hermes primitives rather than
OpenCode log scraping:

- durable run, plan, task, review gate, evidence, and audit state;
- Kanban as the preferred task source of truth with a local SQLite fallback;
- explicit role contracts for Metis, Momus, Sisyphus, Hephaestus, and Hermes-Sheriff;
- Telegram-friendly reporting plus structured JSON for tests and automation;
- optional executor adapters that are peers, never the source of truth.

This bootstrap document is expanded in later implementation slices.
