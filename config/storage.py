import re

from django.contrib.staticfiles.storage import ManifestFilesMixin, StaticFilesStorage
from storages.backends.s3 import S3Storage


class AssetManifestMixin(ManifestFilesMixin):
    # The widget's shadow-root stylesheet is a JS dependency. Rewriting it also
    # changes the loader's hash when only its stylesheet changes.
    patterns = ManifestFilesMixin.patterns + (
        (
            "projects/embed-widget.js",
            (
                (
                    r'(?P<matched>new URL\("(?P<url>embed-loader\.css)", scriptUrl\))',
                    'new URL("%(url)s", scriptUrl)',
                ),
            ),
        ),
    )


class ManifestStaticFilesStorage(AssetManifestMixin, StaticFilesStorage):
    pass


class S3ManifestStaticFilesStorage(AssetManifestMixin, S3Storage):
    def get_object_parameters(self, name):
        parameters = super().get_object_parameters(name).copy()
        # Keep legacy unversioned embed URLs usable while hashed assets can be
        # cached permanently. The manifest must also be revalidated.
        parameters["CacheControl"] = (
            "public, max-age=31536000, immutable"
            if re.search(r"\.[0-9a-f]{12}\.[^/]+$", name)
            else "no-cache"
        )
        return parameters
