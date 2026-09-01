from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire.")
        email = self.normalize_email(email)
        extra_fields.setdefault(
            "full_name",
            extra_fields.get("full_name")
            or " ".join(
                p for p in [extra_fields.get("first_name", ""), extra_fields.get("last_name", "")] if p
            ).strip()
            or email.split("@")[0],
        )
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.USER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPERADMIN)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "Employé"
        TECHNICIAN = "technician", "IT Technician"
        HR = "hr", "RH"
        SUPERADMIN = "superadmin", "SuperAdmin"

    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    job_position = models.CharField("Poste", max_length=120, blank=True)
    employee_id = models.CharField("Matricule", max_length=60, blank=True)
    login_name = models.CharField("Nom d'utilisateur", max_length=80, blank=True, unique=True, null=True)
    hire_date = models.DateField("Date d'embauche", null=True, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    office = models.CharField("Bureau", max_length=80, blank=True, unique=True, null=True)
    building = models.CharField(max_length=80, blank=True)
    floor = models.CharField(max_length=40, blank=True)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["last_name", "first_name"]

    def save(self, *args, **kwargs):
        composed = " ".join(p for p in [self.first_name, self.last_name] if p).strip()
        if composed:
            self.full_name = composed
        if not self.office:
            self.office = None
        if not self.login_name:
            self.login_name = None
        if self.role not in (self.Role.SUPERADMIN, self.Role.HR):
            dept = self.department
            if dept_id := self.department_id:
                if dept is None or getattr(dept, "pk", None) != dept_id:
                    dept = Department.objects.filter(pk=dept_id).first()
            if dept and str(dept.name).strip().upper() == "IT":
                self.role = self.Role.TECHNICIAN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_technician(self):
        return self.role == self.Role.TECHNICIAN

    @property
    def is_hr(self):
        return self.role == self.Role.HR

    @property
    def is_superadmin(self):
        return self.role == self.Role.SUPERADMIN



class Ticket(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        DONE = "done", "Done"

    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_tickets"
    )
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="related_tickets",
    )
    it_service = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    assigned_team = models.CharField(max_length=40, default="IT")
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tickets",
        limit_choices_to={"role": User.Role.TECHNICIAN},
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="tickets")
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    bureau = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    work_notes = models.TextField(blank=True)
    resolution_info = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    intervention_duration = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            from .services import next_ticket_number

            self.ticket_number = next_ticket_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.ticket_number} {self.title}"

    @property
    def display_number(self):
        return f"#{self.ticket_number}"

    @property
    def resolution_seconds(self):
        if not self.started_at or not self.resolved_at:
            return None
        return max(0, int((self.resolved_at - self.started_at).total_seconds()))

    @property
    def resolution_time(self):
        seconds = self.resolution_seconds
        if seconds is None:
            return None
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        if hours:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"


class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    comment = models.ForeignKey(
        TicketComment, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments"
    )
    file = models.FileField(upload_to="tickets/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TicketHistory(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    old_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "ticket histories"


class Notification(models.Model):
    class Type(models.TextChoices):
        TICKET_CREATED = "ticket_created", "Ticket créé"
        ASSIGNMENT = "assignment", "Assignation"
        STATUS = "status", "Statut"
        COMMENT = "comment", "Commentaire"
        RESOLUTION = "resolution", "Résolution"
        REQUEST = "request", "Demande RH"


    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=40, choices=Type.choices)
    related_ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.CASCADE)
    related_request = models.ForeignKey(
        "EmployeeRequest", null=True, blank=True, on_delete=models.CASCADE
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Attendance(models.Model):
    class Presence(models.TextChoices):
        PRESENT = "present", "Présent"
        ABSENT = "absent", "Absent"
        WEEKEND = "weekend", "Week-end"
        HOLIDAY = "holiday", "Jour férié"
        LEAVE = "leave", "Congé"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    presence = models.CharField(max_length=20, choices=Presence.choices, default=Presence.PRESENT)
    note = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["date"]


class EmployeeRequest(models.Model):
    class Kind(models.TextChoices):
        LEAVE = "leave", "Demande de congé"
        ADVANCE = "advance", "Demande d'avance"
        GENERAL = "general", "Demande"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Refusée"

    class Destination(models.TextChoices):
        DIRECTION = "direction", "Direction"
        HR = "hr", "RH"
        ADMIN = "administration", "Administration"

    class LeaveType(models.TextChoices):
        ANNUAL = "annual", "Congé annuel"
        SICK = "sick", "Congé maladie"
        UNPAID = "unpaid", "Congé sans solde"
        OTHER = "other", "Autre"

    request_number = models.CharField(max_length=20, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_requests"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    destination = models.CharField(max_length=30, choices=Destination.choices, default=Destination.HR)
    title = models.CharField(max_length=200, blank=True)
    motif = models.TextField(blank=True)
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    days = models.PositiveIntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="TND")
    admin_comment = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.request_number:
            last = EmployeeRequest.objects.order_by("-id").values_list("id", flat=True).first()
            n = (last or 0) + 1
            self.request_number = f"{n:06d}"
        super().save(*args, **kwargs)

    @property
    def display_number(self):
        return f"#{self.request_number}"

