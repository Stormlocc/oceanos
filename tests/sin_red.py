"""Las pruebas no usan la red: toda conexión que no sea local falla de inmediato.

Un test que por error llegue a un proveedor real (CDSE, USGS, WorldCover) falla con un mensaje
claro en vez de descargar o quedarse colgado. Se importa `setUpModule` y `tearDownModule` en
cada módulo de pruebas.
"""
import socket

LOCAL = ('127.0.0.1', '::1', 'localhost')
_connect = socket.socket.connect


def local_only(sock, address):
    """connect que solo admite sockets Unix y el propio equipo."""
    host = address[0] if isinstance(address, tuple) else address
    if sock.family == socket.AF_UNIX or host in LOCAL:
        return _connect(sock, address)
    raise OSError(f'Red bloqueada en las pruebas: {host}')


def setUpModule():
    socket.socket.connect = local_only


def tearDownModule():
    socket.socket.connect = _connect
