from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    Attendance,
    Category,
    Department,
    EmployeeRequest,
    Notification,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketHistory,
)

User = get_user_model()


def make_office_code(department_name, number):
    return f"{department_name}-bureau {int(number)}"


def parse_office_number(office):
    if not office:
        return None
    marker = "-bureau "
    if marker in office:
        tail = office.rsplit(marker, 1)[-1].strip()
        if tail.isdigit():
            return int(tail)
    return None


def apply_service_office(attrs, instance=None):
    department = attrs.get("department", getattr(instance, "department", None) if instance else None)
    if department in ("", None):
        department = getattr(instance, "department", None) if instance else None
    office_number = attrs.pop("office_number", None)
    if office_number is None and instance and "office" not in attrs:
        office_number = parse_office_number(instance.office)
    if department and getattr(department, "name", None):
        attrs["job_position"] = department.name
        if office_number is not None:
            attrs["office"] = make_office_code(department.name, office_number)
    return attrs, office_number


def ensure_unique_office(office, instance=None):
    if not office:
        raise serializers.ValidationError({"office_number": "Indiquez le numéro de bureau."})
    qs = User.objects.filter(office__iexact=office)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError({"office_number": "Ce bureau est déjà attribué."})



class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ("id", "name", "is_active")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "is_active")
        read_only_fields = ("slug",)

    def create(self, validated_data):
        from django.utils.text import slugify

        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        from django.utils.text import slugify

        if "name" in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])
        return super().update(instance, validated_data)


class UserPublicSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "job_position",
            "department",
            "department_name",
            "office",
            "role",
            "is_active",
        )
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    full_name = serializers.CharField(read_only=True)
    office_number = serializers.IntegerField(write_only=True, required=False, min_value=1)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "job_position",
            "department",
            "department_name",
            "office",
            "office_number",
            "role",
            "is_active",
            "employee_id",
            "login_name",
            "phone",
            "hire_date",
        )
        read_only_fields = (
            "id",
            "email",
            "role",
            "is_active",
            "full_name",
            "department",
            "job_position",
            "office",
            "employee_id",
            "login_name",
            "hire_date",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["office_number"] = parse_office_number(instance.office)
        return data

    def validate(self, attrs):
        attrs, _ = apply_service_office(attrs, self.instance)
        if "office" in attrs:
            ensure_unique_office(attrs["office"], self.instance)
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    office_number = serializers.IntegerField(write_only=True, min_value=1)

    class Meta:
        model = User
        fields = (
            "last_name",
            "first_name",
            "department",
            "office_number",
            "email",
            "password",
            "confirm_password",
        )
        extra_kwargs = {
            "last_name": {"required": True, "allow_blank": False},
            "first_name": {"required": True, "allow_blank": False},
            "department": {"required": True},
        }

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Les mots de passe ne correspondent pas."})
        validate_password(attrs["password"])
        attrs, _ = apply_service_office(attrs)
        ensure_unique_office(attrs.get("office"))
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        department = validated_data.get("department")
        role = User.Role.TECHNICIAN if department and str(department.name).strip().upper() == "IT" else User.Role.USER
        return User.objects.create_user(password=password, role=role, **validated_data)


class AdminUserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    office_number = serializers.IntegerField(write_only=True, required=False, min_value=1)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "job_position",
            "department",
            "department_name",
            "office",
            "office_number",
            "role",
            "is_active",
            "password",
            "phone",
            "employee_id",
            "login_name",
            "hire_date",
        )
        read_only_fields = ("full_name", "job_position", "office")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["office_number"] = parse_office_number(instance.office)
        return data

    def validate(self, attrs):
        if attrs.get("login_name") == "":
            attrs["login_name"] = None
        if attrs.get("department") == "":
            attrs["department"] = None
        attrs, office_number = apply_service_office(attrs, self.instance)
        if not attrs.get("office") and office_number is None and not self.instance:
            raise serializers.ValidationError({"office_number": "Indiquez le numéro de bureau."})
        if "office" in attrs:
            ensure_unique_office(attrs["office"], self.instance)
        return attrs

    def create(self, validated_data):
        import secrets

        password = validated_data.pop("password", None) or secrets.token_urlsafe(10)
        role = validated_data.pop("role", User.Role.USER)
        if not validated_data.get("employee_id"):
            validated_data["employee_id"] = f"EMP-{User.objects.count() + 1:04d}"
        user = User.objects.create_user(password=password, role=role, **validated_data)
        if role == User.Role.SUPERADMIN:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        role = validated_data.get("role", instance.role)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.is_staff = role == User.Role.SUPERADMIN
        instance.is_superuser = role == User.Role.SUPERADMIN
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    author_role = serializers.CharField(source="author.role", read_only=True)

    class Meta:
        model = TicketComment
        fields = ("id", "author", "author_name", "author_role", "message", "created_at")
        read_only_fields = ("id", "author", "created_at")


class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)

    class Meta:
        model = TicketAttachment
        fields = ("id", "file", "uploaded_by", "uploaded_by_name", "created_at", "comment")
        read_only_fields = ("id", "uploaded_by", "created_at")


class TicketHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)

    class Meta:
        model = TicketHistory
        fields = ("id", "actor", "actor_name", "action", "old_value", "new_value", "created_at")


class TicketListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    it_service_name = serializers.CharField(source="it_service.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    created_by_department = serializers.CharField(source="created_by.department.name", read_only=True, allow_null=True)
    created_by_office = serializers.CharField(source="created_by.office", read_only=True, allow_null=True)
    created_by_job_position = serializers.CharField(source="created_by.job_position", read_only=True, allow_null=True)
    related_user_name = serializers.CharField(source="related_user.full_name", read_only=True)
    technician_name = serializers.CharField(source="assigned_technician.full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    display_number = serializers.CharField(read_only=True)
    resolution_time = serializers.CharField(read_only=True)
    resolution_seconds = serializers.IntegerField(read_only=True)
    intervention_duration = serializers.CharField(read_only=True)

    class Meta:
        model = Ticket
        fields = (
            "id",
            "ticket_number",
            "display_number",
            "title",
            "category",
            "category_name",
            "it_service",
            "it_service_name",
            "related_user",
            "related_user_name",
            "bureau",
            "priority",
            "priority_label",
            "status",
            "status_label",
            "created_by",
            "created_by_name",
            "created_by_department",
            "created_by_office",
            "created_by_job_position",
            "assigned_technician",
            "technician_name",
            "created_at",
            "started_at",
            "resolved_at",
            "closed_at",
            "resolution_time",
            "resolution_seconds",
            "intervention_duration",
            "updated_at",
        )


class TicketDetailSerializer(TicketListSerializer):
    created_by_detail = UserPublicSerializer(source="created_by", read_only=True)
    related_user_detail = UserPublicSerializer(source="related_user", read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    history = TicketHistorySerializer(many=True, read_only=True)
    description = serializers.CharField()

    class Meta(TicketListSerializer.Meta):
        fields = TicketListSerializer.Meta.fields + (
            "description",
            "assigned_team",
            "created_by_detail",
            "related_user_detail",
            "work_notes",
            "resolution_info",
            "comments",
            "attachments",
            "history",
        )


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ("category", "title", "description", "priority")

    def create(self, validated_data):
        from django.db.models import Count, Q

        user = self.context["request"].user
        it_service = Department.objects.filter(name__iexact="IT", is_active=True).first()
        if not it_service:
            it_service = Department.objects.filter(name__iexact="IT").first()
        technicians = (
            User.objects.filter(role=User.Role.TECHNICIAN, is_active=True)
            .annotate(
                active_count=Count(
                    "assigned_tickets",
                    filter=~Q(assigned_tickets__status=Ticket.Status.DONE),
                )
            )
            .order_by("active_count", "id")
        )
        if it_service:
            in_dept = technicians.filter(department=it_service)
            technician = in_dept.first() or technicians.first()
        else:
            technician = technicians.first()
        return Ticket.objects.create(
            created_by=user,
            related_user=user,
            it_service=it_service,
            assigned_team="IT",
            status=Ticket.Status.NEW,
            bureau=user.office or "",
            location=user.office or "",
            assigned_technician=technician,
            **validated_data,
        )


class TicketUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ("priority", "status", "work_notes", "resolution_info", "description")


class NotificationSerializer(serializers.ModelSerializer):
    ticket_number = serializers.CharField(source="related_ticket.ticket_number", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "message",
            "type",
            "related_ticket",
            "ticket_number",
            "is_read",
            "created_at",
        )
        read_only_fields = ("id", "title", "message", "type", "related_ticket", "ticket_number", "created_at")


class AttendanceSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    presence_label = serializers.CharField(source="get_presence_display", read_only=True)

    class Meta:
        model = Attendance
        fields = ("id", "user", "user_name", "date", "presence", "presence_label", "note", "updated_at")
        read_only_fields = ("id", "updated_at")


class EmployeeRequestSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    employee_id = serializers.CharField(source="created_by.employee_id", read_only=True)
    service = serializers.CharField(source="created_by.department.name", read_only=True, allow_null=True)
    bureau = serializers.CharField(source="created_by.office", read_only=True, allow_null=True)
    job_position = serializers.CharField(source="created_by.job_position", read_only=True, allow_null=True)
    login_name = serializers.CharField(source="created_by.login_name", read_only=True, allow_null=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    destination_label = serializers.CharField(source="get_destination_display", read_only=True)
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, allow_null=True)
    display_number = serializers.CharField(read_only=True)

    class Meta:
        model = EmployeeRequest
        fields = (
            "id",
            "request_number",
            "display_number",
            "created_by",
            "created_by_name",
            "employee_id",
            "login_name",
            "service",
            "bureau",
            "job_position",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "destination",
            "destination_label",
            "title",
            "motif",
            "leave_type",
            "leave_type_label",
            "start_date",
            "end_date",
            "days",
            "amount",
            "currency",
            "admin_comment",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "request_number",
            "display_number",
            "created_by",
            "status",
            "admin_comment",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        kind = attrs.get("kind") or getattr(self.instance, "kind", None)
        if kind == EmployeeRequest.Kind.LEAVE:
            if not attrs.get("start_date") or not attrs.get("end_date"):
                raise serializers.ValidationError("Les dates de début et de fin sont obligatoires.")
            start, end = attrs["start_date"], attrs["end_date"]
            if end < start:
                raise serializers.ValidationError("La date de fin doit être après la date de début.")
            days = 0
            d = start
            from datetime import timedelta

            while d <= end:
                if d.weekday() < 5:
                    days += 1
                d += timedelta(days=1)
            attrs["days"] = days
            attrs.setdefault("destination", EmployeeRequest.Destination.HR)
            attrs.setdefault("title", "Demande de congé")
        elif kind == EmployeeRequest.Kind.ADVANCE:
            if attrs.get("amount") is None:
                raise serializers.ValidationError({"amount": "Le montant est obligatoire."})
            attrs.setdefault("destination", EmployeeRequest.Destination.HR)
            attrs.setdefault("title", "Demande d'avance")
        else:
            if not attrs.get("title") and not attrs.get("motif"):
                raise serializers.ValidationError("Titre et objet sont obligatoires.")
            attrs.setdefault("kind", EmployeeRequest.Kind.GENERAL)
        return attrs

