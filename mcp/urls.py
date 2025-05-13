from django.urls import path

from . import views

urlpatterns = [
    path(r"", views.index, name="index"),
    path(r"guide", views.guide, name="guide"),
    path(r"prospect_report", views.prospect_report, name="prospect_report"),
    path(r"status_report", views.status_report, name="status_report"),
    path(r"final_report", views.final_report, name="final_report"),
    path(r"market_report", views.market_report, name="market_report"),
    path(r"teams_summary", views.teams_summary, name="teams_summary"),
    path(r"teams_detail", views.teams_detail, name="teams_detail"),
    path(r"teams_stats", views.teams_stats, name="teams_stats"),
    path(r"delete_all", views.delete_all, name="delete_all"),
    path(r"startup", views.startup, name="startup"),
    path(r"register_team", views.register_team, name="register_team"),
    path(r"build_hubs", views.build_hubs, name="build_hubs"),
    path(r"deploy_hubs", views.deploy_hubs, name="deploy_hubs"),
    path(r"move_hubs", views.move_hubs, name="move_hubs"),
    path(r"ship_ore", views.ship_ore, name="ship_ore"),
    path(r"parameters", views.parameters, name="parameters"),
    path(r"set_scenario", views.set_scenario, name="set_scenario"),
    path(r"get_ledger", views.get_ledger, name="get_ledger"),
]
