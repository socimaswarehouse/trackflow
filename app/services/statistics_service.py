"""Statistics and analytics service for approval tracking."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.approver import Approver
from app.models.document import Document


def get_approval_statistics(db: Session) -> dict:
    """Get detailed statistics grouped by approver (QR code).
    
    Returns statistics including:
    - Total submissions per approver
    - Status breakdown per approver
    - Approval rates
    """
    approvers = db.query(Approver).all()
    
    stats = {
        "by_approver": {},
        "total_submissions": 0,
        "total_approved": 0,
        "total_pending": 0,
        "total_rejected": 0,
        "approval_rate": 0.0,
    }
    
    for approver in approvers:
        approver_docs = (
            db.query(Document)
            .filter(Document.approver_id == approver.id)
            .all()
        )
        
        if not approver_docs:
            continue
        
        total = len(approver_docs)
        approved = sum(1 for d in approver_docs if d.status in ("APPROVED", "COMPLETED"))
        pending = sum(1 for d in approver_docs if d.status in ("SUBMITTED", "PENDING"))
        rejected = sum(1 for d in approver_docs if d.status == "REJECTED")
        
        stats["by_approver"][approver.slug] = {
            "name": approver.approval_name,
            "department": approver.department or "N/A",
            "total": total,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "approval_rate": round((approved / total * 100) if total > 0 else 0, 1),
        }
        
        stats["total_submissions"] += total
        stats["total_approved"] += approved
        stats["total_pending"] += pending
        stats["total_rejected"] += rejected
    
    if stats["total_submissions"] > 0:
        stats["approval_rate"] = round(
            (stats["total_approved"] / stats["total_submissions"] * 100), 1
        )
    
    return stats


def get_chart_data_for_approvers(db: Session) -> dict:
    """Get chart-ready data for approver statistics visualization."""
    stats = get_approval_statistics(db)
    
    if not stats["by_approver"]:
        return {
            "labels": [],
            "datasets": {
                "approved": [],
                "pending": [],
                "rejected": [],
            }
        }
    
    labels = [info["name"] for info in stats["by_approver"].values()]
    approved_data = [info["approved"] for info in stats["by_approver"].values()]
    pending_data = [info["pending"] for info in stats["by_approver"].values()]
    rejected_data = [info["rejected"] for info in stats["by_approver"].values()]
    
    return {
        "labels": labels,
        "datasets": {
            "approved": approved_data,
            "pending": pending_data,
            "rejected": rejected_data,
        }
    }
