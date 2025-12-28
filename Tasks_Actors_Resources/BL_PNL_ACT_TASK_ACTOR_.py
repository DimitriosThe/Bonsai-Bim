bl_info = {
    "name": "BIM Task Actor Assignment",
    "author": "Dimitrios Theodorou",
    "version": (0, 0, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > BIM_test",
    "description": "Shows highlighted (selected) task info, task Classificaton, \n assigned actor, actors list, and lets you assign/unassign actors to the task.",
    "category": "3D View",
}

import bpy
import ifcopenshell
import ifcopenshell.guid
import bonsai.bim.ifc
from bonsai.tool.sequence import Sequence


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def wrap_text(text, width=80):
    """Split text into fixed-width chunks for display in Blender labels."""
    if not text:
        return []
    return [text[i:i+width] for i in range(0, len(text), width)]


def get_ifc_file():
    store = bonsai.bim.ifc.IfcStore()
    try:
        return store.get_file()
    except Exception:
        return None


def ensure_actors_loaded(context):
    """Load IFC actors into scene collection if empty or refresh requested."""
    scene = context.scene
    if not hasattr(scene, "bim_actors"):
        return
    model = get_ifc_file()
    if not model:
        return
    # Always refresh to keep in sync (fast enough for typical counts)
    scene.bim_actors.clear()
    for actor in model.by_type("IfcActor"):
        item = scene.bim_actors.add()
        item.name = getattr(actor, "Name", "") or "(no name)"
        item.description = getattr(actor, "Description", "") or ""
        # Store stable references to the IFC entity
        item.entity_id = actor.id()
        item.global_id = getattr(actor, "GlobalId", "") or ""
        # First classification if present
        cls_text = ""
        assocs = getattr(actor, "HasAssociations", None)
        if assocs:
            for assoc in assocs:
                if assoc.is_a("IfcRelAssociatesClassification"):
                    cls = assoc.RelatingClassification
                    if cls:
                        cls_text = f"{getattr(cls, 'Name', '')} ({getattr(cls, 'Identification', '')})"
                        break
        item.classification = cls_text


def get_selected_actor_entity(context):
    """Return the IfcActor entity corresponding to the UI list selection."""
    model = get_ifc_file()
    if not model:
        return None
    idx = context.scene.bim_actors_index
    if idx < 0 or idx >= len(context.scene.bim_actors):
        return None
    item = context.scene.bim_actors[idx]
    # Retrieve by internal id for reliability
    try:
        return model[item.entity_id]
    except Exception:
        # Fallback by GlobalId if available
        if item.global_id:
            try:
                return next(e for e in model.by_type("IfcActor") if getattr(e, "GlobalId", "") == item.global_id)
            except StopIteration:
                return None
        return None


def iter_task_actor_assignments(task):
    """Yield IfcRelAssignsToActor relationships for a task."""
    assignments = getattr(task, "HasAssignments", None)
    if not assignments:
        return
    for assignment in assignments:
        if assignment.is_a("IfcRelAssignsToActor"):
            yield assignment


# ---------------------------------------------------------------------------
# Data model for UIList
# ---------------------------------------------------------------------------

class BIM_ActorItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    description: bpy.props.StringProperty(name="Description")
    classification: bpy.props.StringProperty(name="Classification")
    entity_id: bpy.props.IntProperty(name="IFC Entity ID")
    global_id: bpy.props.StringProperty(name="GlobalId")


class BIM_UL_actors(bpy.types.UIList):
    """UIList to display actors within the IFC model."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if item:
            row = layout.row(align=True)
            row.label(text=item.name or "(no name)", icon='USER')
            if item.classification:
                row.label(text=item.classification, icon='SEQ_SEQUENCER') #SEQ_STRIP_DUPLICATE BOOKMARKS SEQ_SEQUENCER
            else:
                row.label(text="No classification associated", icon='ERROR') #SEQ_STRIP_DUPLICATE
            # Tooltip-like description snippet
            if item.description:
                sub = layout.row()
                sub.enabled = False
                sub.label(text=item.description[:40])


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class BIM_OT_refresh_actors(bpy.types.Operator):
    bl_idname = "bim.refresh_actors"
    bl_label = "Refresh Actors"
    bl_description = "Reload actors from the IFC model"

    def execute(self, context):
        ensure_actors_loaded(context)
        self.report({'INFO'}, "Actors refreshed")
        return {'FINISHED'}


class BIM_OT_assign_actor(bpy.types.Operator):
    bl_idname = "bim.assign_actor"
    bl_label = "Assign Selected Actor"
    bl_description = "Assign the selected actor in the list to the highlighted task"

    def execute(self, context):
        model = get_ifc_file()
        if not model:
            self.report({'WARNING'}, "No IFC model loaded")
            return {'CANCELLED'}

        task = Sequence.get_highlighted_task()
        if not task:
            self.report({'WARNING'}, "No highlighted task")
            return {'CANCELLED'}

        actor = get_selected_actor_entity(context)
        if not actor:
            self.report({'WARNING'}, "No actor selected or actor not found")
            return {'CANCELLED'}

        # Avoid duplicate assignment to the same actor
        for rel in iter_task_actor_assignments(task):
            if rel.RelatingActor == actor:
                self.report({'INFO'}, "Actor already assigned to task")
                return {'FINISHED'}

        # Create new relationship
        rel = model.create_entity(
            "IfcRelAssignsToActor",
            GlobalId=ifcopenshell.guid.new(),
            RelatingActor=actor,
            RelatedObjects=[task],
            Name=f"Assign {getattr(actor, 'Name', '')} to {getattr(task, 'Name', '')}" or None,
            Description="Assigned via Blender panel"
        )

        # Ensure bidirectional links are maintained if needed (ifcopenshell usually handles this)
        self.report({'INFO'}, f"Assigned actor: {getattr(actor, 'Name', '(no name)')}")
        return {'FINISHED'}


class BIM_OT_unassign_actor(bpy.types.Operator):
    bl_idname = "bim.unassign_actor"
    bl_label = "Unassign Task Actor(s)"
    bl_description = "Unassign all IfcRelAssignsToActor relationships from the highlighted task"

    def execute(self, context):
        model = get_ifc_file()
        if not model:
            self.report({'WARNING'}, "No IFC model loaded")
            return {'CANCELLED'}

        task = Sequence.get_highlighted_task()
        if not task:
            self.report({'WARNING'}, "No highlighted task")
            return {'CANCELLED'}

        to_remove = list(iter_task_actor_assignments(task))
        if not to_remove:
            self.report({'INFO'}, "Task has no actor assignments")
            return {'FINISHED'}

        for rel in to_remove:
            model.remove(rel)

        self.report({'INFO'}, f"Removed {len(to_remove)} actor assignment(s)")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class BIM_PT_highlighted_task_info(bpy.types.Panel):
    """
    Show information for the currently highlighted task (via Sequence.get_highlighted_task).

    Displays:
    - Task name and description
    - Task classifications (Name + Identification)
    - Assigned actors: name, description, and organization/person
    - Actor list from the IFC file with selection + assign/unassign buttons
    """
    bl_idname = "BIM_PT_highlighted_task_info"
    bl_label = "Highlighted Task Information"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BIM_PM'

    def draw(self, context):
        layout = self.layout

        # Make sure actors are loaded each draw (keeps in sync)
        #ensure_actors_loaded(context)

        # Get the highlighted task directly from Bonsai Sequence
        task = Sequence.get_highlighted_task()
        if not task:
            layout.label(text="No highlighted task.", icon='INFO')
            # Still show actor list so user can select beforehand
            self.draw_actor_list(layout, context)
            return
            
        tab = 9*' '
        
        # Task header
        box = layout.box()
        box.label(text=f"Task: {getattr(task, 'Name', '(no name)')}", icon='SEQ_SEQUENCER')#SEQ_PREVIEW SEQ_SPLITVIEW SEQ_SEQUENCER

        # Task description (wrapped)
        if getattr(task, "Description", None):
            for line in wrap_text(task.Description, len(task.Description)):
                box.label(text=f"{tab}Task Description: {line}")

        # Task classifications (wrapped)
        associations = getattr(task, "HasAssociations", None)
        if associations:
            for assoc in associations:
                if assoc.is_a("IfcRelAssociatesClassification"):
                    cls = assoc.RelatingClassification
                    if cls:
                        text = f"{tab}Classification: {getattr(cls, 'Name', '')} ({getattr(cls, 'Identification', '')})"
                        for line in wrap_text(text, len(text)):
                            box.label(text=line)

        # Assigned actors
        assignments = list(iter_task_actor_assignments(task))
        if assignments:
            for assignment in assignments:
                actor = assignment.RelatingActor
                actor_box = layout.box()
                actor_box.label(text=f"Assigned Actor: {getattr(actor, 'Name', '(no name)')}", icon='USER')

                # Actor description (wrapped)
                if getattr(actor, "Description", None):
                    for line in wrap_text(actor.Description, len(actor.Description)):
                        actor_box.label(text=f"{tab}Description: {line}")

                # Organization or Person (wrapped)
                if getattr(actor, "TheActor", None):
                    assoc = actor.TheActor
                    if assoc.is_a("IfcOrganization"):
                        for line in wrap_text(getattr(assoc, "Name", "") or "", 50):
                            actor_box.label(text=f"{tab}Organization: {line}")
                    elif assoc.is_a("IfcPerson"):
                        person_name = " ".join(filter(None, [assoc.FamilyName, assoc.GivenName]))
                        for line in wrap_text(person_name, 50):
                            actor_box.label(text=f"{tab}Person: {line}")

                # Actor classifications
                if getattr(actor, "HasAssociations", None):
                    for actor_assoc in actor.HasAssociations:
                        if actor_assoc.is_a("IfcRelAssociatesClassification"):
                            actor_classif = actor_assoc.RelatingClassification
                            if actor_classif:
                                text = f"Actor Classification: {getattr(actor_classif, 'Name', '')} ({getattr(actor_classif, 'Identification', '')})"
                                for line in wrap_text(text, len(text)):
                                    actor_box.label(text=f"{tab}{line}")
        else:
            actor_box = layout.box()
            actor_box.label(text=f"No assigned Actor for the selected task: ", icon='USER')

        # Buttons for assignment management
        btn_row = box.row(align=True)
        btn_row.operator("bim.unassign_actor", text="Unassign Actor(s)", icon='EVENT_MINUS')
        btn_row.operator("bim.assign_actor", text="Assign Selected Actor", icon='EVENT_PLUS')

        # Actor list for selection
        self.draw_actor_list(layout, context)

    def draw_actor_list(self, layout, context):
        actors_box = layout.box()
        actors_box.label(text="Actors in file :", icon='USER')
        actors_box.template_list(
            "BIM_UL_actors", "",
            context.scene, "bim_actors",
            context.scene, "bim_actors_index",
            rows=6
        )
        tab = 9*' '
        row = actors_box.row(align=True)
        row.operator("bim.refresh_actors", text="Refresh", icon='FILE_REFRESH')
        # Show quick details of selected
        selected = None
        if 0 <= context.scene.bim_actors_index < len(context.scene.bim_actors):
            selected = context.scene.bim_actors[context.scene.bim_actors_index]
        if selected:
            info_box = actors_box.box()
            info_box.label(text=f"Selected Actor: {selected.name}", icon='INFO')
            if selected.description:
                for line in wrap_text(selected.description, len(selected.description)):
                    info_box.label(text=f"{tab}Description: {line}")
            else:
                info_box.label(text=f"{tab}Description: No description available")
            if selected.classification:
                info_box.label(text=f"{tab}Classification: {selected.classification}")
            else:
                info_box.label(text=f"{tab}Classification: No Classification assigned")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    BIM_ActorItem,
    BIM_UL_actors,
    BIM_OT_refresh_actors,
    BIM_OT_assign_actor,
    BIM_OT_unassign_actor,
    BIM_PT_highlighted_task_info,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bim_actors = bpy.props.CollectionProperty(type=BIM_ActorItem)
    bpy.types.Scene.bim_actors_index = bpy.props.IntProperty(default=-1)


def unregister():
    del bpy.types.Scene.bim_actors_index
    del bpy.types.Scene.bim_actors
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
