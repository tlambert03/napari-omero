# This code is derived from the conftest.py file from the ezomero library,
# which is licensed under the GNU General Public License v2.0 as published by
# the Free Software Foundation.
#
# Copyright (c) 2020-2025, Erick Ratamero, Dave Mellert, and contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# For the original code, please see:
# https://github.com/erickmartins/ezomero
import os
import subprocess

import ezomero
import numpy as np
import pytest

from omero.cli import CLI
from omero.gateway import BlitzGateway
from omero.plugins.group import GroupControl
from omero.plugins.sessions import SessionsControl
from omero.plugins.user import UserControl

# Settings for OMERO
DEFAULT_OMERO_USER = "root"
DEFAULT_OMERO_PASS = "omero"
DEFAULT_OMERO_HOST = "localhost"
DEFAULT_OMERO_WEB_HOST = "http://localhost:5080"
DEFAULT_OMERO_PORT = "6064"
DEFAULT_OMERO_SECURE = 1

# [[group, permissions], ...]
GROUPS_TO_CREATE = [["test_group_1", "read-only"], ["test_group_2", "read-only"]]

# [[user, [groups to be added to], [groups to own]], ...]
USERS_TO_CREATE = [
    ["test_user1", ["test_group_1", "test_group_2"], ["test_group_1"]],
    ["test_user2", ["test_group_1", "test_group_2"], ["test_group_2"]],
    ["test_user3", ["test_group_2"], []],
]


def pytest_addoption(parser):
    parser.addoption(
        "--omero-user",
        action="store",
        default=os.environ.get("OMERO_USER", DEFAULT_OMERO_USER),
    )
    parser.addoption(
        "--omero-pass",
        action="store",
        default=os.environ.get("OMERO_PASS", DEFAULT_OMERO_PASS),
    )
    parser.addoption(
        "--omero-host",
        action="store",
        default=os.environ.get("OMERO_HOST", DEFAULT_OMERO_HOST),
    )
    parser.addoption(
        "--omero-web-host",
        action="store",
        default=os.environ.get("OMERO_WEB_HOST", DEFAULT_OMERO_WEB_HOST),
    )
    parser.addoption(
        "--omero-port",
        action="store",
        default=os.environ.get("OMERO_PORT", DEFAULT_OMERO_PORT),
    )
    parser.addoption(
        "--omero-secure",
        action="store",
        default=bool(os.environ.get("OMERO_SECURE", DEFAULT_OMERO_SECURE)),
    )


# we can change this later
@pytest.fixture(scope="session")
def omero_params(request):
    user = request.config.getoption("--omero-user")
    password = request.config.getoption("--omero-pass")
    host = request.config.getoption("--omero-host")
    web_host = request.config.getoption("--omero-web-host")
    port = request.config.getoption("--omero-port")
    secure = request.config.getoption("--omero-secure")
    return (user, password, host, web_host, port, secure)


@pytest.fixture(scope="session")
def users_groups(conn, omero_params):
    session_uuid = conn.getSession().getUuid().val
    user = omero_params[0]
    host = omero_params[2]
    port = str(omero_params[4])
    cli = CLI()
    cli.register("sessions", SessionsControl, "test")
    cli.register("user", UserControl, "test")
    cli.register("group", GroupControl, "test")

    group_info = []
    for gname, gperms in GROUPS_TO_CREATE:
        cli.invoke(
            [
                "group",
                "add",
                gname,
                "--type",
                gperms,
                "-k",
                session_uuid,
                "-u",
                user,
                "-s",
                host,
                "-p",
                port,
            ]
        )
        gid = ezomero.get_group_id(conn, gname)
        group_info.append([gname, gid])

    user_info = []
    for user, groups_add, groups_own in USERS_TO_CREATE:
        # make user while adding to first group
        cli.invoke(
            [
                "user",
                "add",
                user,
                "test",
                "tester",
                "--group-name",
                groups_add[0],
                "-e",
                "useremail@jax.org",
                "-P",
                "abc123",
                "-k",
                session_uuid,
                "-u",
                user,
                "-s",
                host,
                "-p",
                port,
            ]
        )

        # add user to rest of groups
        if len(groups_add) > 1:
            for group in groups_add[1:]:
                cli.invoke(
                    [
                        "group",
                        "adduser",
                        "--user-name",
                        user,
                        "--name",
                        group,
                        "-k",
                        session_uuid,
                        "-u",
                        user,
                        "-s",
                        host,
                        "-p",
                        port,
                    ]
                )

        # make user owner of listed groups
        if len(groups_own) > 0:
            for group in groups_own:
                cli.invoke(
                    [
                        "group",
                        "adduser",
                        "--user-name",
                        user,
                        "--name",
                        group,
                        "--as-owner",
                        "-k",
                        session_uuid,
                        "-u",
                        user,
                        "-s",
                        host,
                        "-p",
                        port,
                    ]
                )
        uid = ezomero.get_user_id(conn, user)
        user_info.append([user, uid])

    return (group_info, user_info)


@pytest.fixture(scope="session")
def conn(omero_params):
    user, password, host, web_host, port, secure = omero_params
    conn = BlitzGateway(user, password, host=host, port=port, secure=secure)
    conn.connect()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def image_fixture():
    test_image = np.zeros((200, 201, 20, 3, 1), dtype=np.uint8)
    test_image[0:100, 0:100, 0:10, 0, :] = 255
    test_image[0:100, 0:100, 11:20, 1, :] = 255
    test_image[101:200, 101:201, :, 2, :] = 255
    return test_image


@pytest.fixture(scope="session")
def pyramid_fixture(conn, omero_params):
    session_uuid = conn.getSession().getUuid().val
    user = omero_params[0]
    host = omero_params[2]
    port = str(omero_params[4])
    imp_cmd = [
        "omero",
        "import",
        "tests/data/test_pyramid.ome.tif",
        "-k",
        session_uuid,
        "-u",
        user,
        "-s",
        host,
        "-p",
        port,
    ]
    process = subprocess.Popen(imp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdoutval, stderrval = process.communicate()
