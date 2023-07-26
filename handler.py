from collections import defaultdict
from enum import Enum

import bpy
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


class SceneHandler:
    def __init__(self):
        # NOTE: filename -> [item/group] -> id -> object
        # FIXME: it turns out that caching this is unsafe with undo/redo; for now call __prepare() before every update
        self.files = {}

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

        mesh.update()

        denormalized_normals = np.zeros((len(indices), 3), dtype=np.float32)
        denormalized_normals = normals.reshape(-1, 3)[indices]
        mesh.normals_split_custom_set(denormalized_normals)
        mesh.use_auto_smooth = True

        mesh["groups"] = groups
        mesh["face_ids"] = face_ids
        mesh["normals_split_custom"] = denormalized_normals

        return mesh

    def __update_object(self, obj, object_type, version, name, verts, indices, normals, groups, face_ids):
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

        mesh["groups"] = groups
        mesh["face_ids"] = face_ids

        mesh.update()

        denormalized_normals = np.zeros((len(indices), 3), dtype=np.float32)
        denormalized_normals = normals.reshape(-1, 3)[indices]
        mesh.normals_split_custom_set(denormalized_normals)

    def __update_mesh(self, obj, version, faces, verts, indices, normals, groups, face_ids):
        if obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh = obj.data
        mesh.clear_geometry()

        mesh.vertices.add(len(verts) // 3)
        mesh.vertices.foreach_set("co", verts)

        mesh.loops.add(len(indices))
        mesh.loops.foreach_set("vertex_index", indices)

        if (len(faces) == 0):
            mesh.polygons.add(len(indices) // 3)
            mesh.polygons.foreach_set("loop_start", range(0, len(indices), 3))
            mesh.polygons.foreach_set("loop_total", [3] * (len(indices) // 3))
        else:
            # Find where a new face/polygon starts (value changes in the array)
            diffs = np.where(np.diff(faces))[0] + 1
            # Insert the starting index for the first polygon
            loop_start = np.insert(diffs, 0, 0)
            # Calculate the number of vertices per polygon
            loop_total = np.append(np.diff(loop_start), [
                                   len(faces) - loop_start[-1]])
            mesh.polygons.add(len(loop_start))
            mesh.polygons.foreach_set("loop_start", loop_start)
            mesh.polygons.foreach_set("loop_total", loop_total)

        mesh["groups"] = groups
        mesh["face_ids"] = face_ids

        mesh.update()

        denormalized_normals = np.zeros((len(indices), 3), dtype=np.float32)
        denormalized_normals = normals.reshape(-1, 3)[indices]
        mesh.normals_split_custom_set(denormalized_normals)

        # NOTE: Plasticity currently doesn't merge doubles via this API
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=1e-06)
        bpy.ops.object.mode_set(mode='OBJECT')

    def __add_object(self, to_collection, filename, object_type, plasticity_id, name, mesh):
        mesh_obj = bpy.data.objects.new(name, mesh)
        to_collection.objects.link(mesh_obj)
        self.files[filename][PlasticityIdUniquenessScope.ITEM][plasticity_id] = mesh_obj
        mesh_obj["plasticity_id"] = plasticity_id
        mesh_obj["plasticity_filename"] = filename
        return mesh_obj

    def __delete_object(self, filename, version, plasticity_id):
        obj = self.files[filename][PlasticityIdUniquenessScope.ITEM].pop(
            plasticity_id, None)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    def __replace(self, filename, inbox_collection, version, objects):
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
            is_hidden = flags & 1
            is_visible = flags & 2
            is_selectable = flags & 4

            if object_type == ObjectType.SOLID.value or object_type == ObjectType.SHEET.value:
                obj = None
                if plasticity_id not in self.files[filename][PlasticityIdUniquenessScope.ITEM]:
                    mesh = self.__create_mesh(
                        name, verts, faces, normals, groups, face_ids)
                    obj = self.__add_object(inbox_collection, filename, object_type,
                                            plasticity_id, name, mesh)
                else:
                    obj = self.files[filename][PlasticityIdUniquenessScope.ITEM].get(
                        plasticity_id)
                    if obj:
                        self.__update_object(
                            obj, object_type, version, name, verts, faces, normals, groups, face_ids)

                if obj:
                    obj.hide_set(is_hidden or not is_visible)
                    obj.hide_select = not is_selectable

            elif object_type == ObjectType.GROUP.value:
                if plasticity_id > 0:
                    group_collection = None
                    if plasticity_id not in self.files[filename][PlasticityIdUniquenessScope.GROUP]:
                        group_collection = bpy.data.collections.new(name)
                        group_collection["plasticity_id"] = plasticity_id
                        group_collection["plasticity_filename"] = filename
                        inbox_collection.children.link(group_collection)
                        self.files[filename][PlasticityIdUniquenessScope.GROUP][plasticity_id] = group_collection
                    else:
                        group_collection = self.files[filename][PlasticityIdUniquenessScope.GROUP].get(
                            plasticity_id)
                        group_collection.name = name

                    if group_collection:
                        group_collection.hide_viewport = not is_hidden or not is_visible
                        group_collection.hide_select = not is_selectable

        for item in objects:
            object_type = item['type']
            uniqueness_scope = PlasticityIdUniquenessScope.ITEM
            if object_type == ObjectType.GROUP.value:
                uniqueness_scope = PlasticityIdUniquenessScope.GROUP
            plasticity_id = item['id']
            parent_id = item['parent_id']
            if parent_id > 0:
                parent = self.files[filename][PlasticityIdUniquenessScope.GROUP].get(
                    parent_id)
                if parent:
                    obj = self.files[filename][uniqueness_scope].get(
                        plasticity_id)
                    if obj:
                        if object_type == ObjectType.GROUP.value:
                            parent.children.link(obj)
                        else:
                            parent.objects.link(obj)

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

    def __prepare(self, filename):
        inbox_collection = self.__inbox_for_filename(filename)

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

    def update(self, transaction):
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
            self.__replace(filename, inbox_collection,
                           version, transaction["add"])

        if "update" in transaction:
            self.__replace(filename, inbox_collection,
                           version, transaction["update"])

    def refacet(self, filename, version, plasticity_ids, versions, faces, positions, indices, normals, groups, face_ids):
        self.report({'INFO'}, "Refaceting " + filename +
                    " to version " + str(version))

        self.__prepare(filename)

        prev_obj_mode = bpy.context.object.mode
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
                self.__update_mesh(
                    obj, version, face, position, index, normal, group, face_id)

        bpy.ops.ed.undo_push(message="Plasticity refacet")
        bpy.context.view_layer.objects.active = prev_active_object
        for obj in prev_selected_objects:
            obj.select_set(True)
        bpy.ops.object.mode_set(mode=prev_obj_mode)

    def new_version(self, filename, version):
        self.report({'INFO'}, "New version of " +
                    filename + " available: " + str(version))

    def clear(self):
        self.files = {}

    def report(self, level, message):
        print(message)
