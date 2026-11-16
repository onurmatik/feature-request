import io
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import SimpleTestCase, override_settings

from .storage import ManifestStaticFilesStorage, S3ManifestStaticFilesStorage


class StaticAssetVersioningTest(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "source"
        self.collected = self.root / "collected"
        self.source.mkdir()
        self.assets = self.source / "projects"
        self.assets.mkdir()
        project_assets = settings.BASE_DIR / "projects/static/projects"
        for name in (
            "app.js", "app.css", "favicon.svg", "embed-widget.js",
            "embed-loader.css", "embed-widget.css", "embed-panel.js",
        ):
            (self.assets / name).write_bytes((project_assets / name).read_bytes())
        self.override = override_settings(
            DEBUG=False,
            STATIC_URL="/static/",
            STATIC_ROOT=self.collected,
            STATICFILES_DIRS=[self.source],
            STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"],
            STORAGES={"staticfiles": {"BACKEND": "config.storage.ManifestStaticFilesStorage"}},
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

    def collect(self):
        call_command("collectstatic", interactive=False, verbosity=0, stdout=io.StringIO())
        return ManifestStaticFilesStorage()

    def test_templates_and_widget_dependencies_use_collected_hashes(self):
        storage = self.collect()
        html = render_to_string("projects/app.html", {"fr_bootstrap_json": "{}"})
        for name in ("app.js", "app.css", "favicon.svg", "embed-widget.js"):
            url = storage.url(f"projects/{name}")
            self.assertRegex(url, r"\.[0-9a-f]{12}\.")
            self.assertIn(url, html)
            self.assertTrue((self.collected / storage.stored_name(f"projects/{name}")).is_file())
        self.assertEqual(html.count(f'src="{static("projects/embed-widget.js")}"'), 1)
        loader = self.collected / storage.stored_name("projects/embed-widget.js")
        css_name = Path(storage.stored_name("projects/embed-loader.css")).name
        self.assertIn(f'new URL("{css_name}", scriptUrl)', loader.read_text())
        for template in ("embed_widget.html", "embed_verify.html"):
            embedded = render_to_string(f"projects/{template}")
            self.assertIn(storage.url("projects/embed-widget.css"), embedded)
        self.assertIn(
            storage.url("projects/embed-panel.js"),
            render_to_string("projects/embed_widget.html"),
        )

    def test_changed_content_gets_new_urls_and_old_assets_remain_available(self):
        first = self.collect()
        original_urls = {name: first.url(f"projects/{name}") for name in (
            "app.js", "app.css", "embed-widget.js", "embed-loader.css",
        )}
        with (self.assets / "app.js").open("a") as asset:
            asset.write("\n// next release\n")
        with (self.assets / "embed-loader.css").open("a") as asset:
            asset.write("\n.fr-widget { outline-offset: 1px; }\n")
        second = self.collect()
        for name in ("app.js", "embed-widget.js", "embed-loader.css"):
            self.assertNotEqual(original_urls[name], second.url(f"projects/{name}"))
            self.assertTrue((self.collected / first.stored_name(f"projects/{name}")).exists())
        self.assertEqual(original_urls["app.css"], second.url("projects/app.css"))
        third = self.collect()
        self.assertEqual(second.hashed_files, third.hashed_files)

    def test_s3_urls_use_the_same_manifest_and_distinguish_cache_policies(self):
        local = self.collect()
        s3 = S3ManifestStaticFilesStorage(
            manifest_storage=FileSystemStorage(location=self.collected),
            bucket_name="test-assets",
            custom_domain="assets.example.test",
            location="static",
            querystring_auth=False,
        )
        name = local.stored_name("projects/app.js")
        self.assertEqual(s3.url("projects/app.js"), f"https://assets.example.test/static/{name}")
        self.assertEqual(
            s3.get_object_parameters(f"static/{name}")["CacheControl"],
            "public, max-age=31536000, immutable",
        )
        for path in ("static/projects/embed-widget.js", "static/staticfiles.json"):
            self.assertEqual(s3.get_object_parameters(path)["CacheControl"], "no-cache")

    @override_settings(DEBUG=True)
    def test_development_does_not_require_collectstatic(self):
        self.assertEqual(static("projects/app.js"), "/static/projects/app.js")
