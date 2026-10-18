# Demo video script (2 minutes)

Refs #22. Follows [ARCHITECTURE.md](ARCHITECTURE.md) section 8: company → German query → English evidence → honest answer → metrics. Record on the live Space (https://kaktamsdengami-bern-match.hf.space) on the final UI, logged out, at 1280×720 or larger. The recording is also the backup video.

**Every query below was run on the live Space on 2026-10-18 (revision `d3da47b`) and gave the result described.** Run each one again right before recording; if a result changed, change the line, never the claim.

## The company (fictional)

*GlucoWear AG*, a Bern start-up building a smartwatch, wants a research partner for measuring blood sugar without a needle. Fictional company, real public pages.

## Timeline

| Time | Screen | Voice-over (about 280 words in total) |
| --- | --- | --- |
| 0:00–0:12 | Start page | "Bern's research is spread over dozens of websites, and companies don't speak researchers' language. Bern Match lets the economic development agency find the right partner in seconds." |
| 0:12–0:30 | Type **`Messung des Blutzuckers ohne Nadel für eine Smartwatch`**, press Search | "Our analyst describes the company's need in plain German, the way the founder said it. Results come straight from the search index, before any AI runs." Point at the pill: **"10 results in ~150 ms"** and **"Query language detected: DE"**. |
| 0:30–0:55 | Card 1 **SPN-005 – Pilotstudie zur schmerzfreien Blutzuckermessung** (DCB, project). Then card 2 **Forschung – Diabetes Center Berne**, whose quote is English: *"A prospective pilot study demonstrating non-invasive calibration-free glucose measurement…"* | "The top match is a Diabetes Center Berne pilot study on painless glucose measurement. The German question found English evidence too. Every card quotes the exact sentence from the source page, with its link and dates, and only shows facts that a source sentence supports. Nothing is invented." Click **Open source** once. |
| 0:55–1:05 | Click **Select** on card 1, open **Shortlist** | "The analyst keeps the good ones in a shortlist." |
| 1:05–1:25 | New search: **`recipe for chocolate cake`** | "And when the corpus has no real answer, it says so." Point at the **Low confidence** banner and its suggestions: "It warns that these are weak matches and suggests how to narrow the request, instead of pretending." |
| 1:25–1:45 | Back to the glucose query with **Interpret my request (Apertus)** ticked *(only if verified, see below)* | "Optionally, Apertus, the Swiss open model, turns the request into editable needs and explains each card, always labelled as AI-generated and checked against the source sentences." |
| 1:45–2:00 | Static slide or the README table | "2,811 public pages, 148,404 sentences, 4,374 entities. Search answers in about a quarter of a second. Open models, Swiss inference, removal on request." Show only numbers that are in the README or on #14 at recording time. |

## Before recording

1. **Apertus step (1:25):** tick *Interpret my request* on the glucose query and wait for the "Apertus is analysing…" line and an assessment on a card. If nothing arrives within ~20 s, or the gateway is down, **cut the step** and extend the shortlist step. It has not been checked on the live Space yet.
2. Re-run all three queries and note the latency pill. Say "about" and the observed number, not a target.
3. Clear the shortlist and reload the page so it starts clean.
4. Use the browser at 100 % zoom, light mode, no extensions visible, no bookmarks bar.

## Known limits to keep in mind (do not hide them, do not feature them)

- **Abstention:** a fully off-topic query (`recipe for chocolate cake`, even random letters) gets **low confidence**, not a refusal: multilingual-e5 gives similarities above the 0.83 abstention threshold even for gibberish. The video shows the low-confidence warning, which is what really happens. Tuning is tracked on #82.
- Some cards are generic pages ("Studies", "Research Groups"). Keep the first two cards in view.

## After recording

Check the length and package everything with the T26 script:

```bash
.venv/Scripts/python scripts/package_submission.py --pitch pitch.pdf --report report.pdf --video demo.mp4 --video-url <public link>
```

It fails (and does not build the ZIP) if the video is over 120 s, the pitch over 10 pages or the report over 6.
