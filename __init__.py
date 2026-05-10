if "tools" in locals():
    import importlib

    importlib.reload(tools)
else:
    from . import tools


def register():
    tools.register()


def unregister():
    tools.unregister()


if __name__ == "__main__":
    register()
