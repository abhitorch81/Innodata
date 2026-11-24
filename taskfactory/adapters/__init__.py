def get_adapter(lang):
    if lang == "python":
        from .python_pytest import PytestAdapter
        return PytestAdapter()
    if lang == "cpp":
        from .cpp_gpp import GppAdapter
        return GppAdapter()
    if lang == "ts":
        from .ts_vitest import VitestAdapter
        return VitestAdapter()
    raise KeyError(lang)
