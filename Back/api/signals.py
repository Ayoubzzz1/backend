from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import Category, Department, Notification, Ticket, TicketComment
from .services import log_history, notify, notify_technicians


DEFAULT_DEPARTMENTS = [
    "HR",
    "IT",
    "Finance",
    "Production",
    "Directeur",
    "Commercial",
]

DEFAULT_CATEGORIES = [
    "IT / PC",
    "Réseau",
    "Imprimante",
    "Câbles / Connexion",
    "Email",
    "Compte / Accès",
    "Logiciel",
    "Téléphone",
    "Matériel",
    "Autre",
]


@receiver(post_migrate)
def seed_catalog(sender, **kwargs):
    if sender.name != "api":
        return
    for name in DEFAULT_DEPARTMENTS:
        Department.objects.update_or_create(name=name, defaults={"is_active": True})
    Department.objects.exclude(name__in=DEFAULT_DEPARTMENTS).update(is_active=False)
    for name in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})


@receiver(post_save, sender=Ticket)
def on_ticket_created(sender, instance, created, **kwargs):
    if not created:
        return
    log_history(instance, instance.created_by, "Ticket created", "", instance.display_number)
    notify(
        instance.created_by,
        f"Ticket {instance.display_number}",
        f"Votre ticket {instance.display_number} a été créé.",
        Notification.Type.TICKET_CREATED,
        instance,
    )
    if instance.assigned_technician_id:
        notify(
            instance.assigned_technician,
            f"Nouveau ticket {instance.display_number}",
            f"{instance.created_by} a créé le ticket {instance.display_number}: {instance.title}",
            Notification.Type.ASSIGNMENT,
            instance,
        )
    else:
        notify_technicians(
            f"Nouveau ticket {instance.display_number}",
            f"{instance.created_by} a créé le ticket {instance.display_number}: {instance.title}",
            Notification.Type.TICKET_CREATED,
            instance,
        )


@receiver(post_save, sender=TicketComment)
def on_comment(sender, instance, created, **kwargs):
    if not created:
        return
    ticket = instance.ticket
    log_history(ticket, instance.author, "Comment added", "", instance.message[:80])
    recipients = {ticket.created_by_id}
    if ticket.assigned_technician_id:
        recipients.add(ticket.assigned_technician_id)
    recipients.discard(instance.author_id)
    from .models import User

    for uid in recipients:
        user = User.objects.filter(pk=uid).first()
        notify(
            user,
            f"Nouveau commentaire {ticket.display_number}",
            f"Nouveau commentaire sur le ticket {ticket.display_number}.",
            Notification.Type.COMMENT,
            ticket,
        )
