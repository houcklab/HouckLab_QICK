import pytest

from tests.refactor.equivalence import legacy_worktree


@pytest.fixture(scope="session")
def legacy_root():
    """The legacy tree at 0f0a51f, checked out once per session into a temp git worktree."""
    with legacy_worktree() as root:
        yield root
