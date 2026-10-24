from django.db.models import Count, Q
from django.views.generic import TemplateView

from organizations.mixins import OrganizationContextMixin
from risks.models import Risk
from risks.assessment import DEFAULT_RISK_BANDS, score_expression
from incidents.models import Incident


class DashboardView(OrganizationContextMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        risks = self.organization.risks.all()
        context['counts'] = risks.aggregate(
            total=Count('pk'),
            open=Count('pk', filter=Q(status=Risk.Status.OPEN)),
            in_progress=Count('pk', filter=Q(status=Risk.Status.IN_PROGRESS)),
            closed=Count('pk', filter=Q(status=Risk.Status.CLOSED)),
        )
        context['recent_risks'] = risks.select_related('created_by').order_by('-created_at', '-pk')[:5]
        class_counts = risks.annotate(score=score_expression()).aggregate(**{
            band.code: Count('pk', filter=Q(score__gte=band.minimum, score__lte=band.maximum))
            for band in DEFAULT_RISK_BANDS
        })
        context['risk_class_counts'] = class_counts
        context['risk_class_metrics'] = [
            {'band': band, 'count': class_counts[band.code]} for band in DEFAULT_RISK_BANDS
        ]
        residual_counts = risks.annotate(score=score_expression(residual=True)).aggregate(**{
            band.code: Count('pk', filter=Q(score__gte=band.minimum, score__lte=band.maximum))
            for band in DEFAULT_RISK_BANDS
        })
        context['residual_risk_class_counts'] = residual_counts
        context['residual_risk_class_metrics'] = [
            {'band': band, 'count': residual_counts[band.code]} for band in DEFAULT_RISK_BANDS
        ]
        incidents = self.organization.incidents.all()
        context['incident_counts'] = incidents.aggregate(
            open=Count('pk', filter=Q(status__in=Incident.OPEN_STATUSES)),
            critical=Count('pk', filter=Q(severity=Incident.Severity.CRITICAL)),
            under_review=Count('pk', filter=Q(reporting_status=Incident.ReportingStatus.UNDER_REVIEW)),
        )
        context['recent_incidents'] = incidents.select_related('responsible_user').order_by('-created_at', '-pk')[:5]
        return context
