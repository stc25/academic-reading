from django.urls import path

from . import views

app_name = "reading"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("open/<str:source_ref>/", views.open_view, name="open"),
    path("upload/", views.upload_view, name="upload"),
    path("read/<int:pk>/", views.read_redirect_view, name="read"),
    path("read/<int:pk>/reset/", views.reset_view, name="reset"),
    path("read/<int:pk>/<str:activity_id>/", views.activity_view, name="activity"),
    path("read/<int:pk>/<str:activity_id>/generate/", views.generate_view, name="generate"),
    path("read/<int:pk>/<str:activity_id>/submit/", views.submit_view, name="submit"),
    path("history/", views.history_view, name="history"),
]
