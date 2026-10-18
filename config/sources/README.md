# Source inventory input

The user supplied `unibe_sous_domaines_publics_etendus.xlsx` on 18 October 2026. The original workbook is retained byte-for-byte; SHA-256: `9a98f3631c01bb8a16c222b7958363492277a97c038fea565843ac5619e65b8c`.

`unibe_inventory.csv` is a UTF-8 CSV extraction of worksheet `Sous-domaines UniBE`: the original three French column names, values and row order are preserved. It contains **42 data rows**: 41 UniBE-domain URLs and one DCB URL. The original workbook's `Notes` sheet is preserved in the XLSX; it records a research date of 4 September 2026 and describes a best-effort public list.

The Notes sheet says **71** subdomains, which conflicts with the 42 actual rows. No extra domains were invented, removed or inferred. Clarify whether a fuller inventory exists before claiming exhaustive coverage.

This raw inventory remains source input, not a crawler-ready YAML registry. The separate `unibe_inventory_audit.csv` and sanitised `unibe_inventory_audit.json` now record T02 R1 checks for every row: 41 included inputs and one excluded placeholder, with tiers, reasons, robots/layout signals and timestamps. Full methodology and limitations are in [docs/sources.md](../../docs/sources.md). T06 generates per-domain YAML and crawl profiles from the reviewed inventory joined to that audit. Preserve the distinction between a supplied URL and its later verified redirect/effective host; do not silently normalise source values here.

Verification: original/copy SHA-256 equality; exactly 42 unique inventory keys; valid HTTP(S) URL syntax; 41 UniBE + one DCB URL; exact CSV round-trip equality for all cells. These import checks are distinct from the later 42-row network audit. Neither the import nor the audit performs application ingestion or verifies application behavior.
