class PackError(Exception):
    """Raised when packing fails."""


def create_capcut_pack(*_args, **_kwargs):
    raise RuntimeError("Deprecated: use gateway.app.services.steps_v1.run_pack_step")
