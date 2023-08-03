import bpy

from . import operators, ui
from .client import PlasticityClient
from .handler import SceneHandler

bl_info = {
    "name": "Plasticity",
    "description": "A bridge to Plasticity",
    "author": "Nick Kallen",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Plasticity",
    "category": "Object",
}

handler = SceneHandler()
plasticity_client = PlasticityClient(handler)


def select_similar(self, context):
    self.layout.operator(operators.SelectByFaceIDOperator.bl_idname)


# def right_click_menu(self, context):
#     self.layout.separator()
#     self.layout.operator(
#         operators.SetPlasticityOriginToOriginOperator.bl_idname)


def register():
    print("Registering Plasticity client")

    bpy.utils.register_class(ui.ConnectButton)
    bpy.utils.register_class(ui.DisconnectButton)
    bpy.utils.register_class(ui.ListButton)
    bpy.utils.register_class(ui.SubscribeAllButton)
    bpy.utils.register_class(ui.UnsubscribeAllButton)
    bpy.utils.register_class(ui.RefacetButton)
    bpy.utils.register_class(ui.PlasticityPanel)
    bpy.utils.register_class(operators.SelectByFaceIDOperator)
    bpy.utils.register_class(
        operators.MarkSharpEdgesForPlasticityGroupsWithSplitNormalsOperator)
    bpy.utils.register_class(
        operators.MarkSharpEdgesForPlasticityGroupsOperator)
    bpy.utils.register_class(operators.PaintPlasticityFacesOperator)
    # bpy.utils.register_class(operators.SetPlasticityOriginToOriginOperator)
    # bpy.utils.register_class(operators.ClearPlasticityOriginOperator)

    # bpy.types.VIEW3D_MT_object_context_menu.append(right_click_menu)
    bpy.types.VIEW3D_MT_edit_mesh_select_similar.append(select_similar)

    bpy.types.Scene.prop_plasticity_server = bpy.props.StringProperty(
        name="Server", default="localhost:8080")
    bpy.types.Scene.prop_plasticity_facet_tolerance = bpy.props.FloatProperty(
        name="Tolerance", default=0.01, min=0.0001, max=1.0)
    bpy.types.Scene.prop_plasticity_facet_angle = bpy.props.FloatProperty(
        name="Angle", default=0.45, min=0.1, max=1.0)
    bpy.types.Scene.prop_plasticity_list_only_visible = bpy.props.BoolProperty(
        name="List only visible", default=False)
    bpy.types.Scene.prop_plasticity_facet_tri_or_ngon = bpy.props.EnumProperty(
        items=[
            ("TRI", "Tri", "Tri"),
            ("NGON", "Ngon", "Ngon"),
        ],
        name="Facet Type",
        default="TRI",
    )
    bpy.types.Scene.prop_plasticity_ui_show_advanced_facet = bpy.props.BoolProperty(
        name="Advanced", default=False)
    bpy.types.Scene.prop_plasticity_facet_min_width = bpy.props.FloatProperty(
        name="Min Width", default=0.0, min=0, unit="LENGTH")
    bpy.types.Scene.prop_plasticity_facet_max_width = bpy.props.FloatProperty(
        name="Max Width", default=0.0, min=0, unit="LENGTH")
    bpy.types.Scene.prop_plasticity_unit_scale = bpy.props.FloatProperty(
        name="Unit Scale", default=1.0, min=0.0001, max=1000.0)

    print("Plasticity client registered")


def unregister():
    print("Unregistering Plasticity client")

    bpy.utils.unregister_class(ui.PlasticityPanel)
    bpy.utils.unregister_class(ui.DisconnectButton)
    bpy.utils.unregister_class(ui.ConnectButton)
    bpy.utils.unregister_class(ui.ListButton)
    bpy.utils.unregister_class(ui.SubscribeAllButton)
    bpy.utils.unregister_class(ui.UnsubscribeAllButton)
    bpy.utils.unregister_class(ui.RefacetButton)
    bpy.utils.unregister_class(operators.SelectByFaceIDOperator)
    bpy.utils.unregister_class(
        operators.MarkSharpEdgesForPlasticityGroupsWithSplitNormalsOperator)
    bpy.utils.unregister_class(
        operators.MarkSharpEdgesForPlasticityGroupsOperator)
    bpy.utils.unregister_class(operators.PaintPlasticityFacesOperator)
    # bpy.utils.unregister_class(operators.SetPlasticityOriginToOriginOperator)
    # bpy.utils.unregister_class(operators.ClearPlasticityOriginOperator)

    # bpy.types.VIEW3D_MT_object_context_menu.remove(right_click_menu)
    bpy.types.VIEW3D_MT_edit_mesh_select_similar.remove(select_similar)

    del bpy.types.Scene.prop_plasticity_server
    del bpy.types.Scene.prop_plasticity_facet_tolerance
    del bpy.types.Scene.prop_plasticity_facet_angle
    del bpy.types.Scene.prop_plasticity_facet_tri_or_ngon
    del bpy.types.Scene.prop_plasticity_list_only_visible
    del bpy.types.Scene.prop_plasticity_ui_show_advanced_facet
    del bpy.types.Scene.prop_plasticity_facet_min_width
    del bpy.types.Scene.prop_plasticity_facet_max_width
    del bpy.types.Scene.prop_plasticity_unit_scale


if __name__ == "__main__":
    register()
