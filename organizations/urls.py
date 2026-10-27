from django.urls import path

from .views import OrganizationDetailView, OrganizationSelectionView, OrganizationRKEGView

app_name = 'organizations'

urlpatterns = [
    path('rkeg/', OrganizationRKEGView.as_view(), name='rkeg-edit'),
    path('', OrganizationDetailView.as_view(), name='detail'),
    path('select/', OrganizationSelectionView.as_view(), name='select'),
]
