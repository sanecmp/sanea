"""Browser and sanex client routes for the sanea core application."""

from django.urls import include, path

from .views import (
    accounts,
    app_rules,
    client_events,
    client_log,
    client_register,
    client_register_confirm,
    client_sync,
    computers,
    dashboard,
    issues,
    ignored_processes,
    limits,
    people,
    ranges,
    session_rules,
    sign_in,
    sign_out,
)


app_name = "core"

urlpatterns = [
    path("client/", include([
        path("events/", include([
            path("<int:uid>/<str:sha256>", client_events, name="client_events"),
        ])),
        path("log", client_log, name="client_log"),
        path("register", client_register, name="client_register"),
        path("register/confirm", client_register_confirm, name="client_register_confirm"),
        path("sync", client_sync, name="client_sync"),
    ])),
    path("", dashboard, name="dashboard"),
    path("people/", people, name="people"),
    path("computers/", computers, name="computers"),
    path("accounts/", accounts, name="accounts"),
    path("limits/", include([
        path("", limits, name="limits"),
        path("<int:limits_pk>/", include([
            path("ranges/", ranges, name="ranges"),
            path("session-rules/", include([
                path("", session_rules, name="session_rules"),
                path("<int:rule_pk>/", include([
                    path("app-rules/", app_rules, name="app_rules"),
                ])),
            ])),
        ])),
    ])),
    path("issues/", issues, name="issues"),
    path("settings/", include([
        path("ignored-processes/", ignored_processes, name="ignored_processes"),
    ])),
    path("signin/", sign_in, name="sign_in"),
    path("signout/", sign_out, name="sign_out"),
]
