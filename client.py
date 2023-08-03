import asyncio
import struct
import threading
import weakref
from asyncio import run_coroutine_threadsafe
from enum import Enum

import bpy
import numpy as np

from .libs.websockets import client
from .libs.websockets.exceptions import (ConnectionClosed, InvalidURI,
                                         WebSocketException)

max_size = 2 ** 32 - 1


class MessageType(Enum):
    TRANSACTION_1 = 0
    ADD_1 = 1
    UPDATE_1 = 2
    DELETE_1 = 3
    MOVE_1 = 4
    ATTRIBUTE_1 = 5

    NEW_VERSION_1 = 10
    NEW_FILE_1 = 11

    LIST_ALL_1 = 20
    LIST_SOME_1 = 21
    LIST_VISIBLE_1 = 22
    SUBSCRIBE_ALL_1 = 23
    SUBSCRIBE_SOME_1 = 24
    UNSUBSCRIBE_ALL_1 = 25
    REFACET_SOME_1 = 26


class ObjectType(Enum):
    SOLID = 0
    SHEET = 1
    WIRE = 2
    GROUP = 5
    EMPTY = 6


class FacetShapeType(Enum):
    ANY = 20500
    CUT = 20501
    CONVEX = 20502


class PlasticityClient:
    def __init__(self, handler):
        self.server = None
        self.connected = False
        self.subscribed = False
        self.filename = None
        self.websocket = None
        self.message_id = 0
        self.handler = handler
        self.loop = asyncio.new_event_loop()

    def list_all(self):
        if self.connected:
            self.report({'INFO'}, "Refreshing available meshes...")

            future = run_coroutine_threadsafe(
                self.list_all_async(), self.loop)
            future.result()

    async def list_all_async(self):
        self.message_id += 1

        get_objects_message = struct.pack(
            "<I", MessageType.LIST_ALL_1.value)
        get_objects_message += struct.pack(
            "<I", self.message_id)
        await self.websocket.send(get_objects_message)

    def list_visible(self):
        if self.connected:
            self.report({'INFO'}, "Refreshing visible meshes...")

            future = run_coroutine_threadsafe(
                self.list_visible_async(), self.loop)
            future.result()

    async def list_visible_async(self):
        self.message_id += 1

        get_objects_message = struct.pack(
            "<I", MessageType.LIST_VISIBLE_1.value)
        get_objects_message += struct.pack(
            "<I", self.message_id)
        await self.websocket.send(get_objects_message)

    def subscribe_all(self):
        if self.connected:
            self.report({'INFO'}, "Subscribing to all meshes...")

            future = run_coroutine_threadsafe(
                self.subscribe_all_async(), self.loop)
            future.result()
            self.subscribed = True

    async def subscribe_all_async(self):
        self.message_id += 1

        subscribe_message = struct.pack(
            "<I", MessageType.SUBSCRIBE_ALL_1.value)
        subscribe_message += struct.pack(
            "<I", self.message_id)
        await self.websocket.send(subscribe_message)

    def unsubscribe_all(self):
        if self.connected:
            self.report({'INFO'}, "Unsubscribing to all meshes...")

            future = run_coroutine_threadsafe(
                self.unsubscribe_all_async(), self.loop)
            future.result()
            self.subscribed = False

    async def unsubscribe_all_async(self):
        self.message_id += 1

        subscribe_message = struct.pack(
            "<I", MessageType.UNSUBSCRIBE_ALL_1.value)
        subscribe_message += struct.pack(
            "<I", self.message_id)
        await self.websocket.send(subscribe_message)

    def subscribe_some(self, filename, plasticity_ids):
        if self.connected:
            self.report({'INFO'}, "Subscribing to meshes...")

            future = run_coroutine_threadsafe(
                self.subscribe_some_async(filename, plasticity_ids), self.loop)
            future.result()

    async def subscribe_some_async(self, filename, plasticity_ids):
        if len(plasticity_ids) == 0:
            return

        self.message_id += 1

        subscribe_message = struct.pack(
            "<I", MessageType.SUBSCRIBE_SOME_1.value)
        subscribe_message += struct.pack(
            "<I", self.message_id)
        subscribe_message += struct.pack(
            "<I", len(filename))
        subscribe_message += struct.pack(
            f"<{len(filename)}s", filename.encode('utf-8'))
        padding = (4 - (len(filename) % 4)) % 4
        subscribe_message += struct.pack(
            f"<{padding}x")
        subscribe_message += struct.pack(
            "<I", len(plasticity_ids))
        for plasticity_id in plasticity_ids:
            subscribe_message += struct.pack(
                "<I", plasticity_id)
        await self.websocket.send(subscribe_message)

    def refacet_some(self, filename, plasticity_ids, relative_to_bbox=True, curve_chord_tolerance=0.01, curve_chord_angle=0.35, surface_plane_tolerance=0.01, surface_plane_angle=0.35, match_topology=True, max_sides=3, plane_angle=0, min_width=0, max_width=0, curve_chord_max=0, shape=FacetShapeType.CUT):
        if self.connected:
            self.report({'INFO'}, "Refaceting meshes...")

            future = run_coroutine_threadsafe(
                self.refacet_some_async(filename, plasticity_ids, relative_to_bbox, curve_chord_tolerance, curve_chord_angle, surface_plane_tolerance, surface_plane_angle, match_topology, max_sides, plane_angle, min_width, max_width, curve_chord_max, shape), self.loop)
            future.result()

    async def refacet_some_async(self, filename, plasticity_ids, relative_to_bbox=True, curve_chord_tolerance=0.01, curve_chord_angle=0.35, surface_plane_tolerance=0.01, surface_plane_angle=0.35, match_topology=True, max_sides=3, plane_angle=0, min_width=0, max_width=0, curve_chord_max=0, shape=FacetShapeType.CUT):
        if len(plasticity_ids) == 0:
            return

        self.message_id += 1

        refacet_message = struct.pack(
            "<I", MessageType.REFACET_SOME_1.value)
        refacet_message += struct.pack(
            "<I", self.message_id)
        refacet_message += struct.pack(
            "<I", len(filename))
        refacet_message += struct.pack(
            f"<{len(filename)}s", filename.encode('utf-8'))
        padding = (4 - (len(filename) % 4)) % 4
        refacet_message += struct.pack(
            f"<{padding}x")
        refacet_message += struct.pack(
            "<I", len(plasticity_ids))
        for plasticity_id in plasticity_ids:
            refacet_message += struct.pack(
                "<I", plasticity_id)
        refacet_message += struct.pack(
            "<I", relative_to_bbox)
        refacet_message += struct.pack(
            "<f", curve_chord_tolerance)
        refacet_message += struct.pack(
            "<f", curve_chord_angle)
        refacet_message += struct.pack(
            "<f", surface_plane_tolerance)
        refacet_message += struct.pack(
            "<f", surface_plane_angle)
        refacet_message += struct.pack(
            "<I", 1 if match_topology else 0)
        refacet_message += struct.pack(
            "<I", max_sides)
        refacet_message += struct.pack(
            "<f", plane_angle)
        refacet_message += struct.pack(
            "<f", min_width)
        refacet_message += struct.pack(
            "<f", max_width)
        refacet_message += struct.pack(
            "<f", curve_chord_max)
        refacet_message += struct.pack(
            "<I", shape.value)

        await self.websocket.send(refacet_message)

    def connect(self, server):
        loop = self.loop
        websocket_thread = threading.Thread(
            target=loop.run_until_complete, args=(loop.create_task(self.connect_async(server)),))
        websocket_thread.daemon = True
        websocket_thread.start()

    async def connect_async(self, server):
        self.report({'INFO'}, "Connecting to server: " + server)
        try:
            async with client.connect("ws://" + server, max_size=max_size) as ws:
                self.report({'INFO'}, "Connected to server")
                self.websocket = weakref.proxy(ws)
                self.connected = True
                self.message_id = 0
                self.server = server
                self.handler.on_connect()

                while True:
                    try:
                        self.report({'INFO'}, "Awaiting message")
                        message = await ws.recv()
                        self.report({'INFO'}, "Received message")
                        self.report(
                            {'INFO'}, f"Message length: {len(message)}")
                        await self.on_message(ws, message)
                    except ConnectionClosed as e:
                        self.report(
                            {'INFO'}, f"Disconnected from server: {e}")
                        self.connected = False
                        self.websocket = None
                        self.filename = None
                        self.subscribed = False
                        self.handler.on_disconnect()
                        break
                    except Exception as e:
                        self.report({'ERROR'}, f"Exception: {e}")
        except ConnectionClosed:
            self.report({'INFO'}, "Disconnected from server")
            self.connected = False
            self.websocket = None
            self.filename = None
            self.subscribed = False
            self.handler.on_disconnect()
        except InvalidURI:
            self.report(
                {'ERROR'}, "Invalid URI for the WebSocket server")
        except WebSocketException as e:
            self.report(
                {'ERROR'}, f"Failed to connect to the server: {e}")
        except OSError as e:
            self.report(
                {'ERROR'}, f"Unable to connect to the server: {e}")
        except Exception as e:
            self.report({'ERROR'}, f"Unknown error: {e}")

    async def on_message(self, ws, message):
        view = memoryview(message)
        offset = 0
        message_type = MessageType(
            int.from_bytes(view[offset:offset + 4], 'little'))
        offset += 4

        if message_type == MessageType.TRANSACTION_1:
            self.__on_transaction(view, offset, update_only=True)

        elif message_type == MessageType.LIST_ALL_1 or message_type == MessageType.LIST_SOME_1 or message_type == MessageType.LIST_VISIBLE_1:
            message_id = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            code = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            if code != 200:
                self.report({'ERROR'}, f"List all failed with code: {code}")
                return

            # NOTE: ListAll only has an Add message inside it so it is a bit unlike a regular transaction
            self.__on_transaction(view, offset, update_only=False)

        elif message_type == MessageType.NEW_VERSION_1:
            filename_length = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            filename = view[offset:offset +
                            filename_length].tobytes().decode('utf-8')
            offset += filename_length

            self.filename = filename

            # Add string padding for byte alignment
            padding = (4 - (filename_length % 4)) % 4
            offset += padding

            version = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            bpy.app.timers.register(
                lambda: self.handler.on_new_version(filename, version), first_interval=0.001)

        elif message_type == MessageType.NEW_FILE_1:
            filename_length = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            filename = view[offset:offset +
                            filename_length].tobytes().decode('utf-8')
            offset += filename_length

            self.filename = filename

            bpy.app.timers.register(
                lambda: self.handler.on_new_file(filename), first_interval=0.001)

        elif message_type == MessageType.REFACET_SOME_1:
            self.__on_refacet(view, offset)

    def __on_transaction(self, view, offset, update_only):
        filename_length = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        filename = view[offset:offset +
                        filename_length].tobytes().decode('utf-8')
        offset += filename_length

        self.filename = filename

        # Add string padding for byte alignment
        padding = (4 - (filename_length % 4)) % 4
        offset += padding

        version = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        num_messages = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        self.report({'INFO'}, f"Filename: {filename}")
        self.report({'INFO'}, f"Version: {version}")
        self.report({'INFO'}, f"Num messages: {num_messages}")

        transaction = {"filename": filename, "version": version,
                       "delete": [], "add": [], "update": []}
        for _ in range(num_messages):
            item_length = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            self.on_message_item(
                view[offset:offset + item_length], transaction)
            offset += item_length

        if update_only:
            bpy.app.timers.register(lambda: self.handler.on_transaction(
                transaction), first_interval=0.001)
        else:
            bpy.app.timers.register(lambda: self.handler.on_list(
                transaction), first_interval=0.001)

    def __on_refacet(self, view, offset):
        message_id = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        code = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        if code != 200:
            self.report({'ERROR'}, f"Refacet failed with code: {code}")
            return

        filename_length = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        filename = view[offset:offset +
                        filename_length].tobytes().decode('utf-8')
        offset += filename_length

        self.filename = filename

        # Add string padding for byte alignment
        padding = (4 - (filename_length % 4)) % 4
        offset += padding

        file_version = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        num_items = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        self.report({'INFO'}, f"Message ID: {message_id}")
        self.report({'INFO'}, f"Num items: {num_items}")

        plasticity_ids = []
        versions = []
        faces = []
        positions = []
        indices = []
        normals = []
        groups = []
        face_ids = []

        for _ in range(num_items):
            plasticity_id = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            version = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            num_face_facets = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            face = np.frombuffer(
                view[offset:offset + num_face_facets * 4], dtype=np.int32)
            offset += num_face_facets * 4

            num_positions = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            position = np.frombuffer(
                view[offset:offset + num_positions * 4], dtype=np.float32)
            offset += num_positions * 4

            num_index = int.from_bytes(view[offset:offset + 4], 'little')
            offset += 4

            index = np.frombuffer(
                view[offset:offset + num_index * 4], dtype=np.int32)
            offset += num_index * 4

            num_normals = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            normal = np.frombuffer(
                view[offset:offset + num_normals * 4], dtype=np.float32)
            offset += num_normals * 4

            num_groups = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            group = np.frombuffer(
                view[offset:offset + num_groups * 4], dtype=np.int32)
            offset += num_groups * 4

            num_face_ids = int.from_bytes(
                view[offset:offset + 4], 'little')
            offset += 4

            face_id = np.frombuffer(
                view[offset:offset + num_face_ids * 4], dtype=np.int32)
            offset += num_face_ids * 4

            plasticity_ids.append(plasticity_id)
            versions.append(version)
            faces.append(face)
            positions.append(position)
            indices.append(index)
            normals.append(normal)
            groups.append(group)
            face_ids.append(face_id)

        bpy.app.timers.register(lambda: self.handler.on_refacet(filename, file_version, plasticity_ids,
                                versions, faces, positions, indices, normals, groups, face_ids), first_interval=0.001)

    def on_message_item(self, view, transaction):
        offset = 0
        message_type = MessageType(
            int.from_bytes(view[offset:offset + 4], 'little'))
        offset += 4

        self.report({'INFO'}, f"Message type: {message_type}")

        if message_type == MessageType.DELETE_1:
            num_objects = int.from_bytes(view[:4], 'little')
            offset += 4
            transaction["delete"].extend(
                np.frombuffer(view[offset:offset + num_objects * 4], dtype=np.int32))
        elif message_type == MessageType.ADD_1:
            transaction["add"].extend(decode_objects(view[4:]))
        elif message_type == MessageType.UPDATE_1:
            transaction["update"].extend(decode_objects(view[4:]))

    def disconnect(self):
        if self.connected:
            self.report({'INFO'}, "Closing WebSocket connection...")

            future = run_coroutine_threadsafe(
                self.disconnect_async(), self.loop)
            future.result()
        else:
            self.report({'INFO'}, "Not connected, nothing to disconnect")

    async def disconnect_async(self):
        websocket = self.websocket
        if websocket:
            await websocket.close()
            del self.websocket

        self.connected = False
        self.filename = None
        self.subscribed = False
        self.websocket = None
        self.handler.on_disconnect()
        self.report({'INFO'}, "Disconnected from Plasticity server")
        return {'FINISHED'}

    def report(self, level, message):
        self.handler.report(level, message)


def decode_objects(buffer):
    view = memoryview(buffer)
    num_objects = int.from_bytes(view[:4], 'little')
    offset = 4
    objects = []

    for _ in range(num_objects):
        object_type, object_id, version_id, parent_id, material_id, flags, name, vertices, faces, normals, offset, groups, face_ids = decode_object_data(
            view, offset)
        objects.append({"type": object_type, "id": object_id, "version": version_id, "parent_id": parent_id, "material_id": material_id,
                       "flags": flags, "name": name, "vertices": vertices, "faces": faces, "normals": normals, "groups": groups, "face_ids": face_ids})

    return objects


def decode_object_data(view, offset):
    object_type = int.from_bytes(view[offset:offset + 4], 'little')
    offset += 4

    object_id = int.from_bytes(view[offset:offset + 4], 'little')
    offset += 4

    version_id = int.from_bytes(view[offset:offset + 4], 'little')
    offset += 4

    parent_id = int.from_bytes(view[offset:offset + 4], 'little', signed=True)
    offset += 4

    material_id = int.from_bytes(
        view[offset:offset + 4], 'little', signed=True)
    offset += 4

    flags = int.from_bytes(view[offset:offset + 4], 'little')
    offset += 4

    name_length = int.from_bytes(view[offset:offset + 4], 'little')
    offset += 4

    name = view[offset:offset + name_length].tobytes().decode('utf-8')
    offset += name_length

    # Add string padding for byte alignment
    padding = (4 - (name_length % 4)) % 4
    offset += padding

    vertices = None
    faces = None
    normals = None
    groups = None
    face_ids = None

    if object_type == ObjectType.SOLID.value or object_type == ObjectType.SHEET.value:
        num_vertices = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        vertices = np.frombuffer(
            view[offset:offset + num_vertices * 12], dtype=np.float32)
        offset += num_vertices * 12

        num_faces = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        faces = np.frombuffer(
            view[offset:offset + num_faces * 12], dtype=np.int32)
        offset += num_faces * 12

        num_normals = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        normals = np.frombuffer(
            view[offset:offset + num_normals * 12], dtype=np.float32)
        offset += num_normals * 12

        num_groups = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        groups = np.frombuffer(
            view[offset:offset + num_groups * 4], dtype=np.int32)
        offset += num_groups * 4

        num_face_ids = int.from_bytes(view[offset:offset + 4], 'little')
        offset += 4

        face_ids = np.frombuffer(
            view[offset:offset + num_face_ids * 4], dtype=np.int32)
        offset += num_face_ids * 4

    elif object_type == ObjectType.GROUP.value:
        pass

    return object_type, object_id, version_id, parent_id, material_id, flags, name, vertices, faces, normals, offset, groups, face_ids
