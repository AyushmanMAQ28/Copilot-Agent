import json
from typing import Any

import pandas as pd
from openai import OpenAI

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def _number(value: Any) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def deterministic_analysis(frame: pd.DataFrame, prompt: str) -> dict[str, Any]:
    numeric_columns = list(frame.select_dtypes(include="number").columns)
    missing = int(frame.isna().sum().sum())
    insights = [
        f"The file contains {len(frame):,} rows and {len(frame.columns):,} columns.",
        (
            f"{missing:,} values are missing across the dataset."
            if missing
            else "The dataset has no missing values."
        ),
    ]

    if numeric_columns:
        column = numeric_columns[0]
        series = frame[column].dropna()
        if not series.empty:
            insights.append(
                f"{column} ranges from {_number(series.min())} to "
                f"{_number(series.max())}, with an average of {_number(series.mean())}."
            )

    category_column = next(
        (column for column in frame.columns if column not in numeric_columns),
        frame.columns[0],
    )
    if numeric_columns:
        value_column = numeric_columns[0]
        chart_frame = (
            frame.groupby(category_column, dropna=False)[value_column]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
    else:
        value_column = "Count"
        chart_frame = (
            frame[category_column]
            .fillna("Missing")
            .value_counts()
            .head(10)
            .rename_axis(category_column)
            .reset_index(name=value_column)
        )

    chart_data = [
        {
            category_column: str(row[category_column]),
            value_column: _number(row[value_column]),
        }
        for row in chart_frame.to_dict(orient="records")
    ]
    focus = f' based on "{prompt.strip()}"' if prompt.strip() else ""
    return {
        "insights": insights,
        "chart": {
            "title": f"{value_column} by {category_column}",
            "category_key": category_column,
            "value_key": value_column,
            "data": chart_data,
        },
        "next_steps": [
            f"Review the highest {category_column} group{focus}.",
            "Investigate missing or unexpected values.",
            "Compare the leading groups with the overall average.",
        ],
        "source": "pandas",
    }


def analyze_frame(frame: pd.DataFrame, prompt: str) -> dict[str, Any]:
    fallback = deterministic_analysis(frame, prompt)
    if not LLM_API_KEY or LLM_API_KEY == "sk-your-key-here":
        return fallback

    summary = {
        "question": prompt,
        "columns": list(frame.columns),
        "rows": len(frame),
        "sample": frame.head(5).fillna("").to_dict(orient="records"),
        "statistics": frame.describe(include="all").fillna("").to_dict(),
    }
    try:
        client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return JSON with arrays named insights and next_steps. "
                        "Use concise, factual statements based only on the CSV summary."
                    ),
                },
                {"role": "user", "content": json.dumps(summary, default=str)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        generated = json.loads(content)
        if generated.get("insights"):
            fallback["insights"] = generated["insights"]
        if generated.get("next_steps"):
            fallback["next_steps"] = generated["next_steps"]
        fallback["source"] = "llm"
    except Exception:
        pass
    return fallback

