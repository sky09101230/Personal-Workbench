from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/tasks")


@router.get("/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, object]:
    task = request.app.state.task_repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    return {
        "id": task.id, "operation": task.operation, "status": task.status.value,
        "created_at": task.created_at.isoformat(), "updated_at": task.updated_at.isoformat(),
        "error_code": task.error_code, "result_ref": task.result_ref,
    }
