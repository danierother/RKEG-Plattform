from django.urls import path

from .views import OrganizationDetailView, OrganizationSelectionView

app_name = 'organizations'

urlpatterns = [
    path('', OrganizationDetailView.as_view(), name='detail'),
    path('select/', OrganizationSelectionView.as_view(), name='select'),
]
