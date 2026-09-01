from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import hr_views, views

router = DefaultRouter()
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("tickets", views.TicketViewSet, basename="ticket")
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("admin/users", views.AdminUserViewSet, basename="admin-user")
router.register("technicians", views.TechnicianListView, basename="technician")
router.register("attendance", hr_views.AttendanceViewSet, basename="attendance")
router.register("employee-requests", hr_views.EmployeeRequestViewSet, basename="employee-request")

urlpatterns = [
    path("auth/register/", views.register),
    path("auth/login/", views.login),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("me/", views.me),
    path("directory/", views.directory),
    path("dashboard/user/", views.dashboard_user),
    path("dashboard/it/", views.dashboard_it),
    path("dashboard/admin/", views.dashboard_admin),
    path("dashboard/hr/", hr_views.dashboard_hr),
    path("my-requests/", views.my_requests),
    path("my-employee-requests/", hr_views.my_employee_requests),
    path("it-tickets/", views.it_tickets),
    path("reports/", views.reports),
    path("", include(router.urls)),
]
