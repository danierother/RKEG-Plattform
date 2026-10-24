from django.urls import path

from . import views

app_name = 'incidents'

urlpatterns = [
    path('', views.IncidentListView.as_view(), name='list'),
    path('new/', views.IncidentCreateView.as_view(), name='create'),
    path('<int:pk>/', views.IncidentDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.IncidentUpdateView.as_view(), name='edit'),
    path('<int:incident_pk>/events/new/', views.IncidentEventCreateView.as_view(), name='event-create'),
    path('<int:incident_pk>/actions/new/', views.IncidentActionCreateView.as_view(), name='action-create'),
    path('<int:incident_pk>/actions/<int:pk>/edit/', views.IncidentActionUpdateView.as_view(), name='action-edit'),
]
