from django.urls import path

from .consumers import RdpTerminalConsumer, TerminalConsumer
from database_management.consumers import DatabaseTransferConsumer

websocket_urlpatterns = [
    path("ws/web-terminal/rdp/<int:host_id>/", RdpTerminalConsumer.as_asgi()),
    path("ws/web-terminal/<int:host_id>/", TerminalConsumer.as_asgi()),
    path("ws/database-transfers/", DatabaseTransferConsumer.as_asgi()),
]
