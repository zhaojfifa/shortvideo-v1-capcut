import importlib, traceback
try:
    importlib.import_module('gateway.app.main')
    print('imported gateway.app.main successfully')
except Exception:
    traceback.print_exc()
