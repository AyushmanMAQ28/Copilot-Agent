import csv
import io
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Analysis
from .datasets import dataset_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["exports"])


@router.get("/datasets/{dataset_id}/export")
def export_dataset(project_id: str, dataset_id: str, format: str = "csv", db: Session = Depends(get_db)):
    dataset = dataset_or_404(project_id, dataset_id, db)
    if format == "csv":
        safe_name = "".join(char if char.isalnum() or char in "._-" else "_" for char in dataset.filename)
        return Response(dataset.content, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'})
    if format == "json":
        return Response(json.dumps({"filename": dataset.filename, "profile": json.loads(dataset.profile_json)}),
                        media_type="application/json")
    raise HTTPException(status_code=422, detail="format must be csv or json")


@router.get("/analyses/{analysis_id}/export")
def export_analysis(project_id: str, analysis_id: str, db: Session = Depends(get_db)):
    analysis = db.get(Analysis, analysis_id)
    if not analysis or analysis.project_id != project_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    payload = {"id": analysis.id, "prompt": analysis.prompt, "result": json.loads(analysis.result_json),
               "chart_spec": json.loads(analysis.chart_spec_json) if analysis.chart_spec_json else None}
    return Response(json.dumps(payload), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="analysis-{analysis.id}.json"'})
