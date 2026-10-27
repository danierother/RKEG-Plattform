from django.urls import path
from . import views

app_name = 'services'
urlpatterns = [
    path('', views.ServiceListView.as_view(), name='list'),
    path('new/', views.ServiceCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ServiceDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ServiceUpdateView.as_view(), name='edit'),
    path('locations/', views.LocationListView.as_view(), name='location-list'),
    path('locations/new/', views.LocationCreateView.as_view(), name='location-create'),
    path('locations/<int:pk>/', views.LocationDetailView.as_view(), name='location-detail'),
    path('locations/<int:pk>/edit/', views.LocationUpdateView.as_view(), name='location-edit'),
    path('<int:service_pk>/dependencies/new/', views.DependencyCreateView.as_view(), name='dependency-create'),
    path('<int:service_pk>/dependencies/<int:pk>/', views.DependencyDetailView.as_view(), name='dependency-detail'),
    path('<int:service_pk>/dependencies/<int:pk>/edit/', views.DependencyUpdateView.as_view(), name='dependency-edit'),
]
