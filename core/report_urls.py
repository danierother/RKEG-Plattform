from django.urls import path
from .report_views import REPORTS, ReportIndexView, ReportView

app_name = 'reports'
urlpatterns = [path('', ReportIndexView.as_view(), name='index')]
for name in REPORTS:
    urlpatterns += [
        path(f'{name}/', ReportView.as_view(report_type=name), name=name),
        path(f'{name}/print/', ReportView.as_view(report_type=name, print_view=True), name=name+'-print'),
    ]
