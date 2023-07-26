import bpy

from .__init__ import plasticity_client


class ConnectButton(bpy.types.Operator):
    bl_idname = "wm.connect_button"
    bl_label = "Connect"
    bl_description = "Connect to the Plasticity server"

    @classmethod
    def poll(cls, context):
        return not plasticity_client.connected

    def execute(self, context):
        plasticity_client.connect()
        return {'FINISHED'}


class DisconnectButton(bpy.types.Operator):
    bl_idname = "wm.disconnect_button"
    bl_label = "Disconnect"
    bl_description = "Disconnect from the Plasticity server"

    @classmethod
    def poll(cls, context):
        return plasticity_client.connected

    def execute(self, context):
        plasticity_client.disconnect()
        return {'FINISHED'}


class ListButton(bpy.types.Operator):
    bl_idname = "wm.list"
    bl_label = "Refresh"
    bl_description = "Refresh the list of available items"

    @classmethod
    def poll(cls, context):
        return plasticity_client.connected

    def execute(self, context):
        only_visible = context.scene.prop_plasticity_list_only_visible
        if only_visible:
            plasticity_client.list_visible()
        else:
            plasticity_client.list_all()
        return {'FINISHED'}


class SubscribeAllButton(bpy.types.Operator):
    bl_idname = "wm.subscribe_all"
    bl_label = "Subscribe All"
    bl_description = "Subscribe to all available meshes"

    @classmethod
    def poll(cls, context):
        return plasticity_client.connected and not plasticity_client.subscribed

    def execute(self, context):
        plasticity_client.subscribe_all()
        return {'FINISHED'}


class UnsubscribeAllButton(bpy.types.Operator):
    bl_idname = "wm.unsubscribe_all"
    bl_label = "Unsubscribe All"
    bl_description = "Unsubscribe to all available meshes"

    @classmethod
    def poll(cls, context):
        return plasticity_client.connected and plasticity_client.subscribed

    def execute(self, context):
        plasticity_client.unsubscribe_all()
        return {'FINISHED'}


class RefacetButton(bpy.types.Operator):
    bl_idname = "wm.refacet"
    bl_label = "Refacet"
    bl_description = "Refacet the mesh"

    @classmethod
    def poll(cls, context):
        if not plasticity_client.connected:
            return False
        return any("plasticity_id" in obj.keys() for obj in context.selected_objects)

    def execute(self, context):
        prop_tolerance = context.scene.prop_plasticity_facet_tolerance
        prop_angle = context.scene.prop_plasticity_facet_angle
        plasticity_ids = [obj["plasticity_id"]
                          for obj in context.selected_objects if "plasticity_id" in obj.keys()]

        plasticity_client.refacet_some(plasticity_ids, curve_chord_tolerance=prop_tolerance,
                                       surface_plane_tolerance=prop_tolerance, curve_chord_angle=prop_angle, surface_plane_angle=prop_angle)

        return {'FINISHED'}


class PlasticityPanel(bpy.types.Panel):
    bl_idname = "plasticity_panel"
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

        if plasticity_client.connected:
            layout.separator()

            box = layout.box()
            box.prop(scene, "prop_plasticity_list_only_visible",
                     text="Only visible")
            box.operator("wm.list", text="Refresh")

            layout.separator()
            if not plasticity_client.subscribed:
                layout.operator("wm.subscribe_all", text="Live link")
            else:
                layout.operator("wm.unsubscribe_all", text="Disable live link")
            layout.separator()

            box = layout.box()
            box.label(text="Refacet config:")

            box.prop(scene, "prop_plasticity_facet_tolerance", text="Tolerance")
            box.prop(scene, "prop_plasticity_facet_angle", text="Angle")
            refacet_op = box.operator("wm.refacet", text="Refacet")

            layout.separator()

            box = layout.box()
            box.label(text="Utilities:")
            box.operator("mesh.mark_sharp_edges_for_plasticity_with_split_normals",
                         text="Mark sharp (EXPERIMENTAL)")
            box.operator("mesh.mark_sharp_edges_for_plasticity",
                         text="Mark sharp at boundaries")
            box.operator("mesh.paint_plasticity_faces",
                         text="Paint Plasticity Faces")
