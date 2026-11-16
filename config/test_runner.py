from django.conf import settings
from django.test import override_settings
from django.test.runner import DiscoverRunner


class RepositoryDiscoverRunner(DiscoverRunner):
    """Discover only repository-owned test packages when no labels are supplied."""

    repository_test_labels = (
        "accounts",
        "config",
        "inbox",
        "projects",
        "mcp_oauth",
        "feature_request_mcp",
        "tests",
    )

    def build_suite(self, test_labels=None, extra_tests=None, **kwargs):
        labels = tuple(test_labels or self.repository_test_labels)
        return super().build_suite(labels, extra_tests=extra_tests, **kwargs)

    def run_tests(self, *args, **kwargs):
        # Ordinary tests don't publish assets or need a production manifest.
        # Storage integration tests opt back into manifest storage explicitly.
        storages = {
            **settings.STORAGES,
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
        with override_settings(STORAGES=storages):
            return super().run_tests(*args, **kwargs)
