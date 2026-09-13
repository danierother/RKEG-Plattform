from django.urls import path

from .views import RiskCreateView, RiskDetailView, RiskListView, RiskUpdateView
from .views import RiskMeasureCreateView, RiskMeasureDetailView, RiskMeasureUpdateView

app_name = 'risks'

urlpatterns = [
    path('', RiskListView.as_view(), name='list'),
    path('new/', RiskCreateView.as_view(), name='create'),
    path('<int:pk>/', RiskDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', RiskUpdateView.as_view(), name='edit'),
    path('<int:risk_pk>/measures/new/', RiskMeasureCreateView.as_view(), name='measure-create'),
    path('<int:risk_pk>/measures/<int:pk>/', RiskMeasureDetailView.as_view(), name='measure-detail'),
    path('<int:risk_pk>/measures/<int:pk>/edit/', RiskMeasureUpdateView.as_view(), name='measure-edit'),
]
