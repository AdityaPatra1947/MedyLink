from accounts.permissions import IsVerifiedAccount
from rest_framework.response import Response

from .dashboard import dashboard_data
from .services import audit, own_patient
from .views import DomainView


class PatientDashboardView(DomainView):
    permission_classes = (IsVerifiedAccount,)

    def get(self, request):
        patient = own_patient(request.user)
        data = dashboard_data(patient, request.user)
        audit(request, "dashboard.read", patient)
        return Response(data)
