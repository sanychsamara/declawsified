# declawsified-dashboard

Read-only Streamlit dashboard for the Declawsified spend log
(`~/.declawsified/spend/spend-YYYY-MM-DD.jsonl`).

Design + execution plan: [`docs/streamlit.md`](../../docs/streamlit.md).
User guide for the underlying CLI report: [`docs/cost-attribution-readme.md`](../../docs/cost-attribution-readme.md).

## Install

```bash
pip install -e "./sources/dashboard"
```

## Run

```bash
# Against your real proxy spend log
streamlit run sources/dashboard/declawsified_dashboard/app.py

# Against the synthetic 50-row sample
mkdir -p /tmp/dashboard-demo
cp data/sample-spend-log.jsonl /tmp/dashboard-demo/spend-2026-04-26.jsonl
DECLAWSIFIED_SPEND_LOG_DIR=/tmp/dashboard-demo \
  streamlit run sources/dashboard/declawsified_dashboard/app.py
```

Or via the console-script entry point:

```bash
declawsified-dashboard
```

Then open http://127.0.0.1:8501.

## Tests

```bash
cd sources/dashboard && python -m pytest -q
```
