import math
import random

import bmesh
import bpy


class SelectByFaceIDOperator(bpy.types.Operator):
    bl_idname = "mesh.select_by_plasticity_face_id"
    bl_label = "Select by Plasticity Face ID"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        bpy.ops.object.mode_set(mode='EDIT')

        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)

        groups = mesh["groups"]
        if not groups:
            self.report({'ERROR'}, "No groups found")
            return {'CANCELLED'}

        active_face = bm.faces.active
        if not active_face:
            self.report({'ERROR'}, "No active face selected")
            return {'CANCELLED'}

        face_id = active_face.index

        target_group_index = None
        for idx in range(0, len(groups), 2):
            start_idx = groups[idx + 0] // 3
            count = groups[idx + 1] // 3
            if face_id >= start_idx and face_id < (start_idx + count):
                target_group_index = idx
                break

        if target_group_index is None:
            self.report({'ERROR'}, "No group found for face")
            return {'CANCELLED'}

        target_group = groups[target_group_index + 0]
        target_group_count = groups[target_group_index + 1]
        target_group_start = target_group // 3
        target_group_end = target_group_start + (target_group_count // 3)

        for face_idx in range(target_group_start, target_group_end):
            face = bm.faces[face_idx]
            face.select = True

        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}


class MarkSharpEdgesForPlasticityGroupsWithSplitNormalsOperator(bpy.types.Operator):
    bl_idname = "mesh.mark_sharp_edges_for_plasticity_with_split_normals"
    bl_label = "Mark Sharp Edges for Plasticity Groups"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and "plasticity_id" in obj.keys()

    def execute(self, context):
        obj = context.object
        mesh = obj.data

        prev_obj_mode = bpy.context.object.mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=1e-06)
        bpy.ops.object.mode_set(mode='OBJECT')

        if "plasticity_id" not in obj.keys():
            self.report(
                {'ERROR'}, "Object doesn't have a plasticity_id attribute.")
            return {'CANCELLED'}

        groups = mesh["groups"]

        self.mark_sharp_edges(obj, groups)

        bpy.ops.object.mode_set(mode=prev_obj_mode)

        return {'FINISHED'}

    # NOTE: This doesn't really work. It's just a proof of concept.
    def mark_sharp_edges(self, obj, groups):
        mesh = obj.data
        bm = bmesh.new()
        mesh.calc_normals_split()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        loops = mesh.loops

        edge_lookup = {
            (e.verts[0].index, e.verts[1].index): e for e in bm.edges}

        all_face_boundary_edges = set()
        for idx in range(0, len(groups), 2):
            start_idx = groups[idx] // 3
            count = groups[idx + 1] // 3
            end_idx = start_idx + count

            face_boundary_edges = set()
            for face_idx in range(start_idx, end_idx):
                face = bm.faces[face_idx]
                for edge in face.edges:
                    verts = (edge.verts[0].index, edge.verts[1].index)
                    if verts in edge_lookup:
                        if edge in face_boundary_edges:
                            face_boundary_edges.remove(edge)
                        else:
                            face_boundary_edges.add(edge)
            all_face_boundary_edges.update(face_boundary_edges)

        split_edges = set()
        for vert in bm.verts:
            link_loops = vert.link_loops
            for loop1_idx in range(len(link_loops)):
                loop1 = link_loops[loop1_idx]
                for loop2_idx in range(loop1_idx + 1, len(link_loops)):
                    loop2 = link_loops[loop2_idx]
                    normal1 = loops[loop1.index].normal
                    normal2 = loops[loop2.index].normal
                    if are_normals_different(normal1, normal2):
                        split_edges.add(loop1.edge)

        for edge in all_face_boundary_edges:
            if edge in split_edges:
                edge.smooth = False

        bm.to_mesh(obj.data)
        bm.free()


class MarkSharpEdgesForPlasticityGroupsOperator(bpy.types.Operator):
    bl_idname = "mesh.mark_sharp_edges_for_plasticity"
    bl_label = "Mark Sharp Edges for Plasticity Groups"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == 'MESH' and "plasticity_id" in obj.keys()

    def execute(self, context):
        obj = context.object
        mesh = obj.data

        prev_obj_mode = bpy.context.object.mode
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=1e-06)
        bpy.ops.object.mode_set(mode='OBJECT')

        if "plasticity_id" not in obj.keys():
            self.report(
                {'ERROR'}, "Object doesn't have a plasticity_id attribute.")
            return {'CANCELLED'}

        groups = mesh["groups"]

        self.mark_sharp_edges(obj, groups)

        bpy.ops.object.mode_set(mode=prev_obj_mode)

        return {'FINISHED'}

    def mark_sharp_edges(self, obj, groups):
        mesh = obj.data
        bm = bmesh.new()
        mesh.calc_normals_split()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        loops = mesh.loops

        edge_lookup = {
            (e.verts[0].index, e.verts[1].index): e for e in bm.edges}

        all_face_boundary_edges = set()
        for idx in range(0, len(groups), 2):
            start_idx = groups[idx] // 3
            count = groups[idx + 1] // 3
            end_idx = start_idx + count

            face_boundary_edges = set()
            for face_idx in range(start_idx, end_idx):
                face = bm.faces[face_idx]
                for edge in face.edges:
                    verts = (edge.verts[0].index, edge.verts[1].index)
                    if verts in edge_lookup:
                        if edge in face_boundary_edges:
                            face_boundary_edges.remove(edge)
                        else:
                            face_boundary_edges.add(edge)
            all_face_boundary_edges.update(face_boundary_edges)

        for edge in all_face_boundary_edges:
            edge.smooth = False

        bm.to_mesh(obj.data)
        bm.free()


class PaintPlasticityFacesOperator(bpy.types.Operator):
    bl_idname = "mesh.paint_plasticity_faces"
    bl_label = "Paint Plasticity Faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() for obj in context.selected_objects)

    def execute(self, context):
        prev_obj_mode = bpy.context.object.mode
        if prev_obj_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        obj = context.object
        mesh = obj.data

        if "plasticity_id" not in obj.keys():
            self.report(
                {'ERROR'}, "Object doesn't have a plasticity_id attribute.")
            return {'CANCELLED'}

        self.colorize_mesh(obj, mesh)

        bpy.ops.object.mode_set(mode=prev_obj_mode)

        return {'FINISHED'}

    def colorize_mesh(self, obj, mesh):
        groups = mesh["groups"]
        face_ids = mesh["face_ids"]

        if len(groups) == 0:
            return
        if len(face_ids) * 2 != len(groups):
            return

        if not mesh.vertex_colors:
            mesh.vertex_colors.new()
        color_layer = mesh.vertex_colors.active

        for i in range(0, len(groups), 2):
            start_offset = groups[i + 0]
            count = groups[i + 1]
            face_id = face_ids[i // 2]

            color = generate_random_color(face_id)

            for j in range(start_offset // 3, (start_offset + count) // 3):
                face = mesh.polygons[j]
                for loop_index in face.loop_indices:
                    color_layer.data[loop_index].color = color


def are_normals_different(normal_a, normal_b, threshold_angle_degrees=5.0):
    threshold_cosine = math.cos(math.radians(threshold_angle_degrees))
    dot_product = normal_a.dot(normal_b)
    return dot_product < threshold_cosine


def generate_random_color(face_id):
    return (random.random(), random.random(), random.random(), 1.0)  # RGBA
