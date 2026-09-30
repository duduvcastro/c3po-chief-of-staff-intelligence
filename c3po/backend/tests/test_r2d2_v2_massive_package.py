from pathlib import Path
import shutil
import pytest
from app import r2d2_v2_earnings_package as package


@pytest.mark.parametrize('changed',['r2d2_v2_massive_producer.py','r2d2_v2_massive_supervisor.py'])
def test_bar_runtime_modules_are_bound_and_mutation_changes_release_package(tmp_path,monkeypatch,changed):
 root=Path(package.__file__).parent
 required={p.name for p in root.glob('r2d2_v2_massive_*.py')}|{'r2d2_v2_minute_bars.py','r2d2_v2_composite_source.py'}
 assert required<=set(package.PACKAGE_FILES)
 for name in package.PACKAGE_FILES:
  target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
 monkeypatch.setattr(package,'__file__',str(tmp_path/'r2d2_v2_earnings_package.py'))
 before=package.implementation_package_sha()
 target=tmp_path/changed
 target.write_bytes(target.read_bytes()+b'\n# offline mutation fixture\n')
 assert package.implementation_package_sha()!=before
