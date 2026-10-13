# This code is derived from the conftest.py file in the ezomero project:
#   https://github.com/erickmartins/ezomero
#   Copyright (c) 2020-2025, Erick Ratamero, Dave Mellert, and contributors
#
# ezomero is distributed under the GNU General Public License, version 2
# (GPL-2.0). napari-omero is GPL-2.0-or-later, which is compatible. This file is
# distributed under the same terms; it comes with NO WARRANTY, to the extent
# permitted by law. See the GNU General Public License for more details.
#
# Note that these fixtures are only used for the OMERO server tests.
import os
import socket
import time

import ezomero
import numpy as np
import pytest
from omero.cli import CLI
from omero.gateway import BlitzGateway
from omero.plugins.group import GroupControl
from omero.plugins.sessions import SessionsControl
from omero.plugins.user import UserControl

# Settings for the OMERO *test* server, overridable with OMERO_TEST_USER,
# OMERO_TEST_PASS, OMERO_TEST_HOST, OMERO_TEST_PORT and OMERO_TEST_SECURE.
# These tests post, delete and create users/groups, so they never read the
# generic OMERO_HOST/OMERO_USER, which may point at a real server.
DEFAULT_OMERO_USER = "root"
DEFAULT_OMERO_PASS = "omero"
DEFAULT_OMERO_HOST = "localhost"
DEFAULT_OMERO_PORT = "4064"

# [[group, permissions], ...]
GROUPS_TO_CREATE = [["test_group_1", "read-only"], ["test_group_2", "read-only"]]

# [[user, [groups to be added to], [groups to own]], ...]
USERS_TO_CREATE = [
    ["test_user1", ["test_group_1", "test_group_2"], ["test_group_1"]],
    ["test_user2", ["test_group_1", "test_group_2"], ["test_group_2"]],
    ["test_user3", ["test_group_2"], []],
]


@pytest.fixture(scope="session")
def omero_params():
    """(user, password, host, port, secure) for the test server."""
    env = os.environ.get
    secure = env("OMERO_TEST_SECURE", "1").strip().lower() in ("1", "true", "yes")
    return (
        env("OMERO_TEST_USER", DEFAULT_OMERO_USER),
        env("OMERO_TEST_PASS", DEFAULT_OMERO_PASS),
        env("OMERO_TEST_HOST", DEFAULT_OMERO_HOST),
        env("OMERO_TEST_PORT", DEFAULT_OMERO_PORT),
        secure,
    )


@pytest.fixture(scope="session", autouse=True)
def _isolated_omero_userdir(tmp_path_factory):
    """Keep test logins out of the developer's real ~/omero/sessions.

    The browser widget restores the *current* saved session on start-up and
    saves new logins as current. Without this, a local run could reconnect to
    a real server, or leave the test login as the default afterwards.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OMERO_USERDIR", str(tmp_path_factory.mktemp("omero_userdir")))
        yield


@pytest.fixture(scope="session", autouse=True)
def _require_server(omero_params):
    """Skip the server tests when no OMERO server is reachable.

    Set OMERO_TEST_REQUIRE_SERVER=1 (as CI does) to fail instead, so a server that
    never came up can't turn the job green by skipping every test.
    """
    _user, _password, host, port, _secure = omero_params
    try:
        socket.create_connection((host, int(port)), timeout=2).close()
    except OSError:
        msg = f"no OMERO server reachable at {host}:{port}"
        if os.environ.get("OMERO_TEST_REQUIRE_SERVER"):
            pytest.fail(msg)
        pytest.skip(msg)


@pytest.fixture(scope="session")
def conn(omero_params):
    user, password, host, port, secure = omero_params
    # a freshly started server can accept connections before logins work,
    # so retry a few times before giving up
    for attempt in range(5):
        conn = BlitzGateway(user, password, host=host, port=port, secure=secure)
        if conn.connect():
            break
        time.sleep(2 * (attempt + 1))
    else:
        pytest.fail(f"could not log in to OMERO at {host}:{port} as {user}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def users_groups(conn, omero_params):
    """Create the test groups and users (as the admin); return their ids.

    Not used yet; for tests of group switching, owner filters and
    cross-group saves.
    """
    admin, _password, host, port, _secure = omero_params
    login = ["-k", conn.getSession().getUuid().val, "-u", admin, "-s", host]
    login += ["-p", str(port)]
    cli = CLI()
    cli.register("sessions", SessionsControl, "test")
    cli.register("user", UserControl, "test")
    cli.register("group", GroupControl, "test")

    def omero(*args):
        # strict: raise on failure instead of silently continuing
        cli.invoke([*args, *login], strict=True)

    group_info = []
    for gname, gperms in GROUPS_TO_CREATE:
        omero("group", "add", gname, "--type", gperms)
        group_info.append([gname, ezomero.get_group_id(conn, gname)])

    user_info = []
    for username, groups_add, groups_own in USERS_TO_CREATE:
        # make user while adding to first group
        omero(
            "user", "add", username, "test", "tester",
            "--group-name", groups_add[0],
            "-e", "useremail@jax.org", "-P", "abc123",
        )  # fmt: skip
        # add user to rest of groups
        for group in groups_add[1:]:
            omero("group", "adduser", "--user-name", username, "--name", group)
        # make user owner of listed groups
        for group in groups_own:
            omero(
                "group", "adduser", "--user-name", username, "--name", group,
                "--as-owner",
            )  # fmt: skip
        user_info.append([username, ezomero.get_user_id(conn, username)])

    return (group_info, user_info)


@pytest.fixture(scope="session")
def image_array():
    """Small uint16 XYZCT array (ezomero's order) of unique values."""
    shape = (32, 24, 3, 2, 2)  # x, y, z, c, t
    return np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)


@pytest.fixture(scope="session")
def image_id(conn, image_array):
    """Post `image_array` to OMERO as a new image; delete it afterwards."""
    image_id = ezomero.post_image(conn, image_array, "napari-omero test image")
    yield image_id
    conn.deleteObjects("Image", [image_id], deleteAnns=True, wait=True)
