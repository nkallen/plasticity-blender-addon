import bpy

from .__init__ import plasticity_client


class ConnectButton(bpy.types.Operator):
    bl_idname = "wm.connect_button"
    bl_label = "Connect"
    bl_description = "Connect to the Plasticity server and load available meshes"

    def execute(self, context):
        plasticity_client.connect()
        return {'FINISHED'}


class DisconnectButton(bpy.types.Operator):
    bl_idname = "wm.disconnect_button"
    bl_label = "Disconnect"
    bl_description = "Disconnect from the Plasticity server"

    def execute(self, context):
        plasticity_client.disconnect()
        return {'FINISHED'}


class RefreshButton(bpy.types.Operator):
    bl_idname = "wm.refresh"
    bl_label = "Refresh"
    bl_description = "Refresh the list of available meshes"

    def execute(self, context):
        plasticity_client.refresh()
        return {'FINISHED'}


class RefacetButton(bpy.types.Operator):
    bl_idname = "wm.refacet"
    bl_label = "Refacet"
    bl_description = "Refacet the mesh"

    @classmethod
    def poll(cls, context):
        return any("plasticity_id" in obj.keys() for obj in context.selected_objects)

    def execute(self, context):
        prop_tolerance = context.scene.prop_plasticity_facet_tolerance
        prop_angle = context.scene.prop_plasticity_facet_angle
        plasticity_ids = [obj["plasticity_id"]
                          for obj in context.selected_objects if "plasticity_id" in obj.keys()]

        plasticity_client.refacet(plasticity_ids, curve_chord_tolerance=prop_tolerance,
                                  surface_plane_tolerance=prop_tolerance, curve_chord_angle=prop_angle, surface_plane_angle=prop_angle)

        return {'FINISHED'}


class PlasticityPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_plasticity_panel"
    bl_label = "Plasticity"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Plasticity'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        if plasticity_client.connected:
            disconnect_button = layout.operator(
                "wm.disconnect_button", text="Disconnect")
        else:
            connect_button = layout.operator(
                "wm.connect_button", text="Connect")

        layout.operator("wm.refresh", text="Refresh")

        if plasticity_client.connected:
            box = layout.box()
            box.label(text="Refacet config:")

            box.prop(scene, "prop_plasticity_facet_tolerance", text="Tolerance")
            box.prop(scene, "prop_plasticity_facet_angle", text="Angle")
            refacet_op = box.operator("wm.refacet", text="Refacet")

            box = layout.box()
            box.label(text="Utilities:")
            box.operator("mesh.mark_sharp_edges_for_plasticity",
                         text="Mark Sharp Edges")
            box.operator("mesh.paint_plasticity_faces",
                         text="Paint Plasticity Faces")
