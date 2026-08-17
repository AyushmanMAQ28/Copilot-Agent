import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Analysis
from ..services import dataset_store
from .datasets import dataset_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["exports"])


@router.get("/datasets/{dataset_id}/export")
def export_dataset(project_id: str, dataset_id: str, format: str = "csv", db: Session = Depends(get_db)):
    dataset = dataset_or_404(project_id, dataset_id, db)
    if format == "csv":
        stem = "".join(char if char.isalnum() or char in "._-" else "_" for char in dataset.filename)
        safe_name = stem.rsplit(".", 1)[0] + ".csv" if "." in stem else stem + ".csv"
        headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
        if dataset.storage_path:
            try:
                stream = dataset_store.iter_csv(dataset.storage_path)
            except dataset_store.DatasetError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)
        return Response(dataset.content or "", media_type="text/csv; charset=utf-8", headers=headers)
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
