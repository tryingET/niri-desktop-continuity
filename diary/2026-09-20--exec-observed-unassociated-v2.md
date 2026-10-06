# Explicit five-record partial accounting

Implemented the separate offline v2 family on the existing CLI, with strict semantic closure,
original witness matching, current process/partition proof and one-flock publication. V1 remains
absolute-nine-only. Historical verification uses recorded proofs, never probes old live processes.

The identity contract distinguishes persisted historical pins from the latest generated artifacts'
first-observed operation-interval pins. Later plans bind dependencies as observed at preparation,
not as authenticated original-creation inodes. Newest terminal trust remains owner-controlled
append-only state plus trusted app/operator workflow, not a signed-log guarantee. Missing artifacts
are never rebuilt; semantically equivalent unpinned replacement before observation may accept.

Implementation choices: the existing `.pending` stage precedes consumption to fence pre-receipt
failures and alternative-approval attempts. The final complete prospective check counts actual
existing bytes and exact future bytes, then consumption adds no new dependencies. The staged ending
becomes canonical by one explicit same-file rename across fresh passes. Proposal ancestry is
recorded separately from the fresh ancestry veto at each later CLI invocation. No new Store kind,
marker type, envelope schema, Store implementation change or runtime dependency was needed.

Handwritten tests cover offset zero and v1 → v2 → ordinary terminal → v2 → v2 across Stores,
actual admission consumers, historical-pin versus interval drift, exact prospective boundaries,
closed schemas/partitions/witnesses, staging faults and legacy-suffix routing. Cooperative ELF tests
exercise default pidfd/image/argv/cwd proofs. Installed-wheel checks use fabricated IPC/witnesses,
not native qualification. Retained evidence distinguishes RED, GREEN and failed intermediate runs.
Independent code review, parent full CI and any live/native/deployment approval remain separate.
