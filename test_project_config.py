import pathlib
import tomllib
import unittest

class ProjectConfigurationTests(unittest.TestCase):
    def test_standalone_app_is_not_declared_as_a_package(self):
        config = tomllib.loads(pathlib.Path(__file__).with_name('pyproject.toml').read_text())
        self.assertNotIn('build-system', config)
        self.assertNotIn('scripts', config['project'])
