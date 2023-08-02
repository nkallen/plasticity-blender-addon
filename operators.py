import math
import random

import bmesh
import bpy
import mathutils


class SelectByFaceIDOperator(bpy.types.Operator):
    bl_idname = "mesh.select_by_plasticity_face_id"
    bl_label = "Select by Plasticity Face ID"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() and obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        obj = context.object
        bpy.ops.object.mode_set(mode='EDIT')

        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)

        groups = mesh["groups"]
        if not groups:
            self.report({'ERROR'}, "No groups found")
            return {'CANCELLED'}

        face_ids = mesh["face_ids"]
        if not face_ids:
            self.report({'ERROR'}, "No face_ids found")
            return {'CANCELLED'}

        active_face = bm.faces.active
        if not active_face:
            self.report({'ERROR'}, "No active face selected")
            return {'CANCELLED'}

        loop_idx = active_face.loops[0].index

        group_id = -1
        for i in range(0, len(groups), 2):
            group_start = groups[i + 0]
            group_count = groups[i + 1]
            if loop_idx >= group_start and loop_idx < group_start + group_count:
                group_id = i
                break

        if group_id == -1:
            self.report({'ERROR'}, "No group found for face")
            return {'CANCELLED'}

        group_start = groups[group_id + 0]
        group_count = groups[group_id + 1]

        for face in bm.faces:
            loop_start = face.loops[0].index
            if loop_start >= group_start and loop_start < group_start + group_count:
                face.select = True

        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}


class MarkSharpEdgesForPlasticityGroupsWithSplitNormalsOperator(bpy.types.Operator):
    bl_idname = "mesh.mark_sharp_edges_for_plasticity_with_split_normals"
    bl_label = "Mark Sharp Edges for Plasticity Groups With Split Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() and obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        prev_obj_mode = bpy.context.mode

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            if not "plasticity_id" in obj.keys():
                continue
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

        bpy.ops.object.mode_set(mode=map_mode(prev_obj_mode))

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

        all_face_boundary_edges = face_boundary_edges(groups, mesh, bm)

        split_edges = set()
        for vert in bm.verts:
            for edge in vert.link_edges:
                loops_for_vert_and_edge = []
                for face in edge.link_faces:
                    for loop in face.loops:
                        if loop.vert == vert:
                            loops_for_vert_and_edge.append(loop)
                if len(loops_for_vert_and_edge) != 2:
                    continue
                loop1, loop2 = loops_for_vert_and_edge
                normal1 = loops[loop1.index].normal
                normal2 = loops[loop2.index].normal
                if are_normals_different(normal1, normal2):
                    split_edges.add(edge)
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
        return any("plasticity_id" in obj.keys() and obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        prev_obj_mode = bpy.context.object.mode

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            if not "plasticity_id" in obj.keys():
                continue
            mesh = obj.data

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

        bpy.ops.object.mode_set(mode=map_mode(prev_obj_mode))

        return {'FINISHED'}

    def mark_sharp_edges(self, obj, groups):
        mesh = obj.data
        bm = bmesh.new()
        mesh.calc_normals_split()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        for edge in face_boundary_edges(groups, mesh, bm):
            edge.smooth = False

        bm.to_mesh(obj.data)
        bm.free()


def face_boundary_edges(groups, mesh, bm):
    all_face_boundary_edges = set()
    face_boundary_edges = set()

    group_idx = 0
    group_start = groups[group_idx * 2 + 0]
    group_count = groups[group_idx * 2 + 1]
    face_boundary_edges = set()

    for poly in mesh.polygons:
        loop_start = poly.loop_start
        if loop_start >= group_start + group_count:
            all_face_boundary_edges.update(face_boundary_edges)
            group_idx += 1
            group_start = groups[group_idx * 2 + 0]
            group_count = groups[group_idx * 2 + 1]
            face_boundary_edges = set()

        face = bm.faces[poly.index]
        for edge in face.edges:
            if edge in face_boundary_edges:
                face_boundary_edges.remove(edge)
            else:
                face_boundary_edges.add(edge)
    all_face_boundary_edges.update(face_boundary_edges)

    return all_face_boundary_edges


class SetPlasticityOriginToOriginOperator(bpy.types.Operator):
    bl_idname = "mesh.set_plasticity_origin_to_origin"
    bl_label = "Set Plasticity Origin to Origin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() and obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        prev_obj_mode = bpy.context.mode

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            if not "plasticity_id" in obj.keys():
                continue
            mesh = obj.data

            self.set_plasticity_origin_to_origin(obj)

        bpy.ops.object.mode_set(mode=map_mode(prev_obj_mode))

        return {'FINISHED'}

    def set_plasticity_origin_to_origin(self, obj):
        location = obj.location
        transform = mathutils.Matrix.Identity(4)
        transform.translation = location
        transform_list = [item for sublist in transform for item in sublist]
        obj["plasticity_transform"] = transform_list


class PaintPlasticityFacesOperator(bpy.types.Operator):
    bl_idname = "mesh.paint_plasticity_faces"
    bl_label = "Paint Plasticity Faces"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() and obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        prev_obj_mode = bpy.context.mode

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            if not "plasticity_id" in obj.keys():
                continue
            mesh = obj.data

            if "plasticity_id" not in obj.keys():
                self.report(
                    {'ERROR'}, "Object doesn't have a plasticity_id attribute.")
                return {'CANCELLED'}

            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')

            self.colorize_mesh(obj, mesh)

            mat = bpy.data.materials.new(name="VertexColorMat")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes

            for node in nodes:
                nodes.remove(node)

            vertex_color_node = nodes.new(type='ShaderNodeVertexColor')
            shader_node = nodes.new(type='ShaderNodeBsdfPrincipled')
            shader_node.location = (400, 0)
            mat.node_tree.links.new(
                shader_node.inputs['Base Color'], vertex_color_node.outputs['Color'])

            material_output = nodes.new(type='ShaderNodeOutputMaterial')
            material_output.location = (800, 0)
            mat.node_tree.links.new(
                material_output.inputs['Surface'], shader_node.outputs['BSDF'])

            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        bpy.ops.object.mode_set(mode=map_mode(prev_obj_mode))

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

        group_idx = 0
        group_start = groups[group_idx * 2 + 0]
        group_count = groups[group_idx * 2 + 1]
        face_id = face_ids[group_idx]
        color = generate_random_color(face_id)

        for poly in mesh.polygons:
            loop_start = poly.loop_start
            if loop_start >= group_start + group_count:
                group_idx += 1
                group_start = groups[group_idx * 2 + 0]
                group_count = groups[group_idx * 2 + 1]
                face_id = face_ids[group_idx]
                color = generate_random_color(face_id)
            for loop_index in range(loop_start, loop_start + poly.loop_total):
                color_layer.data[loop_index].color = color


def are_normals_different(normal_a, normal_b, threshold_angle_degrees=5.0):
    threshold_cosine = math.cos(math.radians(threshold_angle_degrees))
    dot_product = normal_a.dot(normal_b)
    return dot_product < threshold_cosine


def generate_random_color(face_id):
    return (random.random(), random.random(), random.random(), 1.0)  # RGBA


mode_map = {
    'EDIT_MESH': 'EDIT',
    'EDIT_CURVE': 'EDIT',
    'EDIT_SURFACE': 'EDIT',
    'EDIT_TEXT': 'EDIT',
    'EDIT_ARMATURE': 'EDIT',
    'EDIT_METABALL': 'EDIT',
    'EDIT_LATTICE': 'EDIT',
    'POSE': 'EDIT',
}


def map_mode(context_mode):
    return mode_map.get(context_mode, context_mode)
