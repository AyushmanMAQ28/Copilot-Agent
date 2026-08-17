# Example Excel workbooks

Four multi-sheet workbooks with realistic-looking but entirely fictional data. Each
one has a large fact sheet (30,000–50,000 rows) plus small lookup sheets that can be
joined back to it, typed date/number columns, and free-text columns for the semantic
path of the Q&A engine.

Everything is generated deterministically by
[`scripts/generate_sample_excels.py`](../../scripts/generate_sample_excels.py), so the
files can be recreated byte-for-byte:

```bash
python scripts/generate_sample_excels.py               # all four workbooks
python scripts/generate_sample_excels.py --only retail # just one
python scripts/generate_sample_excels.py --scale 2     # double every row count
```

| Workbook | Sheets (rows) | Theme |
| --- | --- | --- |
| `retail_orders_2024.xlsx` | `Orders` (48,000), `Products` (600), `Stores` (60) | Omnichannel retail orders for 2024 with pricing, profit, delivery and returns |
| `support_tickets.xlsx` | `Tickets` (45,000), `Agents` (300) | Customer support tickets with SLA, CSAT, agent teams and free-text descriptions |
| `iot_energy_readings.xlsx` | `Readings` (38,000), `Sites` (40) | Half-hourly building energy meter readings with anomalies and maintenance notes |
| `hr_workforce.xlsx` | `Employees` (32,500), `Departments` (8) | Workforce records with salary, performance, attrition and review comments |

## Joins

Every fact sheet shares a key with its lookup sheets, so questions can cross sheets:

- `Orders.store_id` → `Stores.store_id`, `Orders.product_id` → `Products.product_id`
- `Tickets.agent_id` → `Agents.agent_id`
- `Readings.site_id` → `Sites.site_id`
- `Employees.department` → `Departments.department`

## Questions to try

```bash
cd backend
python -m app.qa.cli ask ../sample_data/excel/retail_orders_2024.xlsx  "What is the total net amount by store format?"
python -m app.qa.cli ask ../sample_data/excel/support_tickets.xlsx     "How many tickets were created for each priority?"
python -m app.qa.cli ask ../sample_data/excel/iot_energy_readings.xlsx "What is the average energy kwh by device type?"
python -m app.qa.cli ask ../sample_data/excel/hr_workforce.xlsx        "What is the average annual salary inr per department?"
```

Other useful prompts:

- Retail: *total profit by category*, *how many orders were cancelled*, *average delivery days per region*, *which products mention free installation*
- Support: *count of tickets per agent team*, *average resolution hours by category*, *which tickets mention a refund delay*, *how many tickets mention a billing error*
- Energy: *total cost inr by site type*, *how many readings are flagged as anomalies*, *maintenance notes about a faulty sensor*
- HR: *attrition count by department*, *average engagement score per level*, *review comments about mentoring*

Without an `LLM_API_KEY` the questions above are planned by the built-in deterministic
planner; with a key configured, the router and SQL agent handle more complex phrasing
(multi-condition filters, joins across sheets, time windows).

## Notes

- The workbooks are ~19 MB in total; they are committed so the pipeline can be tried
  without generating data first.
- All names, cities, IDs, salaries and comments are synthetic. No real person,
  customer or company is represented.
- The first ingest of a workbook takes a few seconds (Excel → Parquet); afterwards the
  cache in `backend/data/cache` makes reopening it near-instant.
