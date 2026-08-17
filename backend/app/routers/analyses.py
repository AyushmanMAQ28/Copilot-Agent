import csv
import io
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Analysis
from ..schemas import AnalysisIn, AnalysisOut
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


@router.post("", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def create_analysis(project_id: str, payload: AnalysisIn, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    dataset = dataset_or_404(project_id, payload.dataset_id, db)
    loaded = load_csv(dataset.content.encode(), dataset.filename, len(dataset.content.encode()) + 1, dataset.row_count + 1)
    profile = json.loads(dataset.profile_json)
    try:
        chart = execute_chart_spec(loaded.rows, loaded.headers, payload.chart.model_dump()) if payload.chart else None
    except ChartSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    analysis = Analysis(project_id=project_id, dataset_id=dataset.id, prompt=payload.prompt,
                        result_json=json.dumps(analyze(payload.prompt, profile, loaded.headers, loaded.rows)),
                        chart_spec_json=json.dumps(chart) if chart else None)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return serialize(analysis)
