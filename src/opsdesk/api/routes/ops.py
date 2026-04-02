from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...connectors import ConnectorRegistry
from ...schemas import ApprovalExpiryScanItemResponse, ApprovalExpiryScanResponse, ApprovalReminderScanItemResponse, ApprovalReminderScanResponse, ConnectorDescriptorResponse, ConnectorInventoryResponse, SlaScanItemResponse, SlaScanResponse
from ...workers import SchedulerWorker
from ..deps import get_connector_registry, get_scheduler_worker

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/connectors", response_model=ConnectorInventoryResponse)
def list_connectors(
    connector_registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorInventoryResponse:
    return ConnectorInventoryResponse(
        items=[ConnectorDescriptorResponse(**item) for item in connector_registry.list_connectors()],
    )


@router.post("/sla/scan", response_model=SlaScanResponse)
def run_sla_scan(
    limit: int = Query(default=100, ge=1, le=500),
    scheduler_worker: SchedulerWorker = Depends(get_scheduler_worker),
) -> SlaScanResponse:
    result = scheduler_worker.run_sla_scan(limit=limit)
    return SlaScanResponse(
        scanned_count=result["scanned_count"],
        updated_count=result["updated_count"],
        escalated_count=result["escalated_count"],
        items=[SlaScanItemResponse(**item) for item in result["items"]],
    )


@router.post("/approvals/expire", response_model=ApprovalExpiryScanResponse)
def run_approval_expiry_scan(
    limit: int = Query(default=100, ge=1, le=500),
    scheduler_worker: SchedulerWorker = Depends(get_scheduler_worker),
) -> ApprovalExpiryScanResponse:
    result = scheduler_worker.run_approval_expiry_scan(limit=limit)
    return ApprovalExpiryScanResponse(
        scanned_count=result["scanned_count"],
        expired_count=result["expired_count"],
        items=[ApprovalExpiryScanItemResponse(**item) for item in result["items"]],
    )


@router.post("/approvals/remind", response_model=ApprovalReminderScanResponse)
def run_approval_reminder_scan(
    limit: int = Query(default=100, ge=1, le=500),
    scheduler_worker: SchedulerWorker = Depends(get_scheduler_worker),
) -> ApprovalReminderScanResponse:
    result = scheduler_worker.run_approval_reminder_scan(limit=limit)
    return ApprovalReminderScanResponse(
        scanned_count=result["scanned_count"],
        reminded_count=result["reminded_count"],
        items=[ApprovalReminderScanItemResponse(**item) for item in result["items"]],
    )
