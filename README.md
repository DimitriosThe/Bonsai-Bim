# Bonsai-Bim
Script and snippets for Blender Add-on BonsaiBIM
### BL_PNL_ACT_TASK_ACTOR_.py
---
  #### Shows:
  -   highlighted (selected) task info,
  -   task Classificaton,
  -   Task resource  (if any)
  -   Task resource base cost
  -   ---
  -   Task actor Name,
  -   Task actor Description
  -   Task Actor Organization ("representing" the Actor),
  -   Task Actor Classification References
  -   ---
  -   Task Resource Actor Name
  -   Task Resource Actor id
  -   Task Resource Actor Organization
  -   ---
  -   Selected Resource Name (From the resource panel)
  -   Selected Resource id
  -   Selected Resource Name Base Cost
  -   Selected Resource Actor
  -   You can Assign and unassign a resource actor
       * By assigning an Actor it creates a new actor specific resource build-up
       * if the resource is assigned to a task it creates a copy of the resource for  the specific actor and re-assigns the new actor resource to the task
       * If the resource has an actor allready then it creates a new resource for this actor and re-assigns the new resource to the Task and re-assigns the actor to the task 
       * When Unassigning Resource Actor:
         - If the resource is assigned to a Task it Looks up for resource build up from the existing resources with the similar name that do not have an Actor. If found it unassigns the Actor from the resource, Unassigns the existing resource from the Task, Assigns the matched resource to the Task
         - If the resource is not assigned to a Task , it un assigns the Actor
  -   ---
  -  Actors in file
      -  List of existing actors in the file, along with their classification reference and Description
      -  Option to import Actors from a csv file and selectable option to Update the actors imported from the file vs the existing ones
  -  ---
  -  Selected Actor information
  -    *  Actor id
       *  Descrioption
       *  Classifications
![Image](Highlighted_Task_and_associated_Actors_panel.png)

