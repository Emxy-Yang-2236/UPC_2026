"""Keep real symlink checks on capable hosts; report missing OS privilege as a skip."""


def make_symlink(test_case, link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            test_case.skipTest("Windows account lacks symbolic-link creation privilege")
        raise
