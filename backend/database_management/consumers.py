from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .task_permissions import can_monitor_transfer_tasks, can_view_transfer_payload


class DatabaseTransferConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not await database_sync_to_async(can_monitor_transfer_tasks)(user):
            await self.close(code=4403)
            return
        self.group_name = f"database_transfer_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def transfer_update(self, event):
        task = event["task"]
        if await database_sync_to_async(can_view_transfer_payload)(self.scope["user"], task):
            await self.send_json(task)
