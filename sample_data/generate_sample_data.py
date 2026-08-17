"""Generate large, realistic sample datasets for the CSV Insights Agent.

The script writes four business datasets of 30,000-50,000 rows each. Every
dataset is produced from a fixed seed, so repeated runs create identical files.

Usage:
    python sample_data/generate_sample_data.py                # Excel workbooks
    python sample_data/generate_sample_data.py --format csv   # CSV files
    python sample_data/generate_sample_data.py --format both
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BASE_SEED = 20260817
OUTPUT_DIR = Path(__file__).resolve().parent

RETAIL_ROWS = 48_000
HR_ROWS = 32_000
HEALTHCARE_ROWS = 36_000
BANKING_ROWS = 50_000

MONTH_WEIGHTS = np.array(
    [0.72, 0.68, 0.85, 0.82, 0.90, 0.88, 0.86, 0.89, 0.95, 1.05, 1.35, 1.45]
)


def _rng(offset: int) -> np.random.Generator:
    return np.random.default_rng(BASE_SEED + offset)


def _pick(rng: np.random.Generator, values: list[str], weights: list[float], size: int) -> np.ndarray:
    probabilities = np.array(weights, dtype=float)
    return rng.choice(values, size=size, p=probabilities / probabilities.sum())


def _seasonal_dates(
    rng: np.random.Generator, start: str, end: str, size: int
) -> pd.DatetimeIndex:
    """Sample dates in a range, weighting months so demand peaks late in the year."""
    days = pd.date_range(start=start, end=end, freq="D")
    weights = MONTH_WEIGHTS[days.month - 1]
    weights = weights * np.where(days.dayofweek >= 5, 0.65, 1.0)
    return pd.DatetimeIndex(rng.choice(days, size=size, p=weights / weights.sum())).normalize()


def _blank_out(
    rng: np.random.Generator, series: pd.Series, fraction: float
) -> pd.Series:
    """Blank a small share of values so the data mirrors real-world gaps."""
    mask = rng.random(len(series)) < fraction
    return series.mask(mask)


def _lookup(keys: np.ndarray, mapping: dict[str, float]) -> np.ndarray:
    return np.array([mapping[key] for key in keys], dtype=float)


def build_retail_sales() -> pd.DataFrame:
    rng = _rng(1)
    size = RETAIL_ROWS

    region_countries = {
        "North America": ["United States", "Canada", "Mexico"],
        "Europe": ["United Kingdom", "Germany", "France", "Netherlands", "Spain"],
        "Asia Pacific": ["India", "Japan", "Australia", "Singapore"],
        "Latin America": ["Brazil", "Chile", "Colombia"],
        "Middle East & Africa": ["United Arab Emirates", "South Africa", "Saudi Arabia"],
    }
    category_products = {
        "Laptops": ["UltraBook 14", "UltraBook 16", "WorkStation Pro", "FieldBook Rugged"],
        "Monitors": ["ClearView 24", "ClearView 27", "ClearView 34 Curved"],
        "Accessories": ["Wireless Mouse", "Mechanical Keyboard", "USB-C Dock", "Laptop Sleeve"],
        "Networking": ["Mesh Router", "Managed Switch 24P", "Access Point Pro"],
        "Storage": ["Portable SSD 1TB", "NAS 4-Bay", "Enterprise HDD 8TB"],
        "Software": ["Security Suite", "Analytics Studio", "Backup Manager"],
    }
    category_prices = {
        "Laptops": 1250.0,
        "Monitors": 340.0,
        "Accessories": 55.0,
        "Networking": 410.0,
        "Storage": 220.0,
        "Software": 180.0,
    }

    regions = _pick(
        rng, list(region_countries), [0.34, 0.27, 0.22, 0.10, 0.07], size
    )
    countries = np.array(
        [rng.choice(region_countries[region]) for region in regions], dtype=object
    )
    categories = _pick(
        rng, list(category_products), [0.18, 0.14, 0.30, 0.11, 0.14, 0.13], size
    )
    products = np.array(
        [rng.choice(category_products[category]) for category in categories], dtype=object
    )

    order_dates = _seasonal_dates(rng, "2024-01-01", "2025-12-31", size)
    channels = _pick(
        rng,
        ["Online", "Retail Store", "Marketplace", "Partner Reseller"],
        [0.47, 0.24, 0.18, 0.11],
        size,
    )
    segments = _pick(
        rng,
        ["Consumer", "Small Business", "Enterprise", "Education", "Government"],
        [0.42, 0.26, 0.18, 0.09, 0.05],
        size,
    )

    quantities = np.minimum(rng.geometric(p=0.45, size=size), 15)
    unit_prices = np.round(
        _lookup(categories, category_prices) * rng.lognormal(mean=0.0, sigma=0.22, size=size),
        2,
    )
    discounts = _pick(
        rng, ["0", "5", "10", "15", "20", "25"], [0.38, 0.22, 0.18, 0.11, 0.07, 0.04], size
    ).astype(float)
    revenue = np.round(quantities * unit_prices * (1 - discounts / 100), 2)

    shipping_base = {"Online": 3, "Retail Store": 0, "Marketplace": 5, "Partner Reseller": 6}
    shipping_days = np.clip(
        _lookup(channels, shipping_base) + rng.poisson(lam=1.6, size=size), 0, 21
    ).astype(int)

    frame = pd.DataFrame(
        {
            "OrderID": [f"SO-{number:07d}" for number in range(100_001, 100_001 + size)],
            "OrderDate": order_dates,
            "Channel": channels,
            "Region": regions,
            "Country": countries,
            "CustomerSegment": segments,
            "ProductCategory": categories,
            "ProductName": products,
            "Quantity": quantities,
            "UnitPrice": unit_prices,
            "DiscountPercent": discounts,
            "NetRevenue": revenue,
            "PaymentMethod": _pick(
                rng,
                ["Credit Card", "Invoice", "Digital Wallet", "Bank Transfer", "Gift Card"],
                [0.44, 0.21, 0.19, 0.12, 0.04],
                size,
            ),
            "ShippingDays": shipping_days,
            "Returned": _pick(rng, ["No", "Yes"], [0.955, 0.045], size),
        }
    ).sort_values("OrderDate", kind="stable", ignore_index=True)

    frame["DiscountPercent"] = _blank_out(rng, frame["DiscountPercent"], 0.015)
    return frame


def build_hr_directory() -> pd.DataFrame:
    rng = _rng(2)
    size = HR_ROWS

    first_names = [
        "Aarav", "Alex", "Amara", "Ana", "Ben", "Carla", "Chen", "Daniel", "Elena",
        "Emma", "Farah", "Grace", "Hiro", "Ibrahim", "Isabel", "Jonas", "Kavya",
        "Liam", "Lucia", "Mateo", "Maya", "Nadia", "Noah", "Olga", "Omar", "Priya",
        "Rafael", "Riya", "Samuel", "Sofia", "Takeshi", "Zara",
    ]
    last_names = [
        "Almeida", "Andersen", "Bauer", "Chen", "Diallo", "Dubois", "Fernandez",
        "Garcia", "Haddad", "Ivanov", "Johnson", "Kimura", "Kowalski", "Lambert",
        "Martins", "Mehta", "Nakamura", "Novak", "Okafor", "Patel", "Rossi",
        "Silva", "Smith", "Tanaka", "Weber", "Williams", "Yilmaz",
    ]
    department_titles = {
        "Engineering": ["Software Engineer", "QA Engineer", "Site Reliability Engineer"],
        "Sales": ["Account Executive", "Sales Development Rep", "Solutions Consultant"],
        "Customer Success": ["Customer Success Manager", "Support Specialist"],
        "Marketing": ["Product Marketing Manager", "Campaign Specialist"],
        "Finance": ["Financial Analyst", "Accountant", "Controller"],
        "Human Resources": ["HR Business Partner", "Recruiter", "People Analyst"],
        "Operations": ["Operations Analyst", "Program Manager"],
        "Data & Analytics": ["Data Analyst", "Data Engineer", "Data Scientist"],
    }
    location_countries = {
        "Seattle": "United States",
        "Austin": "United States",
        "Toronto": "Canada",
        "London": "United Kingdom",
        "Berlin": "Germany",
        "Warsaw": "Poland",
        "Bengaluru": "India",
        "Hyderabad": "India",
        "Singapore": "Singapore",
        "Sydney": "Australia",
        "Sao Paulo": "Brazil",
    }
    department_pay = {
        "Engineering": 118_000.0,
        "Sales": 96_000.0,
        "Customer Success": 82_000.0,
        "Marketing": 89_000.0,
        "Finance": 94_000.0,
        "Human Resources": 84_000.0,
        "Operations": 87_000.0,
        "Data & Analytics": 112_000.0,
    }
    location_pay = {
        "Seattle": 1.18,
        "Austin": 1.05,
        "Toronto": 0.95,
        "London": 1.08,
        "Berlin": 0.98,
        "Warsaw": 0.72,
        "Bengaluru": 0.48,
        "Hyderabad": 0.45,
        "Singapore": 1.02,
        "Sydney": 1.04,
        "Sao Paulo": 0.55,
    }

    departments = _pick(
        rng,
        list(department_titles),
        [0.29, 0.16, 0.12, 0.08, 0.07, 0.06, 0.11, 0.11],
        size,
    )
    titles = np.array(
        [rng.choice(department_titles[department]) for department in departments],
        dtype=object,
    )
    locations = _pick(
        rng,
        list(location_countries),
        [0.13, 0.09, 0.07, 0.11, 0.08, 0.05, 0.16, 0.09, 0.06, 0.06, 0.10],
        size,
    )
    levels = _pick(
        rng,
        ["Associate", "Professional", "Senior", "Lead", "Manager", "Director"],
        [0.20, 0.31, 0.24, 0.11, 0.10, 0.04],
        size,
    )
    level_multiplier = {
        "Associate": 0.72,
        "Professional": 1.0,
        "Senior": 1.32,
        "Lead": 1.55,
        "Manager": 1.72,
        "Director": 2.35,
    }

    as_of = pd.Timestamp("2026-06-30")
    hire_dates = as_of - pd.to_timedelta(
        np.round(rng.gamma(shape=2.0, scale=780, size=size)).astype(int).clip(15, 7_300),
        unit="D",
    )
    tenure_years = np.round((as_of - hire_dates).days / 365.25, 1)

    salaries = np.round(
        _lookup(departments, department_pay)
        * _lookup(locations, location_pay)
        * _lookup(levels, level_multiplier)
        * rng.lognormal(mean=0.0, sigma=0.11, size=size),
        -2,
    )
    ratings = _pick(
        rng, ["1", "2", "3", "4", "5"], [0.02, 0.08, 0.42, 0.35, 0.13], size
    ).astype(float)
    engagement = np.clip(
        np.round(rng.normal(loc=72, scale=13, size=size) + (ratings - 3) * 4), 0, 100
    )
    attrition_risk = 0.11 + (ratings <= 2) * 0.22 + (tenure_years < 1.5) * 0.06

    frame = pd.DataFrame(
        {
            "EmployeeID": [f"EMP-{number:06d}" for number in range(100_001, 100_001 + size)],
            "FullName": [
                f"{rng.choice(first_names)} {rng.choice(last_names)}" for _ in range(size)
            ],
            "Department": departments,
            "JobTitle": titles,
            "JobLevel": levels,
            "Location": locations,
            "Country": np.array([location_countries[city] for city in locations], dtype=object),
            "EmploymentType": _pick(
                rng, ["Full-time", "Part-time", "Contract"], [0.86, 0.06, 0.08], size
            ),
            "HireDate": hire_dates,
            "TenureYears": tenure_years,
            "AnnualSalaryUSD": salaries,
            "BonusPercent": np.round(rng.uniform(0, 22, size=size), 1),
            "PerformanceRating": ratings,
            "EngagementScore": engagement,
            "TrainingHours": np.clip(rng.poisson(lam=24, size=size), 0, None),
            "AttritionFlag": np.where(rng.random(size) < attrition_risk, "Yes", "No"),
        }
    ).sort_values("HireDate", kind="stable", ignore_index=True)

    frame["PerformanceRating"] = _blank_out(rng, frame["PerformanceRating"], 0.03)
    frame["EngagementScore"] = _blank_out(rng, frame["EngagementScore"], 0.05)
    return frame


def build_hospital_encounters() -> pd.DataFrame:
    rng = _rng(3)
    size = HEALTHCARE_ROWS

    department_diagnoses = {
        "Cardiology": ["Heart Failure", "Atrial Fibrillation", "Acute Myocardial Infarction"],
        "Orthopedics": ["Hip Replacement", "Knee Osteoarthritis", "Fracture - Femur"],
        "Oncology": ["Breast Cancer", "Colorectal Cancer", "Lymphoma"],
        "Emergency": ["Sepsis", "Trauma - Multiple Injuries", "Acute Appendicitis"],
        "Pediatrics": ["Asthma Exacerbation", "Bronchiolitis", "Gastroenteritis"],
        "Neurology": ["Ischemic Stroke", "Epilepsy", "Migraine - Intractable"],
        "General Medicine": ["Pneumonia", "Type 2 Diabetes", "COPD Exacerbation"],
        "Maternity": ["Vaginal Delivery", "Cesarean Section", "Preterm Labor"],
    }
    department_stay = {
        "Cardiology": 5.0,
        "Orthopedics": 4.0,
        "Oncology": 6.5,
        "Emergency": 2.0,
        "Pediatrics": 2.5,
        "Neurology": 5.5,
        "General Medicine": 4.5,
        "Maternity": 3.0,
    }
    department_cost = {
        "Cardiology": 26_500.0,
        "Orthopedics": 31_000.0,
        "Oncology": 38_000.0,
        "Emergency": 9_500.0,
        "Pediatrics": 7_800.0,
        "Neurology": 24_000.0,
        "General Medicine": 12_500.0,
        "Maternity": 14_000.0,
    }

    departments = _pick(
        rng,
        list(department_diagnoses),
        [0.13, 0.11, 0.08, 0.24, 0.10, 0.09, 0.16, 0.09],
        size,
    )
    diagnoses = np.array(
        [rng.choice(department_diagnoses[department]) for department in departments],
        dtype=object,
    )
    admission_dates = _seasonal_dates(rng, "2024-01-01", "2026-06-30", size)
    stay_days = np.clip(
        np.round(rng.exponential(scale=_lookup(departments, department_stay))), 0, 60
    ).astype(int)
    discharge_dates = admission_dates + pd.to_timedelta(stay_days, unit="D")

    ages = np.where(
        departments == "Pediatrics",
        rng.integers(0, 18, size=size),
        np.where(
            departments == "Maternity",
            rng.integers(18, 45, size=size),
            np.clip(np.round(rng.normal(loc=58, scale=18, size=size)), 18, 98).astype(int),
        ),
    )
    charges = np.round(
        _lookup(departments, department_cost)
        * (0.55 + 0.15 * stay_days)
        * rng.lognormal(mean=0.0, sigma=0.19, size=size),
        2,
    )
    readmit_risk = 0.07 + (stay_days > 7) * 0.08 + (ages > 70) * 0.05
    satisfaction = np.clip(
        np.round(rng.normal(loc=4.1, scale=0.8, size=size) - (stay_days > 10) * 0.6), 1, 5
    )

    genders = _pick(rng, ["Female", "Male", "Other"], [0.505, 0.485, 0.01], size)
    genders = np.where(departments == "Maternity", "Female", genders)
    admission_types = np.where(
        departments == "Maternity",
        _pick(rng, ["Newborn", "Elective", "Urgent"], [0.55, 0.30, 0.15], size),
        np.where(
            departments == "Emergency",
            _pick(rng, ["Emergency", "Urgent"], [0.82, 0.18], size),
            _pick(rng, ["Elective", "Urgent", "Emergency"], [0.58, 0.27, 0.15], size),
        ),
    )

    frame = pd.DataFrame(
        {
            "EncounterID": [f"ENC-{number:07d}" for number in range(500_001, 500_001 + size)],
            "PatientID": [f"PT-{number:06d}" for number in rng.integers(1, 24_000, size=size)],
            "AdmissionDate": admission_dates,
            "DischargeDate": discharge_dates,
            "LengthOfStayDays": stay_days,
            "Department": departments,
            "PrimaryDiagnosis": diagnoses,
            "AdmissionType": admission_types,
            "PatientAge": ages,
            "Gender": genders,
            "InsuranceProvider": _pick(
                rng,
                ["Medicare", "Medicaid", "BlueShield", "UnitedCare", "Self-Pay", "Aetna"],
                [0.29, 0.14, 0.21, 0.18, 0.07, 0.11],
                size,
            ),
            "TotalChargesUSD": charges,
            "Readmitted30Days": np.where(rng.random(size) < readmit_risk, "Yes", "No"),
            "SatisfactionScore": satisfaction,
        }
    ).sort_values("AdmissionDate", kind="stable", ignore_index=True)

    frame["SatisfactionScore"] = _blank_out(rng, frame["SatisfactionScore"], 0.08)
    return frame


def build_banking_transactions() -> pd.DataFrame:
    rng = _rng(4)
    size = BANKING_ROWS
    account_count = 4_200

    account_numbers = rng.integers(1, account_count + 1, size=size)
    account_types = np.array(
        ["Checking", "Savings", "Credit Card", "Business"], dtype=object
    )[account_numbers % 4]
    customer_tiers = np.array(
        ["Standard", "Silver", "Gold", "Platinum"], dtype=object
    )[(account_numbers // 7) % 4]

    dates = _seasonal_dates(rng, "2025-01-01", "2026-06-30", size)
    timestamps = dates + pd.to_timedelta(
        rng.integers(8 * 3_600, 22 * 3_600, size=size), unit="s"
    )

    channels = _pick(
        rng,
        ["Mobile App", "Point of Sale", "Online Banking", "ATM", "Branch"],
        [0.34, 0.28, 0.19, 0.13, 0.06],
        size,
    )
    merchant_categories = _pick(
        rng,
        [
            "Groceries", "Restaurants", "Travel", "Fuel", "Utilities", "Healthcare",
            "Entertainment", "Retail", "Education",
        ],
        [0.21, 0.16, 0.08, 0.10, 0.09, 0.07, 0.08, 0.17, 0.04],
        size,
    )
    transaction_types = _pick(
        rng,
        ["Purchase", "Withdrawal", "Deposit", "Transfer", "Refund", "Fee"],
        [0.52, 0.13, 0.14, 0.13, 0.05, 0.03],
        size,
    )
    non_merchant_labels = {
        "Withdrawal": "Cash Withdrawal",
        "Deposit": "Deposit",
        "Transfer": "Account Transfer",
        "Fee": "Banking Services",
    }
    for transaction_type, label in non_merchant_labels.items():
        merchant_categories = np.where(
            transaction_types == transaction_type, label, merchant_categories
        )

    amounts = np.round(rng.lognormal(mean=3.85, sigma=1.15, size=size), 2)
    amounts = np.where(transaction_types == "Deposit", np.round(amounts * 3.2, 2), amounts)
    amounts = np.where(transaction_types == "Fee", np.round(rng.uniform(2, 45, size=size), 2), amounts)
    amounts = np.clip(amounts, 1.0, 90_000.0)

    credit = np.isin(transaction_types, ["Deposit", "Refund"])

    fraud_risk = (
        0.004
        + (amounts > 5_000) * 0.05
        + np.isin(merchant_categories, ["Travel", "Entertainment"]) * 0.008
    )

    frame = pd.DataFrame(
        {
            "TransactionID": [f"TXN-{number:08d}" for number in range(1, size + 1)],
            "TransactionDate": timestamps,
            "AccountID": [f"ACCT-{number:06d}" for number in account_numbers],
            "AccountType": account_types,
            "CustomerTier": customer_tiers,
            "BranchCity": _pick(
                rng,
                ["Chicago", "Dallas", "Denver", "Miami", "New York", "Phoenix", "Seattle"],
                [0.15, 0.14, 0.11, 0.13, 0.21, 0.12, 0.14],
                size,
            ),
            "Channel": channels,
            "MerchantCategory": merchant_categories,
            "TransactionType": transaction_types,
            "AmountUSD": amounts,
            "Direction": np.where(credit, "Credit", "Debit"),
            "IsFlaggedFraud": np.where(rng.random(size) < fraud_risk, "Yes", "No"),
        }
    ).sort_values(["AccountID", "TransactionDate"], kind="stable", ignore_index=True)

    opening_balance = np.round(rng.uniform(500, 25_000, size=account_count + 1), 2)
    account_index = frame["AccountID"].str.removeprefix("ACCT-").astype(int).to_numpy()
    deltas = np.where(
        frame["Direction"].to_numpy() == "Credit",
        frame["AmountUSD"].to_numpy(),
        -frame["AmountUSD"].to_numpy(),
    )
    running = pd.Series(deltas, index=frame.index).groupby(frame["AccountID"]).cumsum()
    frame["RunningBalanceUSD"] = np.round(
        opening_balance[account_index] + running.to_numpy(), 2
    )

    frame["MerchantCategory"] = _blank_out(rng, frame["MerchantCategory"], 0.02)
    return frame


DATASETS: dict[str, tuple[str, str]] = {
    "retail_sales_transactions": ("Retail sales orders", "Sales"),
    "hr_employee_directory": ("HR employee directory", "Employees"),
    "hospital_patient_encounters": ("Hospital patient encounters", "Encounters"),
    "banking_transactions": ("Retail banking transactions", "Transactions"),
}

BUILDERS = {
    "retail_sales_transactions": build_retail_sales,
    "hr_employee_directory": build_hr_directory,
    "hospital_patient_encounters": build_hospital_encounters,
    "banking_transactions": build_banking_transactions,
}


def write_excel(frame: pd.DataFrame, path: Path, sheet_name: str) -> None:
    with pd.ExcelWriter(
        path,
        engine="openpyxl",
        datetime_format="yyyy-mm-dd",
        date_format="yyyy-mm-dd",
    ) as writer:
        frame.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.sheets[sheet_name]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for position, column in enumerate(frame.columns, start=1):
            width = max(len(str(column)) + 4, 12)
            worksheet.column_dimensions[
                worksheet.cell(row=1, column=position).column_letter
            ].width = min(width, 26)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=["xlsx", "csv", "both"],
        default="xlsx",
        help="Output format for the generated datasets (default: xlsx).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory that receives the generated files (default: sample_data/).",
    )
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    for name, builder in BUILDERS.items():
        label, sheet_name = DATASETS[name]
        frame = builder()
        if arguments.format in {"xlsx", "both"}:
            path = arguments.output_dir / f"{name}.xlsx"
            write_excel(frame, path, sheet_name)
            print(f"{label}: {len(frame):,} rows -> {path}")
        if arguments.format in {"csv", "both"}:
            path = arguments.output_dir / f"{name}.csv"
            frame.to_csv(path, index=False)
            print(f"{label}: {len(frame):,} rows -> {path}")


if __name__ == "__main__":
    main()
