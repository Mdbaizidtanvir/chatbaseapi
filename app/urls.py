from django.urls import path
from .views import *

urlpatterns = [
    path("upload/", MultiFileUploadView.as_view(), name="multi_upload"),
    path("query-bot/", query_bot, name="query_bot"),
    path("delete-file/", delete_user_file, name="delete_user_file"),
    path("list-files/", list_user_files, name="list_user_files"),
]
