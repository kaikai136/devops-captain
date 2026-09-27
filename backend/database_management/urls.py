from django.urls import path
from . import views
from . import catalog
from . import database_admin
urlpatterns = [
    path("database-management/directories/", catalog.directories),
    path("database-management/directories/<int:directory_id>/", catalog.directory_detail),
    path("database-management/directories/<int:directory_id>/copy/", catalog.directory_copy),
    path("database-management/connections/", catalog.connection_manifest),
    path("database-management/types/", views.types_view),
    path("database-management/sqlite-files/", views.sqlite_files),
    path("database-management/assets/", views.assets),
    path("database-management/assets/<int:asset_id>/", views.asset_detail),
    path("database-management/assets/<int:asset_id>/copy/", catalog.asset_copy),
    path("database-management/assets/<int:asset_id>/move/", catalog.asset_move),
    path("database-management/assets/<int:asset_id>/database/", database_admin.database_operation),
    path("database-management/assets/<int:asset_id>/test/", views.asset_test),
    path("database-management/databases/", views.asset_databases),
    path("database-management/tables/", views.asset_tables),
    path("database-management/columns/", views.asset_columns),
    path("database-management/data/", views.asset_data),
    path("database-management/assets/<int:asset_id>/tree/", views.asset_tree),
    path("database-management/assets/<int:asset_id>/objects/", views.asset_objects),
    path("database-management/assets/<int:asset_id>/columns/", views.asset_columns_v2),
    path("database-management/assets/<int:asset_id>/indexes/", views.asset_indexes),
    path("database-management/assets/<int:asset_id>/schema/", views.asset_schema),
    path("database-management/assets/<int:asset_id>/data/", views.asset_data_v2),
    path("database-management/assets/<int:asset_id>/sql/", views.asset_sql),
    path("database-management/assets/<int:asset_id>/redis/", views.asset_redis),
    path("database-management/assets/<int:asset_id>/export/", views.asset_export),
    path("database-management/assets/<int:asset_id>/import/", views.asset_import),
    path("database-management/assets/<int:asset_id>/rows/", views.asset_rows),
    path("database-management/assets/<int:asset_id>/transaction/", views.asset_transaction),
]
