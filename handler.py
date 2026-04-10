# TODO:
# - [ ] All on_... methods should call operators (to better handle undo, to have reporting be visible in the ui, etc)
from collections import defaultdict
from enum import Enum

import bpy
import mathutils
import numpy as np


class PlasticityIdUniquenessScope(Enum):
    ITEM = 0
    GROUP = 1
    EMPTY = 2


class ObjectType(Enum):
    SOLID = 0
    SHEET = 1
    WIRE = 2
    GROUP = 5
    EMPTY = 6


KIND_MESH = 0
KIND_SUBD = 1

class SceneHandler:
    def __init__(self):
        # NOTE: filename -> [item/group] -> id -> object
        # NOTE: items/groups have overlapping ids
        # NOTE: it turns out that caching this is unsafe with undo/redo; call __prepare() before every update
        self.files = {}
        self.client = None

    def __create_mesh(self, name, verts, indices, normals, groups, face_ids):
        mesh = bpy.data.meshes.new(name)
        mesh.vertices.add(len(verts) // 3)
        mesh.vertices.foreach_set("co", verts)
        mesh.loops.add(len(indices))
        mesh.loops.foreach_set("vertex_index", indices)
        mesh.polygons.add(len(indices) // 3)
        mesh.polygons.foreach_set("loop_total", np.full(
            len(indices) // 3, 3, dtype=np.int32))
        mesh.polygons.foreach_set("loop_start", np.arange(
            0, len(indices), 3, dtype=np.int32))

        # NOTE: As of blender 4.2, the concrete type of user attributes cannot be numpy arrays.
        assert isinstance(groups, list)
        assert isinstance(face_ids, list)
        safe_mesh_import_data(mesh, indices, normals, groups, face_ids)

        return mesh

    def __update_object_and_mesh(self, obj, object_type, version, name, verts, indices, normals, groups, face_ids):
        if obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        obj.name = name

        mesh = obj.data
        mesh.clear_geometry()

        mesh.vertices.add(len(verts) // 3)
        mesh.vertices.foreach_set("co", verts)

        mesh.loops.add(len(indices))
        mesh.loops.foreach_set("vertex_index", indices)

        mesh.polygons.add(len(indices) // 3)
        mesh.polygons.foreach_set("loop_start", range(0, len(indices), 3))
        mesh.polygons.foreach_set("loop_total", [3] * (len(indices) // 3))

        # NOTE: As of blender 4.2, the concrete type of user attributes cannot be numpy arrays.
        assert isinstance(groups, list)
        assert isinstance(face_ids, list)
        safe_mesh_import_data(mesh, indices, normals, groups, face_ids)

    def __update_mesh_ngons(self, obj, version, faces, verts, indices, normals, groups, face_ids):
        if obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh = obj.data
        mesh.clear_geometry()

        verts_array = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
        indices = np.asarray(indices, dtype=np.int32)
        unique_verts, inverse_indices = np.unique(
            verts_array, axis=0, return_inverse=True)
        new_indices = inverse_indices[indices].astype(np.int32, copy=False)
        indices, new_indices, loop_total, groups, face_ids, removed_corners, dropped_polygons = sanitize_deduped_polygons(
            indices,
            new_indices,
            faces,
            groups,
            face_ids,
        )

        mesh.vertices.add(len(unique_verts))
        mesh.vertices.foreach_set("co", unique_verts.ravel())

        mesh.loops.add(len(indices))
        mesh.loops.foreach_set("vertex_index", new_indices)

        if len(loop_total):
            loop_start = np.concatenate((
                np.array([0], dtype=np.int32),
                np.cumsum(loop_total[:-1], dtype=np.int32),
            ))
            mesh.polygons.add(len(loop_start))
            mesh.polygons.foreach_set("loop_start", loop_start)
            mesh.polygons.foreach_set("loop_total", loop_total)

        # NOTE: As of blender 4.2, the concrete type of user attributes cannot be numpy arrays.
        assert isinstance(groups, list)
        assert isinstance(face_ids, list)
        safe_mesh_import_data(mesh, indices, normals, groups, face_ids)

    def __add_object(self, filename, object_type, plasticity_id, name, mesh):
        mesh_obj = bpy.data.objects.new(name, mesh)
        self.files[filename][PlasticityIdUniquenessScope.ITEM][plasticity_id] = mesh_obj
        mesh_obj["plasticity_id"] = plasticity_id
        mesh_obj["plasticity_filename"] = filename
        return mesh_obj

    def __delete_object(self, filename, version, plasticity_id):
        obj = self.files[filename][PlasticityIdUniquenessScope.ITEM].pop(
            plasticity_id, None)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    def __delete_group(self, filename, version, plasticity_id):
        group = self.files[filename][PlasticityIdUniquenessScope.GROUP].pop(
            plasticity_id, None)
        if group:
            bpy.data.collections.remove(group, do_unlink=True)

    def __get_outbox_plasticity_ids(self, filename):
        outbox_collection = self.__outbox_for_filename(filename)
        outbox_ids = set()

        def gather_ids(collection):
            for obj in collection.objects:
                pid = obj.get("plasticity_id")
                if pid:
                    outbox_ids.add(pid)
            for child in collection.children:
                gather_ids(child)

        gather_ids(outbox_collection)
        return outbox_ids

    def __replace_objects(self, filename, inbox_collection, version, objects):
        scene = bpy.context.scene
        prop_plasticity_unit_scale = scene.prop_plasticity_unit_scale

        outbox_ids = self.__get_outbox_plasticity_ids(filename)

        collections_to_unlink = set()

        for item in objects:
            object_type = item['type']
            name = item['name']
            plasticity_id = item['id']
            material_id = item['material_id']
            parent_id = item['parent_id']
            flags = item['flags']
            verts = item['vertices']
            faces = item['faces']
            normals = item['normals']
            groups = item['groups']
            face_ids = item['face_ids']

            if plasticity_id in outbox_ids:
                continue

            if object_type == ObjectType.SOLID.value or object_type == ObjectType.SHEET.value:
                obj = None
                if plasticity_id not in self.files[filename][PlasticityIdUniquenessScope.ITEM]:
                    mesh = self.__create_mesh(
                        name, verts, faces, normals, groups, face_ids)
                    obj = self.__add_object(filename, object_type,
                                            plasticity_id, name, mesh)
                    obj.scale = (prop_plasticity_unit_scale,
                                 prop_plasticity_unit_scale, prop_plasticity_unit_scale)
                else:
                    obj = self.files[filename][PlasticityIdUniquenessScope.ITEM].get(
                        plasticity_id)
                    if obj:
                        self.__update_object_and_mesh(
                            obj, object_type, version, name, verts, faces, normals, groups, face_ids)
                        for parent in obj.users_collection:
                            parent.objects.unlink(obj)

            elif object_type == ObjectType.GROUP.value:
                if plasticity_id > 0:
                    group_collection = None
                    if plasticity_id not in self.files[filename][PlasticityIdUniquenessScope.GROUP]:
                        group_collection = bpy.data.collections.new(name)
                        group_collection["plasticity_id"] = plasticity_id
                        group_collection["plasticity_filename"] = filename
                        self.files[filename][PlasticityIdUniquenessScope.GROUP][plasticity_id] = group_collection
                    else:
                        group_collection = self.files[filename][PlasticityIdUniquenessScope.GROUP].get(
                            plasticity_id)
                        group_collection.name = name
                        collections_to_unlink.add(group_collection)


        # Unlink all mirrored collections, in case they have moved. It doesn't seem like there is a more efficient way to do this??
        for potential_parent in bpy.data.collections:
            to_unlink = [
                child for child in potential_parent.children if child in collections_to_unlink]
            for child in to_unlink:
                potential_parent.children.unlink(child)

        for item in objects:
            object_type = item['type']
            uniqueness_scope = PlasticityIdUniquenessScope.ITEM if object_type != ObjectType.GROUP.value else PlasticityIdUniquenessScope.GROUP
            plasticity_id = item['id']
            parent_id = item['parent_id']
            flags = item['flags']
            is_hidden = flags & 1
            is_visible = flags & 2
            is_selectable = flags & 4

            if plasticity_id == 0:  # root group
                continue

            if plasticity_id in outbox_ids:
                continue

            obj = self.files[filename][uniqueness_scope].get(
                plasticity_id)
            if not obj:
                self.report(
                    {'ERROR'}, "Object of type {} with id {} and parent_id {} not found".format(
                        object_type, plasticity_id, parent_id))
                continue

            parent = inbox_collection if parent_id == 0 else self.files[filename][PlasticityIdUniquenessScope.GROUP].get(
                parent_id)
            if not parent:
                self.report(
                    {'ERROR'}, "Parent of object of type {} with id {} and parent_id {} not found".format(
                        object_type, plasticity_id, parent_id))
                continue

            if object_type == ObjectType.GROUP.value:
                parent.children.link(obj)
                group_collection.hide_viewport = is_hidden or not is_visible
                group_collection.hide_select = not is_selectable
            else:
                parent.objects.link(obj)
                obj.hide_set(is_hidden or not is_visible)
                obj.hide_select = not is_selectable

    def __inbox_for_filename(self, filename):
        plasticity_collection = bpy.data.collections.get("Plasticity")
        if not plasticity_collection:
            plasticity_collection = bpy.data.collections.new("Plasticity")
            bpy.context.scene.collection.children.link(plasticity_collection)

        filename_collection = plasticity_collection.children.get(filename)
        if not filename_collection:
            filename_collection = bpy.data.collections.new(filename)
            plasticity_collection.children.link(filename_collection)

        inbox_collections = [
            child for child in filename_collection.children if "inbox" in child]
        inbox_collection = None
        if len(inbox_collections) > 0:
            inbox_collection = inbox_collections[0]
        if not inbox_collection:
            inbox_collection = bpy.data.collections.new("Inbox")
            filename_collection.children.link(inbox_collection)
            inbox_collection["inbox"] = True
        return inbox_collection

    def __outbox_for_filename(self, filename):
        plasticity_collection = bpy.data.collections.get("Plasticity")
        if not plasticity_collection:
            plasticity_collection = bpy.data.collections.new("Plasticity")
            bpy.context.scene.collection.children.link(plasticity_collection)

        filename_collection = plasticity_collection.children.get(filename)
        if not filename_collection:
            filename_collection = bpy.data.collections.new(filename)
            plasticity_collection.children.link(filename_collection)

        outbox_collections = [
            child for child in filename_collection.children if "outbox" in child]
        outbox_collection = None
        if len(outbox_collections) > 0:
            outbox_collection = outbox_collections[0]
        if not outbox_collection:
            outbox_collection = bpy.data.collections.new("Outbox")
            filename_collection.children.link(outbox_collection)
            outbox_collection["outbox"] = True
        return outbox_collection

    def __put_export_data_for_object(self, obj):
        if obj.mode == 'EDIT':
            obj.update_from_editmode()

        modifier_states = [(mod, mod.show_viewport) for mod in obj.modifiers]
        subsurf_modifier = next(
            (mod for mod, show_viewport in modifier_states if mod.type == 'SUBSURF' and show_viewport),
            None,
        )
        disable_from_here = False
        evaluated_obj = None
        mesh = None
        options = KIND_MESH

        try:
            if subsurf_modifier:
                options = KIND_SUBD
                if subsurf_modifier.boundary_smooth == 'ALL':
                    options |= (1 << 8)
                if obj.get("pns_merge_patches", True):
                    options |= (1 << 9)
                if obj.get("pns_interpolate_boundary", False):
                    options |= (1 << 10)

            # Export the visible evaluated stack, but stop before the first
            # viewport-visible subdivision modifier so Plasticity gets the cage
            # for the single SUBD stage it can represent.
            for mod, _ in modifier_states:
                if disable_from_here or mod == subsurf_modifier:
                    mod.show_viewport = False
                    disable_from_here = True

            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = obj.evaluated_get(depsgraph)
            mesh = evaluated_obj.to_mesh()
            if mesh is None:
                return None

            positions = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", positions)

            matrix = np.array(obj.matrix_world)
            positions = positions.reshape(-1, 3)
            positions = (positions @ matrix[:3, :3].T + matrix[:3, 3]).flatten().astype(np.float32)

            indices = []
            sizes = []
            for poly in mesh.polygons:
                sizes.append(poly.loop_total)
                for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    indices.append(mesh.loops[loop_idx].vertex_index)

            return {
                "options": options,
                "positions": positions,
                "indices": np.array(indices, dtype=np.uint32),
                "sizes": np.array(sizes, dtype=np.uint32),
            }
        finally:
            if evaluated_obj is not None and mesh is not None:
                evaluated_obj.to_mesh_clear()

            for mod, show_viewport in modifier_states:
                mod.show_viewport = show_viewport
            bpy.context.view_layer.update()

    def get_outbox_data(self, filename, only_visible=False):
        outbox_collection = self.__outbox_for_filename(filename)
        groups = []
        items = []

        def gather_collections(collection, parent_blender_collection_id=""):
            blender_collection_id = collection.get("blender_collection_id")
            if not blender_collection_id:
                blender_collection_id = str(id(collection))
                collection["blender_collection_id"] = blender_collection_id

            if collection != outbox_collection:
                groups.append({
                    "blender_collection_id": blender_collection_id,
                    "name": collection.name,
                    "parent_blender_collection_id": parent_blender_collection_id,
                    "existing_group_id": collection.get("plasticity_group_id", 0),
                })

            current_parent_id = "" if collection == outbox_collection else blender_collection_id

            for obj in collection.objects:
                if obj.type != 'MESH':
                    continue

                if only_visible and not obj.visible_get():
                    continue

                export_data = self.__put_export_data_for_object(obj)
                if export_data is None:
                    self.report({'WARNING'}, f"Object '{obj.name}' could not be converted to a mesh, skipping")
                    continue

                blender_id = obj.get("blender_pns_id")
                if not blender_id:
                    blender_id = str(id(obj))
                    obj["blender_pns_id"] = blender_id

                items.append({
                    "blender_id": blender_id,
                    "name": obj.name,
                    "parent_blender_collection_id": current_parent_id,
                    "existing_stable_id": obj.get("plasticity_id", 0),
                    **export_data,
                })

            for child in collection.children:
                gather_collections(child, current_parent_id)

        gather_collections(outbox_collection)
        return {"groups": groups, "items": items}

    def __prepare(self, filename):
        inbox_collection = self.__inbox_for_filename(filename)
        self.__outbox_for_filename(filename)

        def gather_items(collection):
            objects = list(collection.objects)
            collections = list(collection.children)
            for sub_collection in collection.children:
                subobjects, subcollections = gather_items(sub_collection)
                objects.extend(subobjects)
                collections.extend(subcollections)
            return objects, collections
        objects, collections = gather_items(inbox_collection)

        existing_objects = {
            PlasticityIdUniquenessScope.ITEM: {},
            PlasticityIdUniquenessScope.GROUP: {}
        }
        for obj in objects:
            if "plasticity_id" not in obj:
                continue
            plasticity_filename = obj.get("plasticity_filename")
            plasticity_id = obj.get("plasticity_id")
            if plasticity_id:
                existing_objects[PlasticityIdUniquenessScope.ITEM][plasticity_id] = obj
        for collection in collections:
            if "plasticity_id" not in collection:
                continue
            plasticity_id = collection.get("plasticity_id")
            if plasticity_id:
                existing_objects[PlasticityIdUniquenessScope.GROUP][plasticity_id] = collection

        self.files[filename] = existing_objects

        return inbox_collection

    def on_transaction(self, transaction):
        bpy.context.window_manager.plasticity_busy = False

        filename = transaction["filename"]
        version = transaction["version"]

        self.report({'INFO'}, "Updating " + filename +
                    " to version " + str(version))
        bpy.ops.ed.undo_push(message="Plasticity update")

        inbox_collection = self.__prepare(filename)

        if "delete" in transaction:
            for plasticity_id in transaction["delete"]:
                self.__delete_object(filename, version, plasticity_id)

        if "add" in transaction:
            self.__replace_objects(filename, inbox_collection,
                                   version, transaction["add"])

        if "update" in transaction:
            self.__replace_objects(filename, inbox_collection,
                                   version, transaction["update"])

        bpy.ops.ed.undo_push(message="/Plasticity update")

    def on_list(self, message):
        bpy.context.window_manager.plasticity_busy = False

        filename = message["filename"]
        version = message["version"]

        self.report({'INFO'}, "Updating " + filename +
                    " to version " + str(version))
        bpy.ops.ed.undo_push(message="Plasticity update")

        if self.client and self.client.on_list_complete:
            self.client.on_list_complete(filename)
            self.client.on_list_complete = None

        inbox_collection = self.__prepare(filename)

        all_items = set()
        all_groups = set()
        if "add" in message:
            for item in message["add"]:
                if item["type"] == ObjectType.GROUP.value:
                    all_groups.add(item["id"])
                else:
                    all_items.add(item["id"])
            self.__replace_objects(filename, inbox_collection,
                                   version, message["add"])

        to_delete = []
        for plasticity_id, obj in self.files[filename][PlasticityIdUniquenessScope.ITEM].items():
            if plasticity_id not in all_items:
                to_delete.append(plasticity_id)
        for plasticity_id in to_delete:
            self.__delete_object(filename, version, plasticity_id)

        to_delete = []
        for plasticity_id, obj in self.files[filename][PlasticityIdUniquenessScope.GROUP].items():
            if plasticity_id not in all_groups:
                to_delete.append(plasticity_id)
        for plasticity_id in to_delete:
            self.__delete_group(filename, version, plasticity_id)

        bpy.ops.ed.undo_push(message="/Plasticity update")

    def on_refacet(self, filename, version, plasticity_ids, versions, faces, positions, indices, normals, groups, face_ids):
        bpy.context.window_manager.plasticity_busy = False

        self.report({'INFO'}, "Refaceting " + filename +
                    " to version " + str(version))
        bpy.ops.ed.undo_push(message="Plasticity refacet")

        self.__prepare(filename)

        prev_obj_mode = bpy.context.object.mode if bpy.context.object else None
        prev_active_object = bpy.context.view_layer.objects.active
        prev_selected_objects = bpy.context.selected_objects

        for i in range(len(plasticity_ids)):
            plasticity_id = plasticity_ids[i]
            version = versions[i]
            face = faces[i] if len(faces) > 0 else None
            position = positions[i]
            index = indices[i]
            normal = normals[i]
            group = groups[i]
            face_id = face_ids[i]

            obj = self.files[filename][PlasticityIdUniquenessScope.ITEM].get(
                plasticity_id)
            if obj:
                self.__update_mesh_ngons(
                    obj, version, face, position, index, normal, group, face_id)

        bpy.context.view_layer.objects.active = prev_active_object
        for obj in prev_selected_objects:
            obj.select_set(True)
        if prev_obj_mode:
            bpy.ops.object.mode_set(mode=prev_obj_mode)

        bpy.ops.ed.undo_push(message="/Plasticity refacet")

    def on_new_version(self, filename, version):
        self.report({'INFO'}, "New version of " +
                    filename + " available: " + str(version))

    def on_new_file(self, filename):
        self.report({'INFO'}, "New file available: " + filename)

    def on_connect(self):
        bpy.context.window_manager.plasticity_busy = False

        self.files = {}

    def on_disconnect(self):
        bpy.context.window_manager.plasticity_busy = False

        self.files = {}

    def on_put_some(self, code, group_results, item_results):
        bpy.context.window_manager.plasticity_busy = False

        if code != 200:
            return

        for item in item_results:
            blender_id = item["blender_id"]
            stable_id = item["stable_id"]
            version_id = item["version_id"]

            for obj in bpy.data.objects:
                if obj.get("blender_pns_id") == blender_id:
                    obj["plasticity_id"] = stable_id
                    obj["plasticity_version"] = version_id
                    break

        for group in group_results:
            blender_collection_id = group["blender_collection_id"]
            group_id = group["group_id"]

            for collection in bpy.data.collections:
                if collection.get("blender_collection_id") == blender_collection_id:
                    collection["plasticity_group_id"] = group_id
                    break

    def on_handshake(self, supported_messages):
        self.report({'INFO'}, f"Server supports: {supported_messages}")

    def report(self, level, message):
        print(message)

def safe_mesh_import_data(mesh, indices, normals, groups, face_ids):
    if len(mesh.polygons) == 0 or len(indices) == 0 or len(face_ids) == 0:
        mesh.update()
        mesh["groups"] = []
        mesh["face_ids"] = []
        return

    original_groups = groups
    original_face_ids = face_ids
    original_polygon_count = len(mesh.polygons)
    loop_normals = np.ascontiguousarray(normals.reshape(-1, 3)[indices], dtype=np.float32)
    mesh.attributes.new("temp_custom_normals", 'FLOAT_VECTOR', 'CORNER')
    mesh.attributes["temp_custom_normals"].data.foreach_set(
        "vector",
        loop_normals.ravel(),
    )

    mesh.attributes.new("temp_group_index", 'INT', 'FACE')

    polygon_group_ids = np.empty(len(mesh.polygons), dtype=np.int32)

    group_idx = 0
    group_start = groups[0]
    group_count = groups[1]

    for poly in mesh.polygons:
        while group_idx + 1 < len(face_ids) and poly.loop_start >= group_start + group_count:
            group_idx += 1
            group_start = groups[group_idx * 2]
            group_count = groups[group_idx * 2 + 1]

        polygon_group_ids[poly.index] = group_idx

    mesh.attributes["temp_group_index"].data.foreach_set("value", polygon_group_ids)

    mesh.update()

    collapsed = original_polygon_count - len(mesh.polygons)

    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    if collapsed == 0:
        mesh.normals_split_custom_set(loop_normals.tolist())
    else:
        buf = np.empty(len(mesh.loops) * 3, dtype=np.float32)
        mesh.attributes["temp_custom_normals"].data.foreach_get("vector", buf)
        remapped_loop_normals = np.ascontiguousarray(buf.reshape(-1, 3), dtype=np.float32)
        mesh.normals_split_custom_set(remapped_loop_normals.tolist())
    mesh.attributes.remove(mesh.attributes["temp_custom_normals"])

    if collapsed == 0:
        mesh["groups"] = original_groups
        mesh["face_ids"] = original_face_ids
        mesh.attributes.remove(mesh.attributes["temp_group_index"])
        return

    if len(mesh.polygons) == 0:
        mesh["groups"] = []
        mesh["face_ids"] = []
        mesh.attributes.remove(mesh.attributes["temp_group_index"])
        return

    polygon_group_ids = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.attributes["temp_group_index"].data.foreach_get("value", polygon_group_ids)

    groups = []
    face_ids = []
    current_group_idx = None
    current_group_start = 0
    current_group_count = 0

    for poly, group_idx in zip(mesh.polygons, polygon_group_ids):
        group_idx = int(group_idx)

        if current_group_idx is None or group_idx != current_group_idx:
            if current_group_idx is not None:
                groups.extend([current_group_start, current_group_count])
                face_ids.append(original_face_ids[current_group_idx])

            current_group_idx = group_idx
            current_group_start = poly.loop_start
            current_group_count = 0

        current_group_count += poly.loop_total

    groups.extend([current_group_start, current_group_count])
    face_ids.append(original_face_ids[current_group_idx])

    mesh["groups"] = groups
    mesh["face_ids"] = face_ids
    mesh.attributes.remove(mesh.attributes["temp_group_index"])


# blender, unlike opengl, does NOT just use unique positions for deduplication.
# the rules allow and sometimes require duplicate positions on the same face for example.
def sanitize_deduped_polygons(indices, new_indices, faces, groups, face_ids):
    if len(faces) == 0:
        loop_start = np.arange(0, len(indices), 3, dtype=np.int32)
        loop_total = np.full(len(indices) // 3, 3, dtype=np.int32)
    else:
        faces = np.asarray(faces, dtype=np.int32)
        diffs = np.where(np.diff(faces))[0] + 1
        loop_start = np.insert(diffs, 0, 0).astype(np.int32, copy=False)
        loop_total = np.append(
            np.diff(loop_start),
            [len(faces) - loop_start[-1]],
        ).astype(np.int32, copy=False)

    filtered_indices = []
    filtered_new_indices = []
    filtered_loop_total = []
    filtered_group_ids = []
    removed_corners = 0
    dropped_polygons = 0

    group_idx = 0
    group_start = groups[0] if groups else 0
    group_count = groups[1] if groups else 0

    for poly_loop_start, poly_loop_total in zip(loop_start, loop_total):
        while group_idx + 1 < len(face_ids) and poly_loop_start >= group_start + group_count:
            group_idx += 1
            group_start = groups[group_idx * 2]
            group_count = groups[group_idx * 2 + 1]

        poly_indices = indices[poly_loop_start:poly_loop_start + poly_loop_total]
        poly_new_indices = new_indices[poly_loop_start:poly_loop_start + poly_loop_total]

        kept_indices = []
        kept_new_indices = []
        seen = set()

        for original_index, deduped_index in zip(poly_indices, poly_new_indices):
            deduped_index = int(deduped_index)
            if deduped_index in seen:
                removed_corners += 1
                continue
            seen.add(deduped_index)
            kept_indices.append(int(original_index))
            kept_new_indices.append(deduped_index)

        if len(kept_new_indices) < 3:
            dropped_polygons += 1
            continue

        filtered_indices.extend(kept_indices)
        filtered_new_indices.extend(kept_new_indices)
        filtered_loop_total.append(len(kept_new_indices))
        filtered_group_ids.append(group_idx)

    rebuilt_groups = []
    rebuilt_face_ids = []
    current_group_idx = None
    current_group_start = 0
    current_group_count = 0
    loop_offset = 0

    for poly_loop_total, poly_group_idx in zip(filtered_loop_total, filtered_group_ids):
        if current_group_idx is None or poly_group_idx != current_group_idx:
            if current_group_idx is not None:
                rebuilt_groups.extend([current_group_start, current_group_count])
                rebuilt_face_ids.append(face_ids[current_group_idx])
            current_group_idx = poly_group_idx
            current_group_start = loop_offset
            current_group_count = 0

        current_group_count += poly_loop_total
        loop_offset += poly_loop_total

    if current_group_idx is not None:
        rebuilt_groups.extend([current_group_start, current_group_count])
        rebuilt_face_ids.append(face_ids[current_group_idx])

    return (
        np.asarray(filtered_indices, dtype=np.int32),
        np.asarray(filtered_new_indices, dtype=np.int32),
        np.asarray(filtered_loop_total, dtype=np.int32),
        rebuilt_groups,
        rebuilt_face_ids,
        removed_corners,
        dropped_polygons,
    )
