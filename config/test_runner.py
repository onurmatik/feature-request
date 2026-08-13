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
