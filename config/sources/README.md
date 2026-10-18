# Source inventory input

The user supplied `unibe_sous_domaines_publics_etendus.xlsx` on 18 October 2026. The original workbook is retained byte-for-byte; SHA-256: `9a98f3631c01bb8a16c222b7958363492277a97c038fea565843ac5619e65b8c`.

`unibe_inventory.csv` is a UTF-8 CSV extraction of worksheet `Sous-domaines UniBE`: the original three French column names, values and row order are preserved. It contains **42 data rows**: 41 UniBE-domain URLs and one DCB URL. The original workbook's `Notes` sheet is preserved in the XLSX; it records a research date of 4 September 2026 and describes a best-effort public list.

The Notes sheet says **71** subdomains, which conflicts with the 42 actual rows. No extra domains were invented, removed or inferred. Clarify whether a fuller inventory exists before claiming exhaustive coverage.

This is source input, not a crawler-ready YAML registry or an audit of reachability/robots/layout. T02 R1 still needs per-row checks, focus/outside-focus classification and included/excluded reasons; T06 generates the per-domain YAML and crawl profiles from the reviewed inventory. Preserve the distinction between a supplied URL and its later verified redirect/effective host; do not silently normalise source values here.

Verification: original/copy SHA-256 equality; exactly 42 unique inventory keys; valid HTTP(S) URL syntax; 41 UniBE + one DCB URL; exact CSV round-trip equality for all cells. No network checks, ingestion or application behavior were run as part of this file import.
