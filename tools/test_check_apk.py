"""Regression tests for the release manifest surface check; no Android tools required."""
import copy
import json
import unittest
from pathlib import Path
from check_apk import Node, check_exported_components, check_activity_classes


class ExportedComponentsTest(unittest.TestCase):
    def setUp(self):
        self.manifest = Node('manifest')
        self.app = Node('application')
        self.manifest.children.append(self.app)
        for row in json.loads(Path(__file__).with_name('exported_components.json').read_text()):
            node = Node(row['kind'])
            node.attrs = {key: value for key, value in row.items() if key != 'kind'}
            node.attrs['exported'] = 'true'
            if node.attrs['enabled'].startswith('@bool/'):
                node.attrs['enabled'] = '@0x123'
            self.app.children.append(node)
        self.names = {'0x123': 'bool/enable_system_job_service_default'}

    def test_reviewed_surface_passes(self):
        self.assertEqual([], check_exported_components(self.manifest, self.app, self.names))

    def test_every_component_kind_is_checked_even_when_disabled(self):
        for kind in ('activity', 'activity-alias', 'provider', 'service', 'receiver'):
            with self.subTest(kind=kind):
                manifest, app = copy.deepcopy((self.manifest, self.app))
                node = Node(kind)
                node.attrs = {'name': 'new.Component', 'exported': 'true', 'enabled': 'false'}
                app.children.append(node)
                self.assertTrue(check_exported_components(manifest, app, self.names))

    def test_weakened_required_permission_is_rejected(self):
        node = next(n for n in self.app.children if n.attrs['permission'])
        node.attrs['permission'] = ''
        self.assertTrue(check_exported_components(self.manifest, self.app, self.names))

    def test_alias_target_changes_are_rejected(self):
        node = next(n for n in self.app.children if n.tag == 'activity-alias')
        node.attrs['targetActivity'] = 'another.Activity'
        self.assertTrue(check_exported_components(self.manifest, self.app, self.names))

    def test_provider_read_permission_changes_are_rejected(self):
        node = next(n for n in self.app.children if n.tag == 'provider')
        node.attrs['readPermission'] = 'changed.permission'
        self.assertTrue(check_exported_components(self.manifest, self.app, self.names))


class ActivityClassesTest(unittest.TestCase):
    def manifest(self, kind="activity", **attrs):
        root, manifest, app, activity = [Node(tag) for tag in ("#document", "manifest", "application", kind)]
        manifest.attrs["package"] = "orb.test"
        activity.attrs = {"name": ".MainActivity", "exported": "true", **attrs}
        root.children.append(manifest)
        manifest.children.append(app)
        app.children.append(activity)
        return root

    def test_present_exported_activity_passes(self):
        self.assertEqual([], check_activity_classes(self.manifest(), {"Lorb/test/MainActivity;"}))

    def test_absent_exported_activity_fails(self):
        self.assertTrue(check_activity_classes(self.manifest(), set()))

    def test_disabled_exported_alias_requires_target_class(self):
        manifest = self.manifest("activity-alias", targetActivity=".MainActivity", enabled="false")
        self.assertTrue(check_activity_classes(manifest, set()))
        self.assertEqual([], check_activity_classes(manifest, {"Lorb/test/MainActivity;"}))

    def test_preview_tooling_is_rejected_even_if_private_and_present(self):
        for name in ("androidx.compose.ui.tooling.PreviewActivity",
                     "org.jetbrains.androidx.compose.ui.tooling.PreviewActivity",
                     "example.preview.OtherActivity"):
            with self.subTest(name=name):
                self.assertTrue(check_activity_classes(self.manifest(name=name, exported="false"),
                                                       {"L" + name.replace(".", "/") + ";"}))

    def test_implicit_exported_activity_is_checked(self):
        manifest = self.manifest()
        activity = manifest.find("activity")[0]
        del activity.attrs["exported"]
        activity.children.append(Node("intent-filter"))
        self.assertTrue(check_activity_classes(manifest, set()))


if __name__ == '__main__':
    unittest.main()
