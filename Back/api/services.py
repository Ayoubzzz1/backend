from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import Notification, Ticket, TicketHistory, User

# Workflow:
#   NEW -> IN_PROGRESS (assigned IT or superadmin only)
#   IN_PROGRESS -> DONE (requester or superadmin only)
TRANSITIONS = {
    Ticket.Status.NEW: {Ticket.Status.IN_PROGRESS},
    Ticket.Status.IN_PROGRESS: {Ticket.Status.DONE},
}


def next_ticket_number():
    last = Ticket.objects.order_by("-id").values_list("id", flat=True).first()
    n = (last or 0) + 1
    return f"{n:06d}"


def log_history(ticket, actor, action, old_value="", new_value=""):
    TicketHistory.objects.create(
        ticket=ticket,
        actor=actor,
        action=action,
        old_value=old_value or "",
        new_value=new_value or "",
    )


def notify(user, title, message, ntype, ticket=None):
    if not user:
        return
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        type=ntype,
        related_ticket=ticket,
    )


def notify_technicians(title, message, ntype, ticket=None):
    techs = User.objects.filter(role=User.Role.TECHNICIAN, is_active=True)
    for tech in techs:
        notify(tech, title, message, ntype, ticket)


def calculate_duration(started_at, ended_at):
    """Calculate intervention duration in hours and minutes"""
    if not started_at or not ended_at:
        return ""
    seconds = max(0, int((ended_at - started_at).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def apply_status(ticket, new_status, actor):
    old = ticket.status
    if old == new_status:
        return ticket
    allowed = TRANSITIONS.get(old, set())
    if new_status not in allowed:
        raise ValidationError(f"Transition invalide: {old} → {new_status}.")

    role = getattr(actor, "role", None)
    is_owner = getattr(actor, "id", None) == ticket.created_by_id
    is_admin = role == User.Role.SUPERADMIN
    is_technician = role == User.Role.TECHNICIAN

    def ensure_assigned_technician():
        if is_admin:
            return
        if not is_technician:
            raise PermissionDenied("Seul l'IT assigné peut modifier le statut.")
        if ticket.assigned_technician_id and ticket.assigned_technician_id != actor.id:
            raise PermissionDenied("Ce ticket est assigné à un autre technicien.")
        if ticket.assigned_technician_id is None:
            ticket.assigned_technician = actor

    if new_status == Ticket.Status.IN_PROGRESS and old == Ticket.Status.NEW:
        ensure_assigned_technician()
        if not ticket.started_at:
            ticket.started_at = timezone.now()
        log_history(ticket, actor, "Intervention démarrée", old, new_status)
    elif new_status == Ticket.Status.DONE and old == Ticket.Status.IN_PROGRESS:
        if not (is_owner or is_admin):
            raise PermissionDenied("Seul le demandeur peut marquer le ticket comme terminé.")
        ticket.resolved_at = timezone.now()
        ticket.closed_at = timezone.now()
        ticket.intervention_duration = calculate_duration(ticket.started_at, ticket.resolved_at)
        log_history(ticket, actor, "Ticket clôturé par le demandeur", old, new_status)
    else:
        log_history(ticket, actor, "Statut changé", old, new_status)

    ticket.status = new_status
    ticket.save()

    num = ticket.display_number
    if ticket.created_by_id != getattr(actor, "id", None):
        notify(
            ticket.created_by,
            f"Ticket {num}",
            f"Votre ticket {num} est maintenant {ticket.get_status_display()}.",
            Notification.Type.STATUS,
            ticket,
        )
    if new_status == Ticket.Status.DONE and ticket.assigned_technician_id and ticket.assigned_technician_id != getattr(actor, "id", None):
        notify(
            ticket.assigned_technician,
            f"Ticket {num} terminé",
            f"{ticket.created_by} a marqué le ticket {num} comme terminé.",
            Notification.Type.RESOLUTION,
            ticket,
        )
    return ticket
