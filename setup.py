"""Keep root sql/ authoritative while bundling identical assets into wheels."""

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithSQL(build_py):
    def run(self):
        super().run()
        source = Path(__file__).resolve().parent / 'sql'
        destination = Path(self.build_lib) / 'zhishu_inspection' / 'sql'
        for path in source.rglob('*.sql'):
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


setup(cmdclass={'build_py': BuildWithSQL})
