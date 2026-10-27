from django.urls import path

from . import views
from . import reporting_views as reporting

app_name = 'incidents'

urlpatterns = [
    path('<int:pk>/rkeg/data/', reporting.ReportingFactsUpdateView.as_view(), name='reporting-data'),
    path('<int:incident_pk>/rkeg/services/<int:service_pk>/', reporting.ServiceImpactUpdateView.as_view(), name='service-impact'),
    path('<int:incident_pk>/rkeg/assess/', reporting.AssessmentCreateView.as_view(), name='assessment-create'),
    path('<int:incident_pk>/rkeg/assessments/<int:pk>/', reporting.AssessmentDetailView.as_view(), name='assessment-detail'),
    path('<int:incident_pk>/reports/new/', reporting.ReportCreateView.as_view(), name='report-create'),
    path('<int:incident_pk>/reports/<int:pk>/', reporting.ReportDetailView.as_view(), name='report-detail'),
    path('<int:incident_pk>/reports/<int:pk>/edit/', reporting.ReportUpdateView.as_view(), name='report-edit'),
    path('', views.IncidentListView.as_view(), name='list'),
    path('new/', views.IncidentCreateView.as_view(), name='create'),
    path('<int:pk>/', views.IncidentDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.IncidentUpdateView.as_view(), name='edit'),
    path('<int:incident_pk>/events/new/', views.IncidentEventCreateView.as_view(), name='event-create'),
    path('<int:incident_pk>/actions/new/', views.IncidentActionCreateView.as_view(), name='action-create'),
    path('<int:incident_pk>/actions/<int:pk>/edit/', views.IncidentActionUpdateView.as_view(), name='action-edit'),
]
