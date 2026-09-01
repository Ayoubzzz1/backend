from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .models import Attendance, EmployeeRequest, Notification
from .permissions import IsAuthenticatedActive, IsHROrAdmin
from .serializers import AttendanceSerializer, EmployeeRequestSerializer
from .services import notify

User = get_user_model()
DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def staff_users():
    return User.objects.filter(role__in=[User.Role.HR, User.Role.SUPERADMIN], is_active=True)


class AttendanceViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticatedActive]

    def get_queryset(self):
        user = self.request.user
        qs = Attendance.objects.select_related("user")
        if user.role in (User.Role.HR, User.Role.SUPERADMIN):
            emp = self.request.query_params.get("user")
            if emp:
                qs = qs.filter(user_id=emp)
            return qs
        return qs.filter(user=user)

    def create(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.HR, User.Role.SUPERADMIN):
            return Response({"detail": "Seul RH/Admin peut modifier les présences."}, status=403)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.HR, User.Role.SUPERADMIN):
            return Response({"detail": "Seul RH/Admin peut modifier les présences."}, status=403)
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        today = date.today()
        try:
            year = int(request.query_params.get("year") or today.year)
            month = int(request.query_params.get("month") or today.month)
        except ValueError:
            return Response({"detail": "Mois/année invalides."}, status=400)
        target = request.user
        if request.user.role in (User.Role.HR, User.Role.SUPERADMIN) and request.query_params.get("user"):
            target = User.objects.filter(pk=request.query_params.get("user")).first() or request.user
        elif request.user.role not in (User.Role.HR, User.Role.SUPERADMIN):
            target = request.user
        start = date(year, month, 1)
        nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        records = {
            a.date: a
            for a in Attendance.objects.filter(user=target, date__gte=start, date__lt=nxt)
        }
        days = []
        d = start
        while d < nxt:
            rec = records.get(d)
            weekend = d.weekday() >= 5
            if rec:
                presence = rec.presence
                note = rec.note
            elif weekend:
                presence = Attendance.Presence.WEEKEND
                note = ""
            else:
                presence = ""
                note = ""
            days.append(
                {
                    "date": d.isoformat(),
                    "weekday": DAYS_FR[d.weekday()],
                    "presence": presence,
                    "presence_label": dict(Attendance.Presence.choices).get(presence, "Non renseigné"),
                    "note": note,
                    "id": rec.id if rec else None,
                }
            )
            d += timedelta(days=1)
        return Response({"year": year, "month": month, "user": target.id, "days": days})


class EmployeeRequestViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeRequestSerializer
    permission_classes = [IsAuthenticatedActive]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = EmployeeRequest.objects.select_related("created_by", "created_by__department", "reviewed_by")
        if user.role in (User.Role.HR, User.Role.SUPERADMIN):
            kind = self.request.query_params.get("kind")
            if kind:
                qs = qs.filter(kind=kind)
            st = self.request.query_params.get("status")
            if st:
                qs = qs.filter(status=st)
            return qs
        qs = qs.filter(created_by=user)
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        st = self.request.query_params.get("status")
        if st == "done":
            qs = qs.filter(status__in=[EmployeeRequest.Status.APPROVED, EmployeeRequest.Status.REJECTED])
        elif st:
            qs = qs.filter(status=st)
        return qs

    def perform_create(self, serializer):
        req = serializer.save(created_by=self.request.user, status=EmployeeRequest.Status.PENDING)
        for staff in staff_users():
            notify(
                staff,
                f"Nouvelle demande {req.display_number}",
                f"{req.created_by} a soumis {req.get_kind_display()}.",
                Notification.Type.REQUEST,
            )

    def partial_update(self, request, *args, **kwargs):
        req = self.get_object()
        if request.user.role not in (User.Role.HR, User.Role.SUPERADMIN):
            return Response({"detail": "Vous ne pouvez pas modifier le statut de cette demande."}, status=403)
        new_status = request.data.get("status")
        comment = request.data.get("admin_comment")
        if new_status and new_status not in (
            EmployeeRequest.Status.APPROVED,
            EmployeeRequest.Status.REJECTED,
            EmployeeRequest.Status.PENDING,
        ):
            return Response({"detail": "Statut invalide."}, status=400)
        if new_status:
            req.status = new_status
            req.reviewed_by = request.user
            req.reviewed_at = timezone.now()
        if comment is not None:
            req.admin_comment = comment
        req.save()
        notify(
            req.created_by,
            f"Demande {req.display_number}",
            f"Votre demande est maintenant {req.get_status_display()}.",
            Notification.Type.REQUEST,
        )
        return Response(EmployeeRequestSerializer(req).data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedActive])
def my_employee_requests(request):
    qs = EmployeeRequest.objects.filter(created_by=request.user).select_related(
        "created_by", "created_by__department", "reviewed_by"
    )
    st = request.query_params.get("status")
    if st == "done":
        qs = qs.filter(status__in=[EmployeeRequest.Status.APPROVED, EmployeeRequest.Status.REJECTED])
    elif st:
        qs = qs.filter(status=st)
    else:
        qs = qs.filter(status=EmployeeRequest.Status.PENDING)
    return Response(EmployeeRequestSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedActive])
def dashboard_hr(request):
    if request.user.role not in (User.Role.HR, User.Role.SUPERADMIN):
        return Response({"detail": "Accès réservé au RH."}, status=403)
    qs = EmployeeRequest.objects.all()
    return Response(
        {
            "pending": qs.filter(status=EmployeeRequest.Status.PENDING).count(),
            "approved": qs.filter(status=EmployeeRequest.Status.APPROVED).count(),
            "rejected": qs.filter(status=EmployeeRequest.Status.REJECTED).count(),
            "leave": qs.filter(kind=EmployeeRequest.Kind.LEAVE, status=EmployeeRequest.Status.PENDING).count(),
            "advance": qs.filter(kind=EmployeeRequest.Kind.ADVANCE, status=EmployeeRequest.Status.PENDING).count(),
            "recent": EmployeeRequestSerializer(qs.order_by("-created_at")[:12], many=True).data,
        }
    )
