"""Real hbbs protocol regression tests; run against a disposable, isolated server."""
import asyncio
import os
import socket
import unittest
import uuid
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

URL = os.environ.get('HBBS_WS_URL', 'ws://127.0.0.1:21118')
SERVER_KEY = os.environ.get('HBBS_PUBLIC_KEY', '')

def vint(n):
    result = bytearray()
    while n > 127:
        result.append((n & 127) | 128)
        n >>= 7
    result.append(n)
    return bytes(result)

def text(n, value):
    if isinstance(value, str):
        value = value.encode()
    return vint(n * 8 + 2) + vint(len(value)) + value

def read_vint(data, pos):
    result, shift = 0, 0
    while True:
        value = data[pos]
        pos += 1
        result |= (value & 127) << shift
        if value < 128:
            return result, pos
        shift += 7

def fields(data):
    result, pos = {}, 0
    while pos < len(data):
        tag, pos = read_vint(data, pos)
        if tag % 8 == 0:
            value, pos = read_vint(data, pos)
        elif tag % 8 == 2:
            length, pos = read_vint(data, pos)
            value = data[pos:pos + length]
            pos += length
        else:
            raise ValueError('Unexpected wire type')
        result[tag >> 3] = value
    return result

async def message(ws):
    while True:
        data = await asyncio.wait_for(ws.recv(), 20)
        if data:
            return fields(data)
        await ws.send(b'')

async def register(ws, ident, uid, key=b'p' * 32):
    await ws.send(text(15, text(1, ident) + text(2, uid) + text(3, key)))
    return fields((await message(ws))[16])

async def online(ident):
    async with connect(URL) as ws:
        await ws.send(text(23, text(2, ident)))
        response = fields((await message(ws))[24])
        return bool(response[1][0] & 128)

async def deliver(ident, receiver):
    async with connect(URL) as controller:
        request = text(1, ident) + text(3, SERVER_KEY) + text(6, '1.5.0')
        await controller.send(text(8, request))
        ph = fields((await message(receiver))[9])
        await receiver.send(b'')
        # The controlled client answers on a separate rendezvous connection.
        async with connect(URL) as answer:
            await answer.send(text(10, text(1, ph[1]) + text(2, ident) + text(5, '1.5.0')))
        response = fields((await message(controller))[11])
        return response

class Registration(unittest.IsolatedAsyncioTestCase):
    def identity(self):
        return 'qs-' + uuid.uuid4().hex, uuid.uuid4().bytes

    async def test_valid_registration_routing_and_disconnect(self):
        ident, uid = self.identity()
        async with connect(URL) as peer:
            result = await register(peer, ident, uid)
            self.assertEqual(result.get(1, 0), 0)
            self.assertEqual(result[2], 15)
            self.assertTrue(await online(ident))
            self.assertIn(2, await deliver(ident, peer))  # signed peer identity returned
        self.assertFalse(await online(ident))

    async def test_conflicting_uuid_cannot_replace_owner(self):
        ident, uid = self.identity()
        async with connect(URL) as original, connect(URL) as wrong:
            self.assertEqual((await register(original, ident, uid)).get(1, 0), 0)
            self.assertEqual((await register(wrong, ident, b'wrong-uuid'))[1], 2)
            await deliver(ident, original)

    async def test_reconnect_old_disconnect_does_not_expire_replacement(self):
        ident, uid = self.identity()
        async with connect(URL) as replacement:
            old = await connect(URL)
            self.assertEqual((await register(old, ident, uid)).get(1, 0), 0)
            self.assertEqual((await register(replacement, ident, uid)).get(1, 0), 0)
            await old.close()
            self.assertTrue(await online(ident))
            await deliver(ident, replacement)

    async def test_multiple_clients_ignore_spoofed_forwarded_connection_identity(self):
        a, auid = self.identity()
        b, buid = self.identity()
        headers = {'X-Real-IP': '198.51.100.4', 'X-Forwarded-For': '198.51.100.4'}
        async with connect(URL, additional_headers=headers) as aw, connect(URL, additional_headers=headers) as bw:
            await register(aw, a, auid)
            await register(bw, b, buid)
            await deliver(a, aw)
            await deliver(b, bw)

    async def test_invalid_public_key_rejected_without_online_route(self):
        ident, uid = self.identity()
        async with connect(URL) as peer:
            self.assertEqual((await register(peer, ident, uid, b'bad'))[1], 2)
        self.assertFalse(await online(ident))

    async def test_stream_cannot_register_second_identity(self):
        first, uid = self.identity()
        second, other_uid = self.identity()
        async with connect(URL) as peer:
            await register(peer, first, uid)
            await peer.send(text(15, text(1, second) + text(2, other_uid) + text(3, b'p' * 32)))
            with self.assertRaises(ConnectionClosed):
                await message(peer)
        self.assertFalse(await online(first))
        self.assertFalse(await online(second))

    async def test_udp_registration_and_heartbeat_preserved(self):
        ident, uid = self.identity()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.connect(('127.0.0.1', 21116))
        loop = asyncio.get_running_loop()
        try:
            await loop.sock_sendall(sock, text(15, text(1, ident) + text(2, uid) + text(3, b'p' * 32)))
            response = fields(await asyncio.wait_for(loop.sock_recv(sock, 4096), 5))
            self.assertEqual(fields(response[16]).get(1, 0), 0)
            await loop.sock_sendall(sock, text(6, text(1, ident)))
            response = fields(await asyncio.wait_for(loop.sock_recv(sock, 4096), 5))
            self.assertEqual(fields(response[7]).get(2, 0), 0)
        finally:
            sock.close()

    async def test_heartbeat_keeps_registration_online_then_missing_ack_expires(self):
        ident, uid = self.identity()
        async with connect(URL) as peer:
            await register(peer, ident, uid)
            for _ in range(3):
                self.assertEqual(await asyncio.wait_for(peer.recv(), 20), b'')
                await peer.send(b'')
            self.assertTrue(await online(ident))
            # Stop acknowledging binary heartbeats: TCP/WS ping frames aren't endpoint leases.
            with self.assertRaises(ConnectionClosed):
                while True:
                    await asyncio.wait_for(peer.recv(), 55)
        self.assertFalse(await online(ident))

if __name__ == '__main__':
    unittest.main(verbosity=2)
