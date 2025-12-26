bl_info = {
    "name": "BIM Task Actor Assignment",
    "author": "Dimitrios Theodorou",
    "version": (0, 0, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > BIM_PrjMngmnt_Actors",
    "description": "Shows highlighted (selected) Actor info, Actor Classificatons, \n assigned Tasks, actors list, unassigned taks,and lets you assign/unassign actors to the task \n and resource as well.",
    "category": "3D View",
}
import os
import re
import bpy
import csv
import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.api.owner
import ifcopenshell.api.resource
import ifcopenshell.api.classification
import ifcopenshell.util.sequence 
import bonsai.bim.ifc
from bonsai.tool.sequence import Sequence
from bonsai.bim.module.sequence.data import SequenceData

from bonsai.tool.ifc import Ifc as ifc
from bonsai.tool.resource import Resource as resource_tool
from bonsai.bim.module.resource.data import ResourceData
from typing import Any, Optional, Union, Literal, get_args, NamedTuple, cast
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

"""
20251204 - Add Resource Box based on selected task and assignment of actors to 
            resource build-up by generating an Actor specific resource build-up 
            based on the existing assigned for the task, thus having the option 
            to tweak the productivity rates for that Actor specific build up, affecting only that specific task and not the whole.
            
20251209 - Able to assign Actor to selected resource

"""

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
        item.classifications.clear()
        assocs = getattr(actor, "HasAssociations", None)
        if assocs:
            for assoc in assocs:
                if assoc.is_a("IfcRelAssociatesClassification"):
                    cls = assoc.RelatingClassification
                    if cls:
                        sub = item.classifications.add()
                        cls_text = f"{getattr(cls, 'Name', '')} ({getattr(cls, 'Identification', '')})"
                        sub.text = cls_text
                        #break
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


def import_actor_data(context, filepath, update_setting):
        
    model = get_ifc_file()
    actors = model.by_type("IfcActor")
    actors_id = []
    
    for actor in actors:
        actors_id.extend([{"org_id":actor.TheActor.Identification, "actor_guid":actor.GlobalId}])
    print(actors_id)
    
    actors_ids = {org["org_id"] for org in actors_id}
    
    print(f'\n\nactors_ids = \n{actors_ids}')

    with open(filepath, newline='', encoding='utf-8') as csvfile:
        
        filename = os.path.split(filepath)
        print(f"Importing actor data from {filename}")
        reader = csv.DictReader(csvfile)
        
        fields = reader.fieldnames
        print(fields)
        
        for row in reader:
            print(f'in row {row}')
            
            if "GUID" in fields:
                if row["GUID"]!= None and row["GUID"] in  organizations_id:
                    print(f'The organization {row["Identification"]} allready exists')
                    if update_setting == True:
                        print(f'The data will be updated on the existing Actor')
                        model.by_guid(row["GUID"])
                        
                        
                continue
            elif not "GUID" in fields:
                print(f'No GUID column')
                # Check for existing based on identification
                print(f'row["Identification"] = {row["Identification"]}')
                
                # If the Actor Identification exist already 
                if row["Identification"] in actors_ids:
                    print(f'The organization {row["Identification"]} allready exists')
                    
                    # And Update is checked
                    if update_setting == True:
                        print(f'The data will be updated on the existing Actor and organization')
                        actor = None
                        for value in actors_id:
                            if value["org_id"] != row["Identification"]:
                                continue
                            actor = model.by_id(value["actor_guid"])
                            print(actor)
                            break
                        if actor:
                            # Edit Organization Name to update it
                            if row["Name"] != actor.TheActor.Name:
                                print(f'Updating Organization Name for {actor.TheActor.Name} with {row["Name"]}')
                                ifcopenshell.api.owner.edit_organisation(
                                    model,
                                    actor.TheActor,
                                    {"Name":row["Name"]}
                                )
                                
                            if row["Description"] != actor.Description:
                                print(f'Updating Actor Description {actor.Description} with {row["Description"]}')
                                ifcopenshell.api.owner.edit_actor(
                                    model,
                                    actor,
                                    {"Description":row["Description"]}
                                )
                            

                            ### TODO GET ATTR check for Role entity
                            role = getattr(actor.TheActor, "Roles")#,None)
                            
                            print(f"role = {role[0].Role}")
                            
                            if row["Roles[0].Role"]!= "" and role and not actor.TheActor.Roles[0].UserDefinedRole:
                                if row["Roles[0].Role"] != actor.TheActor.Roles[0].Role:
                                    
                                    print(f'Updating Organization Role for {role[0].Role} with {row["Roles[0].Role"]}')
                                    
                                    ifcopenshell.api.owner.edit_role(
                                        model,
                                        actor.TheActor.Roles[0],
                                        {"Role":row["Roles[0].Role"]}
                                    )
                                    
                            elif row["Roles[0].Role"]!= "" and role and actor.TheActor.Roles[0].UserDefinedRole:
                                print(f'Updating Organization Role for {actor.TheActor.Roles[0].UserDefinedRole} with {row["Roles[0].Role"]}')
                                ifcopenshell.api.owner.edit_role(
                                        model,
                                        actor.TheActor.Roles[0],
                                        {"Role":row["Roles[0].Role"],
                                            "UserDefinedRole":""}
                                    )
                                    
                                    
                            # User Defined Role
                            """
                            ARCHITECT	
                            BUILDINGOPERATOR	
                            BUILDINGOWNER	
                            CIVILENGINEER	
                            CLIENT	
                            COMMISSIONINGENGINEER	
                            CONSTRUCTIONMANAGER	
                            CONSULTANT	
                            CONTRACTOR	
                            COSTENGINEER	
                            ELECTRICALENGINEER	
                            ENGINEER	
                            FACILITIESMANAGER	
                            FIELDCONSTRUCTIONMANAGER	
                            MANUFACTURER	
                            MECHANICALENGINEER	
                            OWNER	
                            PROJECTMANAGER	
                            RESELLER	
                            STRUCTURALENGINEER	
                            SUBCONTRACTOR	
                            SUPPLIER	
                            USERDEFINED	
                            """
                            
                            # If the importing list has a User Defined Role and the matchin actor doesn't 
                            if row["Roles[0].UserDefinedRole"] and role and not actor.TheActor.Roles[0].UserDefinedRole:
                                print(f'---Updating Organization Role for {actor.TheActor.Roles[0].UserDefinedRole} with {row["Roles[0].UserDefinedRole"]}')
                                
                                ifcopenshell.api.owner.edit_role(
                                    model,
                                    actor.TheActor.Roles[0],
                                    {"Role" : "USERDEFINED",
                                      "UserDefinedRole" : row["Roles[0].UserDefinedRole"]}
                                )
                                
                                
                            #   If The importing list has a User Defined Role and the matching Actor also (UPDATE)
                            if row["Roles[0].UserDefinedRole"]!=() and role and actor.TheActor.Roles[0].UserDefinedRole:
                                print(f'Updating Organization Role for {actor.TheActor.Roles[0].UserDefinedRole or None} with {row["Roles[0].UserDefinedRole"]}')
                                ifcopenshell.api.owner.edit_role(
                                    model,
                                    actor.TheActor.Roles[0],
                                    {"UserDefinedRole" : row["Roles[0].UserDefinedRole"]}
                                )
                            
                            
                            
                            # Org Role Description
                            if role and row["Roles[0].Description"] != actor.TheActor.Roles[0].Description:
                                print(f'Updating Organization Role Description for {actor.TheActor.Roles[0].Description} with {row["Roles[0].Description"]}')
                                ifcopenshell.api.owner.edit_role(
                                    model,
                                    actor.TheActor.Roles[0],
                                    {"Description":row["Roles[0].Description"]}
                                )

                            # Org Address purpose
                            address = getattr(actor.TheActor, "Addresses")#, None)
                            print(f"address ={address}")
                            if address:
                                
                                if row["Addresses[0].Purpose"] != actor.TheActor.Addresses[0].Purpose:
                                    print(f'Updating Organization Adress Purpose for {actor.TheActor.Addresses[0].Purpose or None} with {row["Addresses[0].Purpose"]}')
                                    
                                    ifcopenshell.api.owner.edit_address(
                                        model,
                                        actor.TheActor.Addresses[0],
                                        {"Purpose" : row["Addresses[0].Purpose"]}
                                    )
                                    
                            elif not address:
                                
                                ifcopenshell.api.owner.add_address(
                                model,
                                assigned_object = actor.TheActor,
                                ifc_class="IfcTelecomAddress"
                                )
                                
                                ifcopenshell.api.owner.edit_address(
                                model,
                                actor.TheActor.Addresses[0],
                                {"Purpose" : row["Addresses[0].Purpose"]}
                                )
                                
                            
                            # Org Address Description
                            if address:
                                if row["Addresses[0].Description"] != actor.TheActor.Addresses[0].Description:
                                    print(f'Updating Organization Adress Description for {actor.TheActor.Addresses[0].Description or None} with {row["Addresses[0].Description"]}')
                                    ifcopenshell.api.owner.edit_address(
                                        model,
                                        actor.TheActor.Addresses[0],
                                        {"Description" : row["Addresses[0].Description"]}
                                    )
                            
                            elif not address:
                                ifcopenshell.api.owner.add_address(
                                model,
                                assigned_object = actor.TheActor,
                                ifc_class="IfcTelecomAddress"
                                )
                                
                                ifcopenshell.api.owner.edit_address(
                                model,
                                actor.TheActor.Addresses[0],
                                {"Description" : row["Addresses[0].Description"]}
                                )
                            
                            
                            # Org Address Telephone Numbers[0]
                            if address:
                                if row["Addresses[0].TelephoneNumbers[0]"] != actor.TheActor.Addresses[0].TelephoneNumbers[0]:
                                    print(f'Updating Organization TelephoneNumbers for {actor.TheActor.Addresses[0].TelephoneNumbers[0] or None} with {row["Addresses[0].TelephoneNumbers[0]"]}')
                                    ifcopenshell.api.owner.edit_address(
                                        model,
                                        actor.TheActor.Addresses[0],
                                        {"TelephoneNumbers[0]" : [row["Addresses[0].TelephoneNumbers[0]"]]}
                                    )
                            
                            elif not address:
                                ifcopenshell.api.owner.add_address(
                                model,
                                assigned_object = actor.TheActor,
                                ifc_class="IfcTelecomAddress"
                                )
                                
                                ifcopenshell.api.owner.edit_address(
                                model,
                                actor.TheActor.Addresses[0],
                                {"TelephoneNumbers" : [row["Addresses[0].TelephoneNumbers[0]"]]}
                                )                                
                            
                            
                            # Org Addresses[0].ElectronicMailAddresses
                            if address:
                                if row["Addresses[0].ElectronicMailAddresses"] != actor.TheActor.Addresses[0].ElectronicMailAddresses[0]:
                                    print(f'Updating Organization TelephoneNumbers for {actor.TheActor.Addresses[0].ElectronicMailAddresses[0] or None} with {row["Addresses[0].ElectronicMailAddresses"]}')
                                    ifcopenshell.api.owner.edit_address(
                                        model,
                                        actor.TheActor.Addresses[0],
                                        {"ElectronicMailAddresses" : [row["Addresses[0].ElectronicMailAddresses"]]}
                                    )
                            
                            elif not address:
                                ifcopenshell.api.owner.add_address(
                                    model,
                                    assigned_object = actor.TheActor,
                                    ifc_class="IfcTelecomAddress"
                                    )
                                    
                                ifcopenshell.api.owner.edit_address(
                                    model,
                                    actor.TheActor.Addresses[0],
                                    {"ElectronicMailAddresses" : [row["Addresses[0].ElectronicMailAddresses"]]}
                                    )
                            
                            
                            # Classification
                            """
                            # 
                            if not row["MF_Code"]:
                                continue
                            
                            if not actor.HasAssociations:
                                continue
                            
                            for association in actor.HasAssociations:
                                rel_classification = False
                                if not association.is_a("IfcRelAssociatesClassification"):
                                    continue
                            
                                # Add Classification Reference
                                clas_lib = model.by_type("IfcClassification")
                                if not clas_lib:
                                    print(f"The model doesnt contain any classifications \nIntroduce a classification first and retry with update")
                                    continue
                                
                                    #check existing refs to the one imported
                                    existing_refs = model.by_type("IfcClassificationReference")
                                    class_match = False
                                    for ref in existing_refs:
                                        if ref.Identification == row["MF_Code"]:
                                            class_match = True
                                            reference_match = ref
                                            print(f"There is an existing Classification Reference for the Actor that is being added")
                                            classification_ref = ifcopenshell.api.classification.add_reference(
                                                model,
                                                products = [actor],
                                                classification = clas_lib[0],
                                                reference = [r for r in existing_refs
                                                    if r.Identification == row["MF_Code"]][0]
                                            )
                                    # TODO: if class_match == False further development is needed to import a classification file or to match manually

                            if not association.RelatingClassification.Identification == row["MF_Code"]:
                            """        
                    
                    if update_setting == False:
                        continue
                
                
                # If the Actor Identification doesnt existexist
                if row["Identification"] not in actors_ids:
                    
                    # Create Organization
                    org = ifcopenshell.api.run("owner.add_organisation", model,
                        identification=row["Identification"],
                        name=row["Name"]
                    )
                    
                    
                    # Create Organization Role
                    if row["Roles[0].UserDefinedRole"]:
                        role = ifcopenshell.api.run("owner.add_role", model,
                            assigned_object = org,
                            role="USERDEFINED"
                        )
                    
                        ifcopenshell.api.owner.edit_role(
                                model, 
                                role=role, 
                                attributes={"UserDefinedRole": row["Roles[0].UserDefinedRole"]}
                            )
                    else:
                        role = ifcopenshell.api.run("owner.add_role", model,
                        assigned_object = org,
                        role=row["Roles[0].Role"]
                        )
                    
                    
                    # Role description
                    if row["Roles[0].Description"]:
                        ifcopenshell.api.owner.edit_role(
                            model, 
                            role=role, 
                            attributes={"Description": row["Roles[0].Description"]}
                        )
                    
                    
                    # Create Telecom Address
                    if row["Addresses[0].Purpose"]:
                        
                        telecom = ifcopenshell.api.owner.add_address(
                            model,
                            assigned_object=org, 
                            ifc_class="IfcTelecomAddress"
                        )
                        
                        
                        ifcopenshell.api.owner.edit_address(
                            model,
                            address=telecom,
                            attributes={"Purpose": row["Addresses[0].Purpose"],
                            "TelephoneNumbers": [row["Addresses[0].TelephoneNumbers[0]"]],
                            "ElectronicMailAddresses": [row["Addresses[0].ElectronicMailAddresses"]]}
                        )
                    
                    
                    # Create the actor from this Organization
                    actor = ifcopenshell.api.owner.add_actor(
                        model,
                        org,
                        "IfcActor"
                        )
                        
                    ifcopenshell.api.owner.edit_actor(
                        model,
                        actor,
                        attributes = {
                            "Name": org.Name,
                            "Description": row["Description"]}
                        )

                    #   Add Classification reference
                    if row["MF_Code"]:
                        # Check for existing classification
                        clas_lib = model.by_type("IfcClassification")
                        if not clas_lib:
                            print(f"The model doesnt contain any classifications \nIntroduce a classification first and retry with update")
                            continue
                        
                        #check existing refs to the one imported
                        existing_refs = model.by_type("IfcClassificationReference")
                        for ref in existing_refs:
                            if ref.Identification == row["MF_Code"]:
                                reference_match = ref
                                print(f"There is an existing Classification Reference for the Actor that is being added")
                                classification_ref = ifcopenshell.api.classification.add_reference(
                                    model,
                                    products = [actor],
                                    classification = clas_lib[0],
                                    reference = [r for r in existing_refs
                                        if r.Identification == row["MF_Code"]][0]
                                )
        # would normally load the data here
        #print(data)
        #print(reader())

    return {'FINISHED'}

    
def get_task_actor(task:ifcopenshell.entity_instance)-> ifcopenshell.entity_instance:
    
    actor = None
    
    if (assignments:=getattr(task,"HasAssignments", None)):
        for assignment in assignments:
            if not assignment.is_a("IfcRelAssignsToActor"):
                continue
            actor = assignment
    return actor
            

def get_actor_assigned_tasks(
    actor: ifcopenshell.entity_instance)-> dict[ifcopenshell.entity_instance, list[ifcopenshell.entity_instance]]:
    """
    Get the tasks to which the Actor is assigned
    Returns a dictionary of IfcWorkSchedule and the IfcTasks for which the Actor is 
    assigned under 
    
    """
    actor_dict: dict[ifcopenshell.entity_instance, list[ifcopenshell.entity_instance]] = {}

    #work_schedules = model.by_type("IfcWorkSchedule")
    
    #for work_schedule in work_schedules:
    
    actions = getattr(actor, "IsActingUpon", None)
    
    if not actions:
        return actor_dict
    
    if actions:
        for action in actions:
            related_objs = getattr(action, "RelatedObjects", None)
            if not related_objs:
                continue
            
            for obj in related_objs:
                if not obj.is_a("IfcTask"):
                    continue

                work_schedule = get_task_workschedule(obj)
                #actor_dict[work_schedule].extend(object)
                if not work_schedule:
                    continue
                
                actor_dict.setdefault(work_schedule, []).append(obj)
                #print(f"The task {obj} is not associated with a workschedule.\nReview the structure of your IFC File for errors")
                    
    return actor_dict


def update_actor_tasks(self, context):
    scene = context.scene
    model = get_ifc_file()


    # Clear list
    scene.actor_tasks.clear()

    # Get selected actor
    actor_item = scene.bim_actors[scene.bim_actors_index]
    actor = model.by_id(actor_item.global_id)

    actor_dict = get_actor_assigned_tasks(actor)

    # Populate list
    for ws, tasks in actor_dict.items():

        # Add WorkSchedule header row
        header = scene.actor_tasks.add()
        header.row_type = 'WS'
        header.workschedule_id = ws.id()
        header.workschedule_name = ws.Name or "(Unnamed WS)"

        # Add tasks under this WorkSchedule
        for task in tasks:
            item = scene.actor_tasks.add()
            item.row_type = 'TASK'
            item.task_id = task.id()
            item.task_name = task.Name or "(Unnamed Task)"
            item.task_description = task.Description or ""
            item.workschedule_id = ws.id()
            item.workschedule_name = ws.Name or "(Unnamed WS)"


def get_task_workschedule(
    task: ifcopenshell.entity_instance)-> ifcopenshell.entity_instance:
    
    nests = getattr(task, "Nests", None)
    if nests: # we are still on child task
        for nest in nests:
            parent = getattr(nest,"RelatingObject", None)
            if parent.is_a("IfcTask"):
                return get_task_workschedule(parent)

    # nests is None so we have a Summary task
    assignments = getattr(task, "HasAssignments", None)
    if not assignments:
        print(f"The task {task.Name} doesnt have any assignments check the validity of the work schedule")
        return None
        
    for assignment in assignments:
        control =  getattr(assignment, "RelatingControl", None)
        if control and control.is_a("IfcWorkSchedule"):
            return control
        
    return None
   
   
def get_unassigned_actor_tasks()->dict[ifcopenshell.entity_instance, list[ifcopenshell.entity_instance]]:
    
    model = get_ifc_file()
    if not model:
        return {}
    
    wss = model.by_type("IfcWorkSchedule")
    
    print(wss)
    
    tasks_dict = {}
    
    tasks_dict: dict[ifcopenshell.entity_instance, list[ifcopenshell.entity_instance]] = {}
    
    
    def find_leaf_tasks(current_task):
        #
        #   Recursively explores the task breakdown structure.
        #   If a task has no sub-tasks (nested tasks), it's a leaf and is added to the list.
        #
        nesting = getattr(current_task, "IsNestedBy",None)
        
        is_parent_task = False
        if nesting:
            for rel_nests in nesting:
                # We iterate through the nested cost_items (RelatedObjects)
                for nested_task in rel_nests.RelatedObjects:
                    if nested_task.is_a("IfcTask"):
                        is_parent_task = True
                        # This task has children, so we recurse deeper.
                        find_leaf_tasks(nested_task)

        # If a task is not a parent, it is a leaf task.
        if not is_parent_task:
            leaf_tasks.append(current_task)
    
    
    
    for ws in wss:
        
        leaf_tasks = []
        if not ws.Controls:
            continue
            
        for rel in ws.Controls:
            for top_level_task in rel.RelatedObjects:
                if top_level_task.is_a("IfcTask"):
                    find_leaf_tasks(top_level_task)
        for task in leaf_tasks:
            assignments = getattr(task, "HasAssignments", None)
            if not assignments:
                print(f"The task {task.Name} {task.id()} has No assignments")
                tasks_dict.setdefault(ws, []).append(task)
                continue
            
            actor_exists = False
            
            for assignment in assignments:
                if assignment.is_a("IfcRelAssignsToActor"):
                    actor_exists = True
                    break
                    
            if actor_exists == True:
                continue
            
            elif actor_exists == False:
                tasks_dict.setdefault(ws, []).append(task)
    #print(tasks_dict)
    return tasks_dict
        
        
def update_unassigned_actor_tasks(self, context):
    scene = context.scene
    model = get_ifc_file()
    if not model:
            return
    
    print("In update_unassigned_actor_tasks")
    # Clear list
    scene.unassigned_actor_tasks.clear()

    tasks_dict = get_unassigned_actor_tasks()

    # Populate list
    for ws, tasks in tasks_dict.items():

        # Add WorkSchedule header row
        header = scene.unassigned_actor_tasks.add()
        header.row_type = 'WS'
        header.workschedule_id = ws.id()
        header.workschedule_name = ws.Name or "(Unnamed WS)"

        # Add tasks under this WorkSchedule
        for task in tasks:
            item = scene.unassigned_actor_tasks.add()
            item.row_type = 'TASK'
            item.task_id = task.id()
            item.task_name = task.Name or "(Unnamed Task)"
            item.task_description = task.Description or task.Name or ""
            item.workschedule_id = ws.id()
            item.workschedule_name = ws.Name or "(Unnamed WS)"


def assign_task_actor(
    model: ifcopenshell.file,
    task_actor: ifcopenshell.entity_instance,
    task: ifcopenshell.entity_instance
    )-> ifcopenshell.entity_instance:
    
    new_actor_for_task = ifcopenshell.api.owner.assign_actor(
        model,
        task_actor,
        task
        )
    return new_actor_for_task
    
    
def unassign_task_actor(model,task_actor,task):
    
    ifcopenshell.api.owner.unassign_actor(
        model,
        task_actor,
        task
        )


def get_selected_unassigned_task(context):
    """Return the IfcActor entity corresponding to the UI list selection."""
    model = get_ifc_file()
    if not model:
        return None
    idx = context.scene.unassigned_actor_tasks_index
    if idx < 0 or idx >= len(context.scene.unassigned_actor_tasks):
        return None
    item = context.scene.unassigned_actor_tasks[idx]
    # Retrieve by internal id for reliability
    try:
        return model[item.task_id]
    except Exception:
        # Fallback by GlobalId if available
        if item.global_id:
            try:
                return next(e for e in model.by_type("IfcTask") if getattr(e, "GlobalId", "") == item.global_id)
            except StopIteration:
                return None
        return None

# ---------------------------------------------------------------------------
# Data model for UIList
# ---------------------------------------------------------------------------

class BIM_ActorClassification(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty(name="Classification")


class BIM_ActorItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    description: bpy.props.StringProperty(name="Description")
    entity_id: bpy.props.IntProperty(name="IFC Entity ID")
    global_id: bpy.props.StringProperty(name="GlobalId")
    classifications: bpy.props.CollectionProperty(type=BIM_ActorClassification)
    
    
class BIM_UL_actors(bpy.types.UIList):
    """UIList to display actors within the IFC model."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if item:
            row = layout.row(align=True)
            row.label(text=item.name or "(no name)", icon='USER')
            if item.classifications:
                classifications = item.classifications
                if len(classifications)>1:
                    row.label(text="Multiple Classifications for this Actor", icon='SEQ_SEQUENCER') #SEQ_STRIP_DUPLICATE BOOKMARKS SEQ_SEQUENCER
                else:
                    row.label(text=classifications[0].text, icon='SEQ_SEQUENCER') #SEQ_STRIP_DUPLICATE BOOKMARKS SEQ_SEQUENCER
                # for classification in classifications:
                    # print((classification.name))
                    # print((classification.text))
                    # row = layout.row(align=True)   # new row for each classification
                    # row.label(text=classification.text, icon='SEQ_SEQUENCER') #SEQ_STRIP_DUPLICATE BOOKMARKS SEQ_SEQUENCER
            else:
                row = layout.row(align=True)
                row.label(text="No classification associated", icon='ERROR') #SEQ_STRIP_DUPLICATE
            # Tooltip-like description snippet
            if item.description:
                sub = layout.row()
                sub.enabled = False
                sub.label(text=item.description[:40])


class BIM_ActorTaskItem(bpy.types.PropertyGroup):
    row_type: bpy.props.EnumProperty(
        items=[
            ('WS', "WorkSchedule", ""),
            ('TASK', "Task", "")
        ]
    )

    task_id: bpy.props.IntProperty()
    task_name: bpy.props.StringProperty()
    task_description: bpy.props.StringProperty()

    workschedule_id: bpy.props.IntProperty()
    workschedule_name: bpy.props.StringProperty()
    

class BIM_UL_ActorTasks(bpy.types.UIList):

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        row = layout.row(align=True)

        
        if item.row_type == 'WS':
            # WorkSchedule header
            row.label(text=item.workschedule_name, icon="FILE_FOLDER")

            op = row.operator("bim.jump_to_ifc", text="", icon="VIEWZOOM")
            op.ifc_id = item.workschedule_id

        else:
            # Task row (indented)
            sub = row.row()
            sub.label(text="      " + item.task_description, icon="SEQ_SEQUENCER")

            op = row.operator("bim.jump_to_ifc", text="", icon="STYLUS_PRESSURE")
            op.ifc_id = item.task_id


class BIM_UnassignedActorTaskItem(bpy.types.PropertyGroup):
    row_type: bpy.props.EnumProperty(
        items=[
            ('WS', "WorkSchedule", ""),
            ('TASK', "Task", "")
        ]
    )

    task_id: bpy.props.IntProperty()
    task_name: bpy.props.StringProperty()
    task_description: bpy.props.StringProperty()

    workschedule_id: bpy.props.IntProperty()
    workschedule_name: bpy.props.StringProperty()
    

class BIM_UL_UnassignedActorTasks(bpy.types.UIList):

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        
        print(f"entered BIM_UL_UnassignedActorTasks")
        row = layout.row(align=True)

        
        if item.row_type == 'WS':
            # WorkSchedule header
            row.label(text=item.workschedule_name, icon="FILE_FOLDER")

            op = row.operator("bim.jump_to_ifc", text="", icon="VIEWZOOM")
            op.ifc_id = item.workschedule_id

        else:
            # Task row (indented)
            sub = row.row()
            sub.label(text="      " + item.task_description, icon="SEQ_SEQUENCER")

            op = row.operator("bim.jump_to_ifc", text="", icon="STYLUS_PRESSURE")
            op.ifc_id = item.task_id
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


class BIM_OT_ImportActorsData(Operator, ImportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "bim.import_actor_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Import Actor Data"
    bl_description = "Read actors csv file and import to\nupdate the contents of the IFC file."

    # ImportHelper mix-in class uses this.
    filename_ext = ".csv"

    filter_glob: StringProperty(
        default="*.csv",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )
    
    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    use_setting: BoolProperty(
        name="Update existing actors in the file?",
        description="Having this checked the existing actors in the file are compared with the ones in the imported file. If the Organization (Name column) respresenting the actor already exists then the rest of the fields will be overwritten with new ones from the imported file. Othewise the Actors in the fie will be imported as they appear",
        default=True,
    )
    """
    type: EnumProperty(
        name="Example Enum",
        description="Choose between two items",
        items=(
            ('OPT_A', "First Option", "Description one"),
            ('OPT_B', "Second Option", "Description two"),
        ),
        default='OPT_A',
    )
    """
    def execute(self, context):
        return import_actor_data(context, self.filepath, self.use_setting)


class BIM_OT_JumpToIFC(bpy.types.Operator):
    bl_idname = "bim.jump_to_ifc"
    bl_label = f"Jump to IFC Entity "
    bl_description = "Select the coresponding task in the Workschedule Panel."

    ifc_id: bpy.props.IntProperty()

    def execute(self, context):
        model = bonsai.tool.Ifc.get()
        entity = model.by_id(self.ifc_id)
        print(entity.Description, entity.id())
        
        
        # Select the Blender object representing this IFC entity
        
        Sequence.enable_editing_work_schedule_tasks(get_task_workschedule(entity))
        Sequence.go_to_task(entity)

        return {'FINISHED'}


class BIM_OT_UpdateActorTasks(bpy.types.Operator):
    bl_idname = "bim.update_actor_tasks"
    bl_label = "Update Actor Tasks"

    def execute(self, context):
        scene = context.scene
        model = bonsai.tool.Ifc.get()


        return {'FINISHED'}


class BIM_OT_UpdateUnassignedActorTasks(bpy.types.Operator):
    bl_idname = "bim.update_unassigned_actor_tasks"
    bl_label = "Update Unassigned Actor Tasks"

    def execute(self, context):
        scene = context.scene
        model = bonsai.tool.Ifc.get()
        update_unassigned_actor_tasks(self, context)

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


        task = get_selected_unassigned_task(context)
        print(task)
        #task = Sequence.get_highlighted_task()
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
            # Only one Actor permited
            elif rel:
                self.report({'INFO'}, "The task can have only one Actor. Un-assign existing and try again")
                return {'FINISHED'}
                

        # Create new relationship
        rel = model.create_entity(
            "IfcRelAssignsToActor",
            GlobalId=ifcopenshell.guid.new(),
            RelatingActor=actor,
            RelatedObjects=[task],
            Name=f"Assign {getattr(actor, 'Name', '')} to {getattr(task, 'Name', '')}" or None,
            Description="Assigned via BIM_PrMngmnt_Actors panel"
        )

        # Ensure bidirectional links are maintained if needed (ifcopenshell usually handles this)
        self.report({'INFO'}, f"Assigned actor: {getattr(actor, 'Name', '(no name)')}")
        return {'FINISHED'}


class BIM_OT_unassign_actor(bpy.types.Operator):
    bl_idname = "bim.unassign_actor"
    bl_label = "Unassign Task Actor(s)"
    bl_description = "Unassign all IfcRelAssignsToActor relationships from the highlighted task"
    
    #model = get_ifc_file()
    
    def execute(self, context):
        
        model = get_ifc_file()
        
        task = get_selected_unassigned_task(context)
        print(task)
        #task = Sequence.get_highlighted_task()
        
        task_actor = [assignment.RelatingActor for assignment in task.HasAssignments if assignment.is_a("IfcRelAssignsToActor")][0]
        
        if not model:
            self.report({'WARNING'}, "No IFC model loaded")
            return {'CANCELLED'}

        if not task:
            self.report({'WARNING'}, "No highlighted task")
            return {'CANCELLED'}

        to_remove = list(iter_task_actor_assignments(task))
        if not to_remove:
            self.report({'INFO'}, "Task has no actor assignments")
            return {'FINISHED'}

        #   20251204 Not fond of this approach TODO change it
        #for rel in to_remove:
        #    model.remove(rel)
        
        # TODO:Prefer with unnasign
        ifcopenshell.api.owner.unassign_actor(
            model,
            task_actor,
            task
            )

        self.report({'INFO'}, f"Removed {len(to_remove)} actor assignment(s)")
        return {'FINISHED'}
# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class BIM_PT_highlighted_actor_info(bpy.types.Panel):
    """
    Show information for the currently highlighted Actor form the actors panel

    Displays:
    - Actor name and description
    - Actor organization/person
    - Actor classifications (Name + Identification)
    - Assigned Tasks: name, description, 
    - Assigned Resources: Name , Description
    - Actor list from the IFC file with selection + assign/unassign buttons
    """
    bl_idname = "BIM_PT_highlighted_actor_info"
    bl_label = "Highlighted Actor Information"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BIM_PrMngmnt_Actors'


    
    def draw(self, context):
        layout = self.layout
        
        #layout_2 = self.layout
        
        #what_ever_box = layout.box()
        # Make sure actors are loaded each draw (keeps in sync)
        #ensure_actors_loaded(context)
            
        tab = 9*' '

        self.draw_actor_list(layout, context)

    def draw_actor_list(self, layout, context):
        model = get_ifc_file()
        actors_box = layout.box()
        actors_box.label(text="Actors in file :", icon='USER')
        
        #   20251212 adition for import operator
        row_imp = actors_box.row(align=True)
        row_imp.operator("bim.import_actor_data", text = "", icon = "IMPORT")
        
        
        
        ###
        actors_box.template_list(
            "BIM_UL_actors", "",
            context.scene, "bim_actors",
            context.scene, "bim_actors_index",
            rows=4
        )
        tab = 9*' '
        row = actors_box.row(align=True)
        row.operator("bim.refresh_actors", text="Refresh Actors List", icon='FILE_REFRESH')
        # Show quick details of selected
        selected = None
        if 0 <= context.scene.bim_actors_index < len(context.scene.bim_actors):
            selected = context.scene.bim_actors[context.scene.bim_actors_index]
        if selected:
            info_box = actors_box.box()
            info_box.label(text=f"Selected Actor: {selected.name}", icon='INFO')
            info_box.label(text=f"{tab}Actor Id: {selected.entity_id}")
            
            if selected.description:
                for line in wrap_text(selected.description, len(selected.description)):
                    info_box.label(text=f"{tab}Description: {line}")
            else:
                info_box.label(text=f"{tab}Description: No description available")
            
            
            if selected.classifications:
                for cls in selected.classifications:
                    info_box.label(text=f"{tab}Classification: {cls.text}")
            else:
                info_box.label(text=f"{tab}Classification: No Classification assigned")
            """
            # Show the tasks to which the actor is assigned
            tasks_assigned_info = actors_box.box()
            
            selected_actor = model.by_guid(selected.global_id)
            actor_dict = {}
            actor_dict = get_actor_assigned_tasks(selected_actor)
            #print(selected_actor)
            
            if not actor_dict:
                tasks_assigned_info.label(text=f"{tab}!!!The Actor has no task associaions!!!")
                return
            tasks_assigned_info.label(text=f"{tab}The Actor: {selected.name}")
            for work_schedule, tasks in actor_dict.items():
                
                row = tasks_assigned_info.row()
                ws_row = tasks_assigned_info.row()
                row.label(text=f"{2*tab} Is assigned in the following ({len(tasks)}) tasks of the Workschedule:")
                
                ws_row.label(text=f"{2*tab} {work_schedule.Name[0:30]}")
                
                # Jump-to operator
                #op = row.operator("bim.jump_to_ifc", text="", icon="VIEWZOOM")
                #op.ifc_id = work_schedule.id()
                
                for task in tasks:
                    row = tasks_assigned_info.row(align=True)
                    row.label(text=f"{3*tab} Task: {task.Description}")
                    op = row.operator("bim.jump_to_ifc", text="", icon="STYLUS_PRESSURE")
                    op.ifc_id = task.id()
            """

class BIM_PT_ActorTasks(bpy.types.Panel):
    bl_label = "Actor Task Assignments"
    bl_idname = "BIM_PT_actor_tasks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BIM_PrMngmnt_Actors"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        model = bonsai.tool.Ifc.get()
        
        unassign_box = layout.box()
        btn_row = unassign_box.row(align=True)
        btn_row.operator("bim.unassign_actor", text="Unassign Task Actor(s)", icon='EVENT_MINUS')
        #btn_row.operator("bim.assign_actor", text="Assign Selected Actor to Task", icon='EVENT_PLUS')
        
        # Draw the UIList
        layout.template_list(
            "BIM_UL_ActorTasks",
            "",
            scene,
            "actor_tasks",
            scene,
            "actor_tasks_index",
            rows=6,
        )

class BIM_PT_UnassignedActorTasks(bpy.types.Panel):
    bl_label = "Unassigned Actor Tasks"
    bl_idname = "BIM_PT_unassignedactor_tasks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BIM_PrMngmnt_Actors"

    

    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        model = bonsai.tool.Ifc.get()
        #update_unassigned_actor_tasks(self, context)
        

        
        
        
        
        
        assign_box = layout.box()
        btn_row = assign_box.row(align=True)
        #btn_row.operator("bim.unassign_actor", text="Unassign Task Actor(s)", icon='EVENT_MINUS')
        btn_row.operator("bim.assign_actor", text="Assign Selected Actor to Task", icon='EVENT_PLUS')
        
        layout.operator("bim.update_unassigned_actor_tasks", icon='FILE_REFRESH', text="Find Unassigned Tasks")
        
        # Draw the UIList
        layout.template_list(
            "BIM_UL_UnassignedActorTasks",
            "",
            scene,
            "unassigned_actor_tasks",
            scene,
            "unassigned_actor_tasks_index",
            rows=6,
        )

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    BIM_ActorClassification,
    BIM_ActorItem,
    BIM_ActorTaskItem,
    BIM_UnassignedActorTaskItem,
    BIM_UL_actors,
    BIM_UL_ActorTasks,
    BIM_UL_UnassignedActorTasks,
    BIM_OT_refresh_actors,
    BIM_OT_ImportActorsData,
    BIM_OT_JumpToIFC,
    BIM_OT_UpdateActorTasks,
    BIM_OT_UpdateUnassignedActorTasks,
    BIM_OT_assign_actor,
    BIM_OT_unassign_actor,
    BIM_PT_highlighted_actor_info,
    BIM_PT_ActorTasks,
    BIM_PT_UnassignedActorTasks,
    )

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Standard Actor Properties
    bpy.types.Scene.bim_actors = bpy.props.CollectionProperty(type=BIM_ActorItem)
    bpy.types.Scene.bim_actors_index = bpy.props.IntProperty(default=0,
        update=update_actor_tasks
        )
    
    # bpy.types.Scene.unassigned_actor_tasks = bpy.props.CollectionProperty(type = BIM_UnassignedActorTaskItem)
    # bpy.types.Scene.unassigned_actor_tasks_index = bpy.props.IntProperty(default =0,update = update_unassigned_actor_tasks)
    
    
    
    bpy.types.TOPBAR_MT_file_import.append(BIM_PT_highlighted_actor_info.draw_actor_list)
    
    
    # Assigned Tasks Properties
    bpy.types.Scene.actor_tasks = bpy.props.CollectionProperty(type=BIM_ActorTaskItem)
    bpy.types.Scene.actor_tasks_index = bpy.props.IntProperty()

    
    # Unassigned Tasks Properties (FIXED REGISTRATION)
    bpy.types.Scene.unassigned_actor_tasks = bpy.props.CollectionProperty(type=BIM_UnassignedActorTaskItem)
    #bpy.types.Scene.unassigned_actor_tasks_index = bpy.props.IntProperty(default =0,update = update_unassigned_actor_tasks)
    bpy.types.Scene.unassigned_actor_tasks_index = bpy.props.IntProperty(default =0)


def unregister():
    del bpy.types.Scene.bim_actors_index
    del bpy.types.Scene.bim_actors
    bpy.types.TOPBAR_MT_file_import.append(BIM_PT_highlighted_actor_info.draw_actor_list)
    
    bpy.types.Scene.actor_tasks
    bpy.types.Scene.actor_tasks_index

    bpy.types.Scene.unassigned_actor_tasks
    bpy.types.Scene.unassigned_actor_tasks_index

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
