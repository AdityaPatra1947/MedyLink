from django.urls import path

from . import views
from . import ml_views

urlpatterns = [
    path("ml/catalog/", ml_views.MLCatalogView.as_view()),
    path("ml/insights/", ml_views.MLInsightsView.as_view()),
    path("ml/runs/", ml_views.MLRunsView.as_view()),
    path("ml/runs/<uuid:pk>/", ml_views.MLRunView.as_view()),
    path("catalog/", views.CatalogView.as_view()),
    path("summary/", views.SummaryView.as_view()),
    path("cluster-runs/", views.ClusterRunsView.as_view()),
    path("cluster-runs/<uuid:pk>/", views.RunView.as_view()),
    path("evaluation-runs/", views.EvaluationRunsView.as_view()),
    path("evaluation-runs/<uuid:pk>/", views.EvaluationRunView.as_view()),
]
