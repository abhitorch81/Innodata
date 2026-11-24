"""Auto-discovers every Recipe subclass in this package: drop a module in, it is registered."""
import importlib
import pkgutil

from ..core import Recipe

ALL: dict = {}
for _m in pkgutil.iter_modules(__path__):
    mod = importlib.import_module(f"{__name__}.{_m.name}")
    for obj in vars(mod).values():
        if isinstance(obj, type) and issubclass(obj, Recipe) and obj is not Recipe and obj.__module__ == mod.__name__ \
                and obj.repo and obj.family:
            ALL.setdefault(obj.repo, {})[obj.family] = obj()
