from django.urls import path

from . import views

urlpatterns = [
    path("pipeline/counts", views.PipelineCountsView.as_view(), name="v2-pipeline-counts"),

    # Potenciales
    path("pipeline/potentials/", views.PotentialListView.as_view(), name="v2-potential-list"),
    path("pipeline/potentials/<int:pk>/", views.PotentialDetailView.as_view(), name="v2-potential-detail"),

    # Etapa de un lead (combo del encabezado del chat) + Cotizar/Reservar rápido
    path("pipeline/leads/<int:pk>/stage", views.LeadStageView.as_view(), name="v2-lead-stage"),
    path("pipeline/leads/<int:pk>/quick-quote", views.LeadQuickQuoteView.as_view(), name="v2-lead-quick-quote"),
    path("pipeline/leads/<int:pk>/quick-booking", views.LeadQuickBookingView.as_view(), name="v2-lead-quick-booking"),
    path("pipeline/leads/<int:pk>/service-summary", views.LeadServiceSummaryView.as_view(), name="v2-lead-service-summary"),
    path("pipeline/leads/<int:pk>/service", views.LeadServiceEditView.as_view(), name="v2-lead-service-edit"),
    path("pipeline/leads/<int:pk>/cancel-booking", views.LeadCancelBookingView.as_view(), name="v2-lead-cancel-booking"),
    path("pipeline/leads/<int:pk>/discard", views.LeadDiscardView.as_view(), name="v2-lead-discard"),
    path("pipeline/leads/<int:pk>/mark-seen", views.LeadMarkSeenView.as_view(), name="v2-lead-mark-seen"),
    path("pipeline/leads/<int:pk>/reactivate", views.LeadReactivateView.as_view(), name="v2-lead-reactivate"),

    # Perdidos
    path("pipeline/lost/", views.LostListView.as_view(), name="v2-lost-list"),
    path("pipeline/leads/<int:pk>/send-summary", views.LeadSendSummaryView.as_view(), name="v2-lead-send-summary"),

    # Para revisión
    path("pipeline/review/", views.ReviewListView.as_view(), name="v2-review-list"),
    path("pipeline/review/<int:pk>/", views.ReviewDetailView.as_view(), name="v2-review-detail"),
    path("pipeline/review/<int:pk>/to-quoting", views.ReviewToQuotingView.as_view(), name="v2-review-to-quoting"),
    path("pipeline/review/<int:pk>/discard", views.ReviewDiscardView.as_view(), name="v2-review-discard"),

    # Por cotizar
    path("pipeline/quote-requests/", views.QuoteRequestListView.as_view(), name="v2-qr-list"),
    path("pipeline/quote-requests/<int:pk>/", views.QuoteRequestDetailView.as_view(), name="v2-qr-detail"),
    path("pipeline/quote-requests/<int:pk>/assign", views.QuoteRequestAssignView.as_view(), name="v2-qr-assign"),
    path("pipeline/quote-requests/<int:pk>/quote", views.QuoteRequestQuoteView.as_view(), name="v2-qr-quote"),
    path("pipeline/quote-requests/<int:pk>/send", views.QuoteRequestSendView.as_view(), name="v2-qr-send"),

    # Cotizaciones
    path("pipeline/quotes/", views.QuoteListView.as_view(), name="v2-quote-list"),
    path("pipeline/quotes/<int:pk>/", views.QuoteDetailView.as_view(), name="v2-quote-detail"),
    path("pipeline/quotes/<int:pk>/state", views.QuoteStateView.as_view(), name="v2-quote-state"),
    path("pipeline/quotes/<int:pk>/revise", views.QuoteReviseView.as_view(), name="v2-quote-revise"),
    path("pipeline/quotes/<int:pk>/accept", views.QuoteAcceptView.as_view(), name="v2-quote-accept"),

    # Reservas
    path("pipeline/bookings/", views.BookingListView.as_view(), name="v2-booking-list"),
    path("pipeline/bookings/<int:pk>/", views.BookingDetailView.as_view(), name="v2-booking-detail"),
    path("pipeline/bookings/<int:pk>/payment", views.BookingPaymentView.as_view(), name="v2-booking-payment"),
    path("pipeline/bookings/<int:pk>/finalize", views.BookingFinalizeView.as_view(), name="v2-booking-finalize"),
    path("pipeline/bookings/<int:pk>/cancel", views.BookingCancelView.as_view(), name="v2-booking-cancel"),
    path("pipeline/bookings/<int:pk>/set-mode", views.BookingSetModeView.as_view(), name="v2-booking-set-mode"),
]
