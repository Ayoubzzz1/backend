from django.contrib import admin

from .models import (
    Category,
    Department,
    Notification,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketHistory,
    User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "last_name", "first_name", "role", "department", "is_active")
    search_fields = ("email", "last_name", "first_name", "full_name")
    list_filter = ("role", "is_active", "department")


admin.site.register(Department)
admin.site.register(Category)
admin.site.register(Ticket)
admin.site.register(TicketComment)
admin.site.register(TicketAttachment)
admin.site.register(TicketHistory)
admin.site.register(Notification)
