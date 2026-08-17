#!/usr/bin/env python3
"""Generate the deterministic example workbooks stored in `sample_data/excel/`.

The data is fictional but shaped like real operational exports: multiple sheets,
lookup tables that join back to the fact sheet, typed date/number columns, and
free-text columns that exercise the semantic path of the Q&A engine.

Usage:
    python scripts/generate_sample_excels.py                 # regenerate all workbooks
    python scripts/generate_sample_excels.py --only retail   # regenerate one workbook
    python scripts/generate_sample_excels.py --scale 2       # double every row count
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Sequence

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "sample_data" / "excel"

Sheet = tuple[str, list[str], Iterator[Sequence[object]]]

REGIONS = ["North", "South", "East", "West", "Central"]
CITIES = [
    ("Mumbai", "Maharashtra", "West"), ("Pune", "Maharashtra", "West"),
    ("Ahmedabad", "Gujarat", "West"), ("Delhi", "Delhi", "North"),
    ("Gurugram", "Haryana", "North"), ("Jaipur", "Rajasthan", "North"),
    ("Lucknow", "Uttar Pradesh", "North"), ("Bengaluru", "Karnataka", "South"),
    ("Chennai", "Tamil Nadu", "South"), ("Hyderabad", "Telangana", "South"),
    ("Kochi", "Kerala", "South"), ("Kolkata", "West Bengal", "East"),
    ("Bhubaneswar", "Odisha", "East"), ("Guwahati", "Assam", "East"),
    ("Patna", "Bihar", "East"), ("Indore", "Madhya Pradesh", "Central"),
    ("Bhopal", "Madhya Pradesh", "Central"), ("Nagpur", "Maharashtra", "Central"),
]
FIRST_NAMES = [
    "Aarav", "Ananya", "Rohan", "Priya", "Kabir", "Meera", "Ishaan", "Diya", "Vihaan", "Saanvi",
    "Arjun", "Nisha", "Rahul", "Fatima", "Vikram", "Neha", "Aditya", "Kavya", "Sameer", "Tara",
    "Farhan", "Ritu", "Manav", "Ayesha", "Nikhil", "Sneha", "Karthik", "Ira", "Dev", "Anjali",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Singh", "Khan", "Bose", "Chatterjee",
    "Gupta", "Menon", "Joshi", "Kulkarni", "Das", "Mehta", "Rao", "Pillai", "Banerjee", "Kapoor",
]


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _weighted(rng: random.Random, options: Sequence[tuple[object, float]]) -> object:
    values = [option for option, _ in options]
    weights = [weight for _, weight in options]
    return rng.choices(values, weights=weights, k=1)[0]


def _seasonality(day: date) -> float:
    """Festive-season style demand multiplier so trends are discoverable."""
    return {10: 1.45, 11: 1.30, 12: 1.15, 3: 1.10}.get(day.month, 1.0)


# --------------------------------------------------------------------------- retail
PRODUCT_CATEGORIES = {
    "Electronics": ["Smartphones", "Laptops", "Audio", "Wearables"],
    "Home & Kitchen": ["Cookware", "Small Appliances", "Furniture", "Decor"],
    "Apparel": ["Menswear", "Womenswear", "Footwear", "Accessories"],
    "Grocery": ["Beverages", "Snacks", "Staples", "Personal Care"],
    "Sports": ["Fitness", "Outdoor", "Team Sports", "Cycling"],
}
BRANDS = ["Nimbus", "Kestrel", "Orbit", "Vantage", "Lumen", "Ashvin", "Peakline", "Corvo"]
CUSTOMER_NOTES = [
    "Delivered on time, packaging was intact and the product works perfectly.",
    "Courier left the parcel with the security desk without calling me first.",
    "Item arrived with a scratched panel, requested a replacement through support.",
    "Great value for money, would order again during the next festive sale.",
    "Invoice shows the wrong GST number, need a corrected copy for reimbursement.",
    "Delivery slipped by four days and no proactive update was shared.",
    "Product matches the description; the accessories bundle was missing though.",
    "Refund was processed quickly after the return pickup was scheduled.",
    "The size chart is misleading, ordered a medium and it fits like a small.",
    "Bulk order for our office pantry, the finance team needs a consolidated bill.",
]


def build_retail(rng: random.Random, rows: int) -> list[Sheet]:
    stores = []
    for index in range(60):
        city, state, region = CITIES[index % len(CITIES)]
        stores.append([
            f"ST-{1000 + index}", f"{city} {rng.choice(['Central', 'Galleria', 'Junction', 'Hub'])}",
            city, state, region,
            _weighted(rng, [("Flagship", 0.2), ("Standard", 0.5), ("Express", 0.3)]),
            date(2015, 1, 1) + timedelta(days=rng.randrange(3200)),
            rng.randrange(1800, 42000, 100), _name(rng),
        ])

    products = []
    for index in range(600):
        category = rng.choice(list(PRODUCT_CATEGORIES))
        sub_category = rng.choice(PRODUCT_CATEGORIES[category])
        unit_cost = round(rng.uniform(120, 48000), 2)
        products.append([
            f"SKU-{20000 + index}",
            f"{rng.choice(BRANDS)} {sub_category[:-1] if sub_category.endswith('s') else sub_category} {rng.randrange(100, 999)}",
            category, sub_category, rng.choice(BRANDS), unit_cost,
            round(unit_cost * rng.uniform(1.18, 1.85), 2),
            date(2019, 1, 1) + timedelta(days=rng.randrange(2000)),
            f"Supplier {rng.randrange(1, 45):02d}",
            f"{sub_category} line built for {rng.choice(['everyday use', 'premium buyers', 'value shoppers', 'small businesses'])} "
            f"with {rng.choice(['a 2 year warranty', 'free installation', 'bulk pricing', 'energy saving certification'])}.",
        ])

    def orders() -> Iterator[Sequence[object]]:
        start = date(2024, 1, 1)
        for index in range(rows):
            order_date = start + timedelta(days=rng.randrange(366))
            store = stores[rng.randrange(len(stores))]
            product = products[rng.randrange(len(products))]
            quantity = max(1, int(rng.triangular(1, 9, 2) * _seasonality(order_date)))
            unit_price = round(float(product[6]) * rng.uniform(0.92, 1.08), 2)
            discount = _weighted(rng, [(0.0, 0.45), (5.0, 0.2), (10.0, 0.18), (15.0, 0.1), (25.0, 0.07)])
            gross = round(unit_price * quantity, 2)
            net = round(gross * (1 - float(discount) / 100), 2)
            cost = round(float(product[5]) * quantity, 2)
            status = _weighted(rng, [("Delivered", 0.82), ("Shipped", 0.08), ("Cancelled", 0.05), ("Returned", 0.05)])
            yield [
                f"ORD-2024-{index + 100000}", order_date, store[0], product[0],
                _weighted(rng, [("Web", 0.38), ("Mobile App", 0.34), ("Store", 0.2), ("Partner", 0.08)]),
                f"CUST-{rng.randrange(1, 26000):06d}",
                _weighted(rng, [("Consumer", 0.62), ("Small Business", 0.24), ("Enterprise", 0.14)]),
                quantity, unit_price, float(discount), gross, net, cost, round(net - cost, 2),
                _weighted(rng, [("UPI", 0.42), ("Credit Card", 0.24), ("Debit Card", 0.16), ("Net Banking", 0.1), ("Cash on Delivery", 0.08)]),
                rng.randrange(1, 11), status, "Yes" if status == "Returned" else "No",
                _weighted(rng, [("", 0.6), ("FESTIVE10", 0.15), ("NEWUSER", 0.1), ("BULK25", 0.08), ("WEEKEND5", 0.07)]),
                rng.choice(CUSTOMER_NOTES) if rng.random() < 0.35 else "",
            ]

    return [
        ("Orders", [
            "order_id", "order_date", "store_id", "product_id", "channel", "customer_id",
            "customer_segment", "quantity", "unit_price", "discount_pct", "gross_amount",
            "net_amount", "cost_amount", "profit", "payment_method", "delivery_days",
            "order_status", "returned", "promo_code", "customer_note",
        ], orders()),
        ("Products", [
            "product_id", "product_name", "category", "sub_category", "brand", "unit_cost",
            "list_price", "launch_date", "supplier", "description",
        ], iter(products)),
        ("Stores", [
            "store_id", "store_name", "city", "state", "region", "store_format",
            "opened_on", "floor_area_sqft", "store_manager",
        ], iter(stores)),
    ]


# --------------------------------------------------------------------------- hr
DEPARTMENTS = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Engineering Manager", "QA Engineer", "Site Reliability Engineer"],
    "Data & Analytics": ["Data Analyst", "Data Engineer", "Data Scientist", "Analytics Manager"],
    "Sales": ["Account Executive", "Sales Development Rep", "Regional Sales Manager", "Solutions Consultant"],
    "Customer Success": ["Support Specialist", "Customer Success Manager", "Onboarding Lead"],
    "Finance": ["Financial Analyst", "Accountant", "Finance Manager"],
    "People Operations": ["Recruiter", "HR Business Partner", "Learning Specialist"],
    "Marketing": ["Content Strategist", "Performance Marketer", "Brand Manager"],
    "Operations": ["Operations Analyst", "Facilities Coordinator", "Program Manager"],
}
REVIEW_COMMENTS = [
    "Consistently ships high quality work and mentors newer teammates during sprint planning.",
    "Strong domain knowledge but needs to communicate blockers earlier in the cycle.",
    "Exceeded quota two quarters in a row and rebuilt the territory pipeline from scratch.",
    "Reliable delivery, however documentation for handovers is frequently incomplete.",
    "Took ownership of the migration project and reduced manual effort significantly.",
    "Collaboration with partner teams improved after the feedback in the last review.",
    "Attendance and responsiveness dipped during the last quarter, flagged for a check-in.",
    "Excellent stakeholder management; consistently rated highly by internal customers.",
    "Technical depth is good, next step is leading a cross-functional initiative.",
    "Handled escalations calmly and created a runbook the whole team now uses.",
]
SKILL_POOL = [
    "Python", "SQL", "Excel", "Power BI", "Tableau", "Java", "Kubernetes", "Salesforce",
    "Negotiation", "Public Speaking", "Project Management", "Financial Modelling",
    "Recruiting", "Copywriting", "Docker", "React", "Airflow", "Statistics",
]


def build_hr(rng: random.Random, rows: int) -> list[Sheet]:
    departments = [
        [f"DEP-{index + 1:02d}", name, f"{name} Group", _name(rng), rng.randrange(40, 320) * 10000, rng.choice(REGIONS)]
        for index, name in enumerate(DEPARTMENTS)
    ]

    def employees() -> Iterator[Sequence[object]]:
        for index in range(rows):
            department = rng.choice(list(DEPARTMENTS))
            title = rng.choice(DEPARTMENTS[department])
            level = str(_weighted(rng, [("L1", 0.18), ("L2", 0.3), ("L3", 0.26), ("L4", 0.16), ("L5", 0.07), ("L6", 0.03)]))
            hire_date = date(2013, 1, 1) + timedelta(days=rng.randrange(4300))
            base = {"L1": 480000, "L2": 780000, "L3": 1250000, "L4": 1950000, "L5": 3100000, "L6": 4600000}[level]
            salary = round(base * rng.uniform(0.85, 1.2), -2)
            attrition = rng.random() < 0.14
            exit_date = hire_date + timedelta(days=rng.randrange(200, 3000)) if attrition else None
            if exit_date and exit_date > date(2025, 6, 30):
                exit_date, attrition = None, False
            city, state, region = CITIES[rng.randrange(len(CITIES))]
            yield [
                f"EMP-{index + 10000}", _name(rng), department, title, level, city, region,
                hire_date,
                _weighted(rng, [("Full Time", 0.86), ("Contract", 0.09), ("Intern", 0.05)]),
                salary, round(rng.uniform(0, 22), 1),
                f"EMP-{rng.randrange(10000, 10000 + max(rows // 12, 20))}",
                _weighted(rng, [(1, 0.04), (2, 0.13), (3, 0.44), (4, 0.29), (5, 0.1)]),
                round(rng.uniform(2.4, 5.0), 2),
                "Yes" if attrition else "No", exit_date,
                ", ".join(sorted(rng.sample(SKILL_POOL, k=rng.randrange(2, 5)))),
                rng.randrange(0, 26), state,
                rng.choice(REVIEW_COMMENTS) if rng.random() < 0.45 else "",
            ]

    return [
        ("Employees", [
            "employee_id", "full_name", "department", "job_title", "level", "work_city", "region",
            "hire_date", "employment_type", "annual_salary_inr", "bonus_pct", "manager_id",
            "performance_rating", "engagement_score", "attrition", "exit_date", "skills",
            "training_hours", "state", "review_comment",
        ], employees()),
        ("Departments", ["department_id", "department", "division", "department_head", "annual_budget_inr", "hq_region"], iter(departments)),
    ]


# --------------------------------------------------------------------------- support
TICKET_CATEGORIES = {
    "Billing": ["Invoice dispute", "Refund request", "Payment failure", "Plan upgrade"],
    "Technical": ["Login failure", "Sync error", "Performance degradation", "Integration bug"],
    "Account": ["Access request", "Role change", "Data export", "Account closure"],
    "Onboarding": ["Setup help", "Training request", "Migration support"],
    "Feature Request": ["New report", "API endpoint", "Mobile parity"],
}
TICKET_BODIES = [
    "Users in the Mumbai office cannot sign in after the single sign-on change was rolled out last night.",
    "The monthly invoice charges for 42 seats but our contract was reduced to 30 seats in April.",
    "Dashboard exports time out whenever the date range is longer than ninety days.",
    "Two-factor codes arrive several minutes late, so the login window expires before entry.",
    "We need the payment retried on the corporate card because the first attempt was declined.",
    "Data sync from the warehouse stopped at 02:00 and no error was raised in the audit log.",
    "Requesting a bulk export of all customer records for the annual compliance audit.",
    "The mobile app crashes on Android 14 when opening the saved reports tab.",
    "Please help us migrate historical tickets from the legacy helpdesk before the renewal.",
    "Would like an API endpoint that returns aggregated usage per workspace per day.",
    "Charges appear twice on the same invoice line and finance has put the payment on hold.",
    "Performance of the search page degraded noticeably after the last product release.",
]


def build_support(rng: random.Random, rows: int) -> list[Sheet]:
    teams = ["Tier 1", "Tier 2", "Billing Desk", "Enterprise Pod", "Technical Escalations"]
    agents = [
        [f"AG-{index + 500}", _name(rng), rng.choice(teams), rng.choice(REGIONS),
         date(2018, 1, 1) + timedelta(days=rng.randrange(2500)),
         _weighted(rng, [("Associate", 0.5), ("Specialist", 0.34), ("Lead", 0.16)]),
         rng.choice(["English", "English, Hindi", "English, Tamil", "English, Marathi", "English, Bengali"])]
        for index in range(300)
    ]

    def tickets() -> Iterator[Sequence[object]]:
        start = datetime(2024, 1, 1, 0, 0)
        for index in range(rows):
            created = start + timedelta(minutes=rng.randrange(527040))
            priority = str(_weighted(rng, [("Low", 0.31), ("Medium", 0.4), ("High", 0.22), ("Critical", 0.07)]))
            category = rng.choice(list(TICKET_CATEGORIES))
            first_response = max(2, int(rng.expovariate(1 / {"Critical": 12, "High": 30, "Medium": 75, "Low": 160}[priority])))
            resolution_hours = round(max(0.3, rng.gammavariate(2.0, {"Critical": 2.5, "High": 5.0, "Medium": 11.0, "Low": 20.0}[priority])), 2)
            status = _weighted(rng, [("Resolved", 0.78), ("Closed", 0.11), ("In Progress", 0.07), ("Waiting on Customer", 0.04)])
            resolved = created + timedelta(hours=resolution_hours) if status in {"Resolved", "Closed"} else None
            sla_target = {"Critical": 4, "High": 12, "Medium": 24, "Low": 48}[priority]
            agent = agents[rng.randrange(len(agents))]
            yield [
                f"TCK-{index + 700000}", created, resolved,
                _weighted(rng, [("Email", 0.36), ("Chat", 0.28), ("Phone", 0.18), ("Portal", 0.13), ("Social", 0.05)]),
                priority, category, rng.choice(TICKET_CATEGORIES[category]),
                f"CUST-{rng.randrange(1, 26000):06d}",
                _weighted(rng, [("Starter", 0.34), ("Growth", 0.4), ("Enterprise", 0.26)]),
                rng.choice(REGIONS), agent[0], agent[2], first_response, resolution_hours,
                "Yes" if resolution_hours > sla_target else "No", status,
                rng.randrange(1, 6) if status in {"Resolved", "Closed"} else None,
                rng.randrange(0, 5),
                f"{rng.choice(TICKET_CATEGORIES[category])} reported by {rng.choice(['finance', 'IT', 'operations', 'the admin team'])}",
                rng.choice(TICKET_BODIES),
            ]

    return [
        ("Tickets", [
            "ticket_id", "created_at", "resolved_at", "channel", "priority", "category",
            "issue_type", "customer_id", "plan_tier", "region", "agent_id", "agent_team",
            "first_response_minutes", "resolution_hours", "sla_breached", "status",
            "csat_score", "reopen_count", "subject", "description",
        ], tickets()),
        ("Agents", ["agent_id", "agent_name", "team", "region", "joined_on", "seniority", "languages"], iter(agents)),
    ]


# --------------------------------------------------------------------------- iot
DEVICE_TYPES = ["HVAC", "Chiller", "Lighting", "Compressor", "Server Rack", "Boiler"]
MAINTENANCE_NOTES = [
    "Filter replaced during the scheduled preventive maintenance window.",
    "Vibration levels above baseline, bearing inspection recommended next visit.",
    "Firmware updated to the latest release, telemetry stable afterwards.",
    "Sensor drift detected, recalibrated against the reference meter on site.",
    "Unit tripped on overload and was restarted by the facilities technician.",
    "Coolant top-up completed, no leakage observed after the pressure test.",
]


def build_iot(rng: random.Random, rows: int) -> list[Sheet]:
    sites = []
    for index in range(40):
        city, state, region = CITIES[index % len(CITIES)]
        sites.append([
            f"SITE-{index + 100}", f"{city} {rng.choice(['Plant', 'Campus', 'Warehouse', 'Data Centre'])}",
            city, state, region,
            _weighted(rng, [("Manufacturing", 0.4), ("Office", 0.35), ("Warehouse", 0.25)]),
            rng.randrange(200, 5000) * 10, _name(rng), round(rng.uniform(4.5, 9.5), 2),
        ])

    def readings() -> Iterator[Sequence[object]]:
        start = datetime(2024, 4, 1, 0, 0)
        for index in range(rows):
            timestamp = start + timedelta(minutes=15 * (index % 96) + 1440 * (index // 96 % 275))
            site = sites[rng.randrange(len(sites))]
            device_type = rng.choice(DEVICE_TYPES)
            base_load = {"HVAC": 42, "Chiller": 65, "Lighting": 12, "Compressor": 38, "Server Rack": 28, "Boiler": 55}[device_type]
            hour_factor = 1.35 if 9 <= timestamp.hour <= 19 else 0.7
            energy = round(base_load * hour_factor * rng.uniform(0.75, 1.3), 3)
            anomaly = rng.random() < 0.03
            if anomaly:
                energy = round(energy * rng.uniform(1.8, 2.6), 3)
            voltage = round(rng.gauss(415, 6.5), 2)
            yield [
                f"RD-{index + 4000000}", timestamp, site[0], site[4],
                f"MTR-{rng.randrange(1, 900):04d}", device_type, energy, voltage,
                round(energy * 1000 / (voltage * 1.732 * 0.92), 2), round(rng.uniform(0.82, 0.99), 3),
                round(rng.gauss(29, 4.2), 2), round(rng.uniform(28, 82), 1),
                round(energy * 0.82, 3), round(energy * 7.4, 2),
                _weighted(rng, [("Normal", 0.9), ("Warning", 0.07), ("Fault", 0.03)]),
                "Yes" if anomaly else "No",
                rng.choice(MAINTENANCE_NOTES) if rng.random() < 0.12 else "",
            ]

    return [
        ("Readings", [
            "reading_id", "reading_timestamp", "site_id", "region", "meter_id", "device_type",
            "energy_kwh", "voltage_v", "current_a", "power_factor", "temperature_c",
            "humidity_pct", "co2_kg", "cost_inr", "device_status", "anomaly_flag", "maintenance_note",
        ], readings()),
        ("Sites", [
            "site_id", "site_name", "city", "state", "region", "site_type",
            "floor_area_sqm", "site_manager", "tariff_inr_per_kwh",
        ], iter(sites)),
    ]


DATASETS: dict[str, tuple[str, int, int, Callable[[random.Random, int], list[Sheet]]]] = {
    "retail": ("retail_orders_2024.xlsx", 48000, 20240117, build_retail),
    "hr": ("hr_workforce.xlsx", 32500, 20240218, build_hr),
    "support": ("support_tickets.xlsx", 45000, 20240319, build_support),
    "energy": ("iot_energy_readings.xlsx", 38000, 20240420, build_iot),
}


def write_workbook(path: Path, sheets: list[Sheet]) -> None:
    workbook = Workbook(write_only=True)
    for title, headers, rows in sheets:
        worksheet = workbook.create_sheet(title=title)
        worksheet.append(headers)
        for row in rows:
            worksheet.append(list(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument("--only", choices=sorted(DATASETS), action="append", help="generate a subset")
    parser.add_argument("--scale", type=float, default=1.0, help="multiply every fact-table row count")
    arguments = parser.parse_args()
    selected = arguments.only or sorted(DATASETS)
    for key in selected:
        filename, rows, seed, builder = DATASETS[key]
        target = arguments.out / filename
        scaled = max(1, int(rows * arguments.scale))
        write_workbook(target, builder(random.Random(seed), scaled))
        print(f"{target} ({scaled} fact rows, {target.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
