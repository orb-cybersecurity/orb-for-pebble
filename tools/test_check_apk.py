"""Regression tests for the release manifest surface check; no Android tools required."""
import copy
import json
import unittest
from pathlib import Path
from check_apk import Node, check_exported_components


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


if __name__ == '__main__':
    unittest.main()
