import importlib
import pkgutil

COMMAND_HANDLERS = []

def command(name, description=""):
    def wrapper(func):
        COMMAND_HANDLERS.append((name, func, description))
        return func
    return wrapper

def load_all():
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name != "__init__":
            importlib.import_module(f"{__name__}.{module_name}")
