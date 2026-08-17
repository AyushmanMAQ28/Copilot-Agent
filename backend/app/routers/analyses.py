import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Analysis
from ..schemas import AnalysisIn, AnalysisOut
from ..services import dataset_store, qa_analysis
from ..services.analyzer import analyze
from ..services.chart_builder import ChartSpecError, execute_chart_spec
from ..services.csv_loader import load_csv
from .datasets import dataset_or_404
from .projects import project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/analyses", tags=["analyses"])


def serialize(analysis: Analysis) -> AnalysisOut:
    return AnalysisOut(id=analysis.id, project_id=analysis.project_id, dataset_id=analysis.dataset_id,
                       prompt=analysis.prompt, result=json.loads(analysis.result_json),
                       chart_spec=json.loads(analysis.chart_spec_json) if analysis.chart_spec_json else None,
                       status=analysis.status, created_at=analysis.created_at)


@router.get("", response_model=list[AnalysisOut])
def list_analyses(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    return [serialize(item) for item in db.query(Analysis).filter_by(project_id=project_id).order_by(Analysis.created_at.desc())]


def _duckdb_chart(dataset, payload: AnalysisIn) -> dict:
    """Build the requested chart with a single DuckDB aggregation."""
    request = payload.chart.model_dump() if payload.chart else {}
    points = dataset_store.aggregate(dataset.storage_path or "", x=request["x"], y=request.get("y"),
                                     aggregation=request.get("aggregation", "count"),
                                     limit=request.get("limit", 25))
    return {"chart_type": request.get("chart_type", "bar"), "x": request["x"], "y": request.get("y"),
            "aggregation": request.get("aggregation", "count"), "data": points}


@router.post("", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def create_analysis(project_id: str, payload: AnalysisIn, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    dataset = dataset_or_404(project_id, payload.dataset_id, db)
    profile = json.loads(dataset.profile_json)
    try:
        if dataset.storage_path:
            chart = _duckdb_chart(dataset, payload) if payload.chart else None
            result = qa_analysis.analyze_dataset(payload.prompt, dataset, profile)
        else:
            stored_bytes = (dataset.content or "").encode()
            loaded = load_csv(stored_bytes, dataset.filename, len(stored_bytes) + 1, dataset.row_count + 1)
            chart = execute_chart_spec(loaded.rows, loaded.headers, payload.chart.model_dump()) if payload.chart else None
            result = analyze(payload.prompt, profile, loaded.headers, loaded.rows)
    except (ChartSpecError, dataset_store.DatasetError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    analysis = Analysis(project_id=project_id, dataset_id=dataset.id, prompt=payload.prompt,
                        result_json=json.dumps(result),
                        chart_spec_json=json.dumps(chart) if chart else None)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return serialize(analysis)
