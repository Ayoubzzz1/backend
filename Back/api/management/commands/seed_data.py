from django.core.management.base import BaseCommand

from api.models import Department, User


class Command(BaseCommand):
    help = "Create default KOKAM PLUS SuperAdmin and a sample technician if missing"

    def handle(self, *args, **options):
        if not User.objects.filter(email="admin@kokamplus.local").exists():
            User.objects.create_superuser(
                email="admin@kokamplus.local",
                password="KokamPlus2026!",
                full_name="SuperAdmin KOKAM PLUS",
                first_name="SuperAdmin",
                last_name="KOKAM PLUS",
                job_position="Directeur",
                office="Directeur-bureau 1",
            )
            self.stdout.write(self.style.SUCCESS("Created SuperAdmin  admin@kokamplus.local / KokamPlus2026!"))
        else:
            self.stdout.write("SuperAdmin already exists: admin@kokamplus.local")

        it_dept = Department.objects.filter(name="IT").first()
        tech = User.objects.filter(email="tech@kokamplus.local").first()
        if not tech:
            User.objects.create_user(
                email="tech@kokamplus.local",
                password="KokamPlus2026!",
                full_name="Ahmed IT",
                first_name="Ahmed",
                last_name="IT",
                role=User.Role.TECHNICIAN,
                department=it_dept,
                job_position="IT",
                office="IT-bureau 1",
            )
            self.stdout.write(self.style.SUCCESS("Created technician  tech@kokamplus.local / KokamPlus2026!"))
        else:
            if it_dept and tech.department_id is None:
                tech.department = it_dept
                tech.save(update_fields=["department"])
            self.stdout.write("Technician already exists: tech@kokamplus.local")
