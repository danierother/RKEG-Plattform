from django.db.models import Count, Q
from django.views.generic import TemplateView

from organizations.mixins import OrganizationContextMixin
from risks.models import Risk
from risks.assessment import DEFAULT_RISK_BANDS, score_expression


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
        return context
