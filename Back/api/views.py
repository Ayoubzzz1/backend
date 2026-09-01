from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Category, Department, Notification, Ticket, User
from .permissions import (
    IsAuthenticatedActive,
    IsITGuy,
    IsRegularUser,
    IsSuperAdmin,
    IsTechnicianOrSuperAdmin,
    PublicReadActiveCatalog,
)
from .serializers import (
    AdminUserSerializer,
    CategorySerializer,
    DepartmentSerializer,
    MeSerializer,
    NotificationSerializer,
    RegisterSerializer,
    TicketAttachmentSerializer,
    TicketCommentSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketHistorySerializer,
    TicketListSerializer,
    TicketUpdateSerializer,
    UserPublicSerializer,
)
from .services import apply_status, log_history, notify

UserModel = get_user_model()


def ticket_base_qs():
    return Ticket.objects.select_related(
        "category",
        "created_by",
        "created_by__department",
        "related_user",
        "it_service",
        "assigned_technician",
    ).prefetch_related("comments", "attachments", "history")


def apply_ticket_query_filters(qs, request):
    search = request.query_params.get("search")
    if search:
        qs = qs.filter(
            Q(ticket_number__icontains=search.replace("#", ""))
            | Q(title__icontains=search)
            | Q(description__icontains=search)
        )
    for field in ("status", "priority", "category"):
        value = request.query_params.get(field)
        if value:
            qs = qs.filter(**{field: value})
    technician = request.query_params.get("technician")
    if technician:
        qs = qs.filter(assigned_technician_id=technician)
    department = request.query_params.get("department")
    if department:
        qs = qs.filter(it_service_id=department)
    return qs


def visible_tickets_for(user):
    """Tickets a user may retrieve (detail), not the IT inbox list."""
    qs = ticket_base_qs()
    if user.role == User.Role.SUPERADMIN:
        return qs
    if user.role == User.Role.TECHNICIAN:
        return qs.filter(assigned_technician=user)
    return qs.filter(created_by=user)


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": MeSerializer(user).data,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    return Response(
        {"detail": "L'inscription publique est désactivée. Un administrateur doit créer votre compte."},
        status=403,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    ident = (request.data.get("email") or request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    user = UserModel.objects.filter(email__iexact=ident).first()
    if not user and ident:
        user = UserModel.objects.filter(login_name__iexact=ident).first()
    if not user or not user.is_active or not user.check_password(password):
        return Response({"detail": "Identifiant ou mot de passe incorrect."}, status=400)
    if user.role not in (User.Role.SUPERADMIN, User.Role.HR):
        user.save()
        user.refresh_from_db()
    return Response(tokens_for(user))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "GET":
        if request.user.role != User.Role.SUPERADMIN:
            request.user.save()
            request.user.refresh_from_db()
        return Response(MeSerializer(request.user).data)
    serializer = MeSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [PublicReadActiveCatalog]

    def get_queryset(self):
        qs = Department.objects.all()
        if not (self.request.user.is_authenticated and self.request.user.role == User.Role.SUPERADMIN):
            qs = qs.filter(is_active=True)
        return qs


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [PublicReadActiveCatalog]

    def get_queryset(self):
        qs = Category.objects.all()
        if not (self.request.user.is_authenticated and self.request.user.role == User.Role.SUPERADMIN):
            qs = qs.filter(is_active=True)
        return qs


class TicketViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedActive]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action == "list":
            return [IsITGuy()]
        return [IsAuthenticatedActive()]

    def get_queryset(self):
        return apply_ticket_query_filters(visible_tickets_for(self.request.user), self.request)

    def list(self, request, *args, **kwargs):
        """IT inbox: assigned tickets only. Regular users must use /my-requests/."""
        user = request.user
        if user.role == User.Role.SUPERADMIN:
            qs = apply_ticket_query_filters(ticket_base_qs(), request)
        else:
            qs = apply_ticket_query_filters(ticket_base_qs().filter(assigned_technician=user), request)
        if not request.query_params.get("status"):
            qs = qs.exclude(status=Ticket.Status.DONE)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = TicketListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(TicketListSerializer(qs, many=True).data)

    def get_serializer_class(self):
        if self.action == "create":
            return TicketCreateSerializer
        if self.action in ("update", "partial_update"):
            return TicketUpdateSerializer
        if self.action == "retrieve":
            return TicketDetailSerializer
        return TicketListSerializer

    def create(self, request, *args, **kwargs):
        if request.user.role == User.Role.TECHNICIAN:
            return Response(
                {"detail": "L'espace IT reçoit les tickets. La création est réservée aux autres services."},
                status=403,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data, status=201)

    @action(detail=False, methods=["get"], url_path="history")
    def completed_list(self, request):
        user = request.user
        qs = ticket_base_qs().filter(status=Ticket.Status.DONE)
        if user.role == User.Role.USER:
            qs = qs.filter(created_by=user)
        elif user.role == User.Role.TECHNICIAN:
            qs = qs.filter(assigned_technician=user)
        qs = apply_ticket_query_filters(qs, request)
        return Response(TicketListSerializer(qs, many=True).data)

    def partial_update(self, request, *args, **kwargs):
        ticket = self.get_object()
        user = request.user
        serializer = TicketUpdateSerializer(ticket, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "status" in data:
            try:
                apply_status(ticket, data["status"], user)
            except ValidationError as exc:
                return Response({"detail": exc.messages[0] if exc.messages else str(exc)}, status=400)
            except PermissionDenied as exc:
                return Response({"detail": str(exc)}, status=403)

        if user.role == User.Role.USER:
            ticket.refresh_from_db()
            return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

        if "priority" in data and data["priority"] != ticket.priority:
            old = ticket.priority
            ticket.priority = data["priority"]
            ticket.save(update_fields=["priority", "updated_at"])
            log_history(ticket, user, "Priority changed", old, ticket.priority)
        if "work_notes" in data and data["work_notes"] != ticket.work_notes:
            ticket.work_notes = data["work_notes"]
            ticket.save(update_fields=["work_notes", "updated_at"])
            log_history(ticket, user, "Work notes updated")
        if "resolution_info" in data and data["resolution_info"] != ticket.resolution_info:
            ticket.resolution_info = data["resolution_info"]
            ticket.save(update_fields=["resolution_info", "updated_at"])
            log_history(ticket, user, "Resolution information updated")
        if "description" in data and data["description"] != ticket.description:
            old = ticket.description[:80]
            ticket.description = data["description"]
            ticket.save(update_fields=["description", "updated_at"])
            log_history(ticket, user, "Description updated", old, ticket.description[:80])
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        user = request.user
        if user.role not in (User.Role.TECHNICIAN, User.Role.SUPERADMIN):
            return Response({"detail": "Action non autorisée."}, status=403)
        if user.role == User.Role.TECHNICIAN and ticket.assigned_technician_id not in (None, user.id):
            return Response({"detail": "Ce ticket est assigné à un autre technicien."}, status=403)
        tech_id = request.data.get("technician_id")
        if tech_id:
            if user.role != User.Role.SUPERADMIN and str(tech_id) != str(user.id):
                return Response({"detail": "Vous ne pouvez assigner qu'à vous-même."}, status=403)
            technician = UserModel.objects.filter(pk=tech_id, role=User.Role.TECHNICIAN, is_active=True).first()
        else:
            if user.role != User.Role.TECHNICIAN:
                return Response({"detail": "technician_id requis."}, status=400)
            technician = user
        if not technician:
            return Response({"detail": "Technicien introuvable."}, status=400)
        old = ticket.assigned_technician.full_name if ticket.assigned_technician else ""
        ticket.assigned_technician = technician
        ticket.save(update_fields=["assigned_technician", "updated_at"])
        log_history(ticket, user, "Technician assigned", old, technician.full_name)
        notify(
            ticket.created_by,
            f"Ticket {ticket.display_number}",
            f"Votre ticket {ticket.display_number} a été pris en charge par {technician.full_name}.",
            Notification.Type.ASSIGNMENT,
            ticket,
        )
        if technician.id != user.id:
            notify(
                technician,
                f"Ticket {ticket.display_number} assigné",
                f"Le ticket {ticket.display_number} vous a été assigné.",
                Notification.Type.ASSIGNMENT,
                ticket,
            )
        if ticket.status == Ticket.Status.NEW:
            try:
                apply_status(ticket, Ticket.Status.IN_PROGRESS, user)
            except (ValidationError, PermissionDenied):
                pass
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        ticket = self.get_object()
        try:
            apply_status(ticket, Ticket.Status.IN_PROGRESS, request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0] if getattr(exc, "messages", None) else str(exc)}, status=400)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=403)
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        ticket = self.get_object()
        info = request.data.get("resolution_info")
        if info is not None:
            ticket.resolution_info = info
            ticket.save(update_fields=["resolution_info", "updated_at"])
            log_history(ticket, request.user, "Resolution information updated", "", str(info)[:80])
        try:
            apply_status(ticket, Ticket.Status.RESOLVED, request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0] if getattr(exc, "messages", None) else str(exc)}, status=400)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=403)
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="confirm-resolution")
    def confirm_resolution(self, request, pk=None):
        ticket = self.get_object()
        if ticket.created_by_id != request.user.id:
            return Response({"detail": "Seul le demandeur peut confirmer."}, status=403)
        if ticket.status != Ticket.Status.RESOLVED:
            return Response({"detail": "Ce ticket n'est pas en attente de confirmation."}, status=400)
        confirmed = request.data.get("confirmed")
        try:
            if confirmed in (True, "true", "1", 1):
                apply_status(ticket, Ticket.Status.DONE, request.user)
            else:
                apply_status(ticket, Ticket.Status.IN_PROGRESS, request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0] if exc.messages else str(exc)}, status=400)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=403)
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "GET":
            return Response(TicketCommentSerializer(ticket.comments.all(), many=True).data)
        serializer = TicketCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(ticket=ticket, author=request.user)
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data, status=201)

    @action(detail=True, methods=["get", "post"])
    def attachments(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "GET":
            return Response(
                TicketAttachmentSerializer(ticket.attachments.all(), many=True, context={"request": request}).data
            )
        serializer = TicketAttachmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(ticket=ticket, uploaded_by=request.user)
        ticket.refresh_from_db()
        return Response(TicketDetailSerializer(ticket, context={"request": request}).data, status=201)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        ticket = self.get_object()
        return Response(TicketHistorySerializer(ticket.history.all(), many=True).data)


class NotificationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticatedActive]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.save(update_fields=["is_read"])
        return Response(self.get_serializer(n).data)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({"ok": True})


class AdminUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsSuperAdmin]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = UserModel.objects.select_related("department")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs


class TechnicianListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserPublicSerializer
    permission_classes = [IsTechnicianOrSuperAdmin]

    def get_queryset(self):
        return UserModel.objects.filter(role=User.Role.TECHNICIAN, is_active=True)


@api_view(["GET"])
@permission_classes([IsAuthenticatedActive])
def directory(request):
    qs = UserModel.objects.filter(is_active=True).select_related("department")
    department = request.query_params.get("department")
    if department:
        qs = qs.filter(department_id=department)
    return Response(UserPublicSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedActive])
def dashboard_user(request):
    user = request.user
    qs = Ticket.objects.filter(created_by=user).select_related(
        "category", "created_by", "it_service", "assigned_technician"
    )
    return Response(
        {
            "open": qs.exclude(status=Ticket.Status.DONE).count(),
            "in_progress": qs.filter(status=Ticket.Status.IN_PROGRESS).count(),
            "resolved": qs.filter(status=Ticket.Status.DONE).count(),
            "closed": qs.filter(status=Ticket.Status.DONE).count(),
            "recent": TicketListSerializer(qs.order_by("-created_at")[:8], many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsTechnicianOrSuperAdmin])
def dashboard_it(request):
    user = request.user
    if user.role == User.Role.SUPERADMIN:
        qs = Ticket.objects.all()
    else:
        qs = Ticket.objects.filter(assigned_technician=user)
    qs = qs.select_related("category", "created_by", "it_service", "assigned_technician")
    mine = qs.filter(assigned_technician=user)
    return Response(
        {
            "total": qs.exclude(status=Ticket.Status.DONE).count(),
            "new": qs.filter(status=Ticket.Status.NEW).count(),
            "in_progress": qs.filter(status=Ticket.Status.IN_PROGRESS).count(),
            "waiting": 0,
            "urgent": qs.filter(priority=Ticket.Priority.CRITICAL).exclude(status=Ticket.Status.DONE).count(),
            "resolved": qs.filter(status=Ticket.Status.DONE).count(),
            "my_tickets": mine.exclude(status=Ticket.Status.DONE).count(),
            "recent": TicketListSerializer(
                qs.exclude(status=Ticket.Status.DONE).order_by("-created_at")[:12], many=True
            ).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def dashboard_admin(request):
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Response(
        {
            "total_users": UserModel.objects.filter(is_active=True).count(),
            "technicians": UserModel.objects.filter(role=User.Role.TECHNICIAN, is_active=True).count(),
            "open_tickets": Ticket.objects.exclude(status=Ticket.Status.DONE).count(),
            "urgent_tickets": Ticket.objects.filter(priority=Ticket.Priority.CRITICAL)
            .exclude(status=Ticket.Status.DONE)
            .count(),
            "resolved_this_month": Ticket.objects.filter(
                status__in=[Ticket.Status.RESOLVED, Ticket.Status.DONE],
                resolved_at__gte=month_start,
            ).count(),
            "by_status": list(Ticket.objects.values("status").annotate(count=Count("id"))),
            "by_category": list(
                Ticket.objects.values("category__name").annotate(count=Count("id")).order_by("-count")
            ),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticatedActive])
def my_requests(request):
    """Requester inbox: tickets created by the authenticated user only."""
    qs = ticket_base_qs().filter(created_by=request.user)
    status_filter = request.query_params.get("status")
    if status_filter == "done":
        qs = qs.filter(status=Ticket.Status.DONE)
    elif status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status=Ticket.Status.DONE)
    qs = apply_ticket_query_filters(qs, request)
    return Response(TicketListSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsITGuy])
def it_tickets(request):
    """IT inbox: tickets assigned to the technician. SuperAdmin sees all."""
    user = request.user
    qs = ticket_base_qs()
    status_filter = request.query_params.get("status")
    if user.role != User.Role.SUPERADMIN:
        qs = qs.filter(assigned_technician=user)
    if status_filter == "done":
        qs = qs.filter(status=Ticket.Status.DONE)
    elif status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status=Ticket.Status.DONE)
    qs = apply_ticket_query_filters(qs, request)
    return Response(TicketListSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def reports(request):
    return dashboard_admin(request)
