# Legacy compiler binaries — quarantined

The two executables in this directory predate the provenance audit. They are
byte-identical (`SHA-256 539eb689d2e0d3751aeed273385865278bef6696c46bc0cab116b40c3b2fe820`),
but their original source revision and reproducible build recipe are unknown.

GhostScripter does **not** package or automatically execute them. Script
compilation uses the pinned `nwscript.nss` definitions with PyKotor's native
compiler. A separately installed `nwnnsscomp` on `PATH` remains an explicit
fallback. The legacy files may be removed once repository history confirms
whether they need to be retained for archival reasons.
